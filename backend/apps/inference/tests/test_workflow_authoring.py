"""Workflow authoring: saved workflows, the prompt node, structured output,
and single-step re-run (PRD 11).

Builds on the PRD 10 engine. Upstream and the broker are mocked; jobs run inline
via ``jobs.process_jobs_inline``. Shares the fixture style of test_async_jobs.
"""
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.inference import jobs, workflows
from apps.inference.models import (
    InferenceRequest, Provider, ProviderModel, ProviderService, Workflow,
    WorkflowRun, link_catalog_model,
)

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _async_on(settings):
    settings.ASYNC_ENABLED = True


@pytest.fixture
def user(db):
    return User.objects.create_user(email="author@example.com", password="x")


def _provider(u, name="node", hostname="n1"):
    return Provider.objects.create(
        user=u, name=name, tailnet_hostname=hostname,
        is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
    )


def _service_model(u, service_type, model_name, *, provider=None,
                   max_concurrent=1, resource_group=""):
    p = provider or _provider(
        u, name=f"node-{service_type}-{model_name}",
        hostname=f"n-{service_type}-{model_name}",
    )
    svc = ProviderService.objects.create(
        provider=p, name=f"{service_type}-{model_name}", engine="other",
        service_type=service_type, access_policy=ProviderService.ACCESS_AUTHENTICATED,
        max_concurrent=max_concurrent, resource_group=resource_group,
    )
    pm = ProviderModel(provider=p, name=model_name, service=svc)
    link_catalog_model(pm)
    pm.save()
    return p, svc, pm


def _client(u):
    from rest_framework.test import APIClient
    c = APIClient()
    c.force_authenticate(user=u)
    return c


class _FakeResp:
    def __init__(self, content=b"", status=200, content_type="application/json", headers=None):
        self.content = content if isinstance(content, bytes) else json.dumps(content).encode()
        self.status_code = status
        self.ok = 200 <= status < 300
        self.headers = {"content-type": content_type, **(headers or {})}
        self.text = self.content.decode(errors="replace")

    def json(self):
        return json.loads(self.content)


def _image_resp(n=1):
    import base64
    px = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
    return _FakeResp({"created": 1, "data": [{"b64_json": px} for _ in range(n)]})


def _chat_resp(content):
    return _FakeResp({"choices": [{"message": {"role": "assistant", "content": content}}]})


# --- saved workflow CRUD -----------------------------------------------------


class TestWorkflowCrud:
    def test_create_list_get_update_delete(self, user):
        c = _client(user)
        spec = {"steps": [
            {"id": "img", "kind": "inference", "type": "image", "body": {"prompt": "x"}},
        ]}
        # create
        r = c.post("/v1/workflows", {"name": "My flow", "spec": spec}, format="json")
        assert r.status_code == 201, r.content
        wid = r.json()["id"]
        assert r.json()["step_count"] == 1

        # list (slim — no spec)
        r = c.get("/v1/workflows")
        assert r.status_code == 200
        assert any(w["id"] == wid for w in r.json()["data"])

        # get (full spec)
        r = c.get(f"/v1/workflows/{wid}")
        assert r.status_code == 200 and r.json()["spec"]["steps"][0]["id"] == "img"

        # update name + spec
        spec["steps"].append({"id": "review", "kind": "gate", "depends_on": ["img"]})
        r = c.patch(f"/v1/workflows/{wid}", {"name": "Renamed", "spec": spec}, format="json")
        assert r.status_code == 200 and r.json()["name"] == "Renamed"
        assert r.json()["step_count"] == 2

        # delete
        r = c.delete(f"/v1/workflows/{wid}")
        assert r.status_code == 204
        assert not Workflow.objects.filter(id=wid).exists()

    def test_create_requires_name(self, user):
        r = _client(user).post("/v1/workflows", {"spec": {"steps": []}}, format="json")
        assert r.status_code == 400

    def test_empty_draft_spec_allowed(self, user):
        # A brand-new builder draft (no steps yet) saves fine; full validation
        # only bites at run time.
        r = _client(user).post("/v1/workflows", {"name": "Draft"}, format="json")
        assert r.status_code == 201
        assert r.json()["spec"] == {"steps": []}

    def test_duplicate_step_id_rejected_on_save(self, user):
        spec = {"steps": [
            {"id": "a", "kind": "inference", "type": "image"},
            {"id": "a", "kind": "gate"},
        ]}
        r = _client(user).post("/v1/workflows", {"name": "Bad", "spec": spec}, format="json")
        assert r.status_code == 400

    def test_cannot_touch_another_users_workflow(self, user):
        other = User.objects.create_user(email="other@example.com", password="x")
        wf = Workflow.objects.create(user=other, name="theirs", spec={"steps": []})
        c = _client(user)
        assert c.get(f"/v1/workflows/{wf.id}").status_code == 404
        assert c.delete(f"/v1/workflows/{wf.id}").status_code == 404


class TestRunSavedWorkflow:
    def test_run_saved_workflow_with_inputs(self, user):
        _service_model(user, "image", "flux")
        spec = {
            "inputs": [{"name": "subject", "label": "Subject", "type": "text", "required": True}],
            "steps": [
                {"id": "img", "kind": "inference", "type": "image",
                 "body": {"prompt": "{{inputs.subject}}"}},
            ],
        }
        wf = Workflow.objects.create(user=user, name="One image", spec=spec)
        c = _client(user)
        # missing required input → 400
        assert c.post(f"/v1/workflows/{wf.id}/runs", {"inputs": {}}, format="json").status_code == 400
        # with input → 202 and a run linked to the workflow
        r = c.post(f"/v1/workflows/{wf.id}/runs", {"inputs": {"subject": "a teapot"}}, format="json")
        assert r.status_code == 202, r.content
        run = WorkflowRun.objects.get(id=r.json()["id"])
        assert run.workflow_id == wf.id
        job = run.steps.get(step_id="img").jobs.first()
        assert job.payload.get("prompt") == "a teapot"


class TestForking:
    def test_fork_template_into_editable_workflow(self, user):
        r = _client(user).post("/v1/workflows/from-template/image-variations", {}, format="json")
        assert r.status_code == 201, r.content
        wf = Workflow.objects.get(id=r.json()["id"])
        # The input schema travels with the spec so the run form still works.
        assert any(i["name"] == "subject" for i in wf.spec["inputs"])
        assert {s["id"] for s in wf.spec["steps"]} == {"prompts", "images"}

    def test_fork_unknown_template_404(self, user):
        r = _client(user).post("/v1/workflows/from-template/nope", {}, format="json")
        assert r.status_code == 404

    def test_fork_run_into_workflow(self, user):
        _service_model(user, "image", "flux")
        spec = {"steps": [
            {"id": "img", "kind": "inference", "type": "image", "model": "flux",
             "body": {"prompt": "x"}},
        ]}
        run = workflows.start_run(user, spec, name="ran once")
        r = _client(user).post(f"/v1/workflows/from-run/{run.id}", {}, format="json")
        assert r.status_code == 201
        wf = Workflow.objects.get(id=r.json()["id"])
        assert wf.spec["steps"][0]["id"] == "img"


# --- prompt node (meta-prompting) --------------------------------------------


class TestPromptNode:
    def test_prompt_node_single_feeds_downstream_image(self, user):
        _service_model(user, "llm", "qwen")
        _service_model(user, "image", "flux")
        spec = {"steps": [
            {"id": "p", "kind": "prompt", "target": "image",
             "input": "a cozy cabin"},
            {"id": "img", "kind": "inference", "type": "image",
             "body": {"prompt": "{{steps.p.output.prompt}}"}},
        ]}
        run = workflows.start_run(user, spec)
        # The prompt step issued a chat job whose system message is the image preset.
        pjob = run.steps.get(step_id="p").jobs.first()
        assert pjob.inference_type == "LLM"
        sys = pjob.payload["messages"][0]["content"].lower()
        assert "image" in sys

        def _post(url, **kw):
            return _chat_resp("a warm cabin at golden hour, wide angle") \
                if "chat/completions" in url else _image_resp()

        with patch("apps.inference.openai_views.requests.post", side_effect=_post):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "DONE"
        img = run.steps.get(step_id="img").jobs.first()
        assert img.payload.get("prompt") == "a warm cabin at golden hour, wide angle"

    def test_prompt_node_count_fans_out_a_map(self, user):
        _service_model(user, "llm", "qwen")
        _service_model(user, "image", "flux")
        spec = {"steps": [
            {"id": "p", "kind": "prompt", "target": "image", "count": 3,
             "input": "variations on a teapot"},
            {"id": "imgs", "kind": "map", "type": "image",
             "over": "{{steps.p.output.prompts}}", "body": {"prompt": "{{item}}"}},
        ]}
        run = workflows.start_run(user, spec)
        prompts = json.dumps({"prompts": ["one", "two", "three"]})

        def _post(url, **kw):
            return _chat_resp(prompts) if "chat/completions" in url else _image_resp()

        with patch("apps.inference.openai_views.requests.post", side_effect=_post):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "DONE"
        assert run.steps.get(step_id="imgs").jobs.count() == 3


# --- structured output -------------------------------------------------------


class TestStructuredOutput:
    def test_response_schema_attaches_response_format_and_parses(self, user):
        _service_model(user, "llm", "qwen")
        captured = {}
        spec = {"steps": [
            {"id": "plan", "kind": "inference", "type": "chat",
             "response_schema": {"type": "object",
                                 "properties": {"title": {"type": "string"}}},
             "body": {"messages": [{"role": "user", "content": "make a title"}]}},
        ]}
        run = workflows.start_run(user, spec)

        def _post(url, **kw):
            captured["body"] = kw.get("json")
            return _chat_resp(json.dumps({"title": "Hello"}))

        with patch("apps.inference.openai_views.requests.post", side_effect=_post):
            jobs.process_jobs_inline()
        # response_format was forwarded upstream...
        assert captured["body"]["response_format"]["type"] == "json_schema"
        # ...and the JSON reply was parsed into the step output.
        run.refresh_from_db()
        out = run.steps.get(step_id="plan").output
        assert out.get("title") == "Hello"


# --- single-step re-run ------------------------------------------------------


class TestStepRerun:
    def test_rerun_step_regenerates_and_keeps_old_in_gallery(self, user):
        _service_model(user, "image", "flux")
        spec = {"steps": [
            {"id": "img", "kind": "inference", "type": "image", "model": "flux",
             "body": {"prompt": "x"}},
        ]}
        run = workflows.start_run(user, spec)
        with patch("apps.inference.openai_views.requests.post", return_value=_image_resp()):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "DONE"
        first_job = run.steps.get(step_id="img").jobs.first()
        assert first_job is not None

        # Re-run just that step.
        r = _client(user).post(f"/v1/workflows/runs/{run.id}/steps/img/rerun", {}, format="json")
        assert r.status_code == 200, r.content
        run.refresh_from_db()
        assert run.status == "RUNNING"
        # Old job detached (survives in the gallery), not deleted.
        first_job.refresh_from_db()
        assert first_job.step_run_id is None
        with patch("apps.inference.openai_views.requests.post", return_value=_image_resp()):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "DONE"
        # A fresh job now backs the step.
        assert run.steps.get(step_id="img").jobs.exclude(id=first_job.id).exists()

    def test_rerun_resets_downstream_steps(self, user):
        _service_model(user, "image", "flux")
        spec = {"steps": [
            {"id": "a", "kind": "inference", "type": "image", "model": "flux", "body": {"prompt": "x"}},
            {"id": "b", "kind": "inference", "type": "image", "model": "flux",
             "depends_on": ["a"], "body": {"prompt": "y"}},
        ]}
        run = workflows.start_run(user, spec)
        with patch("apps.inference.openai_views.requests.post", return_value=_image_resp()):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "DONE"
        ok, err = workflows.rerun_step(run, "a")
        assert ok, err
        run.refresh_from_db()
        # Both a and its dependent b were reset and must run again.
        assert run.steps.get(step_id="b").status in ("PENDING", "RUNNING")

    def test_rerun_unknown_step_409(self, user):
        _service_model(user, "image", "flux")
        spec = {"steps": [
            {"id": "img", "kind": "inference", "type": "image", "model": "flux", "body": {"prompt": "x"}},
        ]}
        run = workflows.start_run(user, spec)
        r = _client(user).post(f"/v1/workflows/runs/{run.id}/steps/nope/rerun", {}, format="json")
        assert r.status_code == 409
