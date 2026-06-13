"""Async jobs, batches and workflows (PRD 10).

Covers: async submission (202 + queued job), the dispatcher's capacity gating
(per-service max_concurrent + shared resource_group), job execution via the
reused modality runners, retry/backoff, cancel, batches, and the workflow DAG
engine (fan-out + transform + human gate). Upstream and the broker are both
mocked — jobs run inline via ``jobs.process_jobs_inline``.
"""
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from apps.inference import jobs, workflows
from apps.inference.models import (
    Batch, InferenceRequest, Provider, ProviderModel, ProviderService,
    ResourceGroup, WorkflowRun, link_catalog_model,
)

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _async_on(settings):
    settings.ASYNC_ENABLED = True


# --- fixtures / helpers ------------------------------------------------------


@pytest.fixture
def user(db):
    return User.objects.create_user(email="async@example.com", password="x")


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


# --- async submission --------------------------------------------------------


class TestAsyncSubmit:
    def test_image_async_returns_202_and_queues(self, user):
        _service_model(user, "image", "flux")
        resp = _client(user).post(
            "/v1/images/generations",
            {"model": "flux", "prompt": "a cat", "async": True}, format="json",
        )
        assert resp.status_code == 202, resp.content
        body = resp.json()
        assert body["status"] == "QUEUED"
        job = InferenceRequest.objects.get(id=body["id"])
        assert job.is_async and job.status == "QUEUED"
        # Nothing was sent upstream yet.
        assert job.results is None

    def test_async_disabled_returns_503(self, user):
        _service_model(user, "image", "flux")
        with override_settings(ASYNC_ENABLED=False):
            resp = _client(user).post(
                "/v1/images/generations",
                {"model": "flux", "prompt": "x", "async": True}, format="json",
            )
        assert resp.status_code == 503

    def test_sync_path_unchanged_without_flag(self, user):
        _service_model(user, "image", "flux")
        with patch("apps.inference.openai_views.requests.post", return_value=_image_resp()):
            resp = _client(user).post(
                "/v1/images/generations",
                {"model": "flux", "prompt": "x"}, format="json",
            )
        assert resp.status_code == 200
        assert not InferenceRequest.objects.get().is_async

    def test_idempotency_key_dedupes(self, user):
        _service_model(user, "image", "flux")
        c = _client(user)
        headers = {"HTTP_IDEMPOTENCY_KEY": "abc-123"}
        r1 = c.post("/v1/images/generations",
                    {"model": "flux", "prompt": "x", "async": True}, format="json", **headers)
        r2 = c.post("/v1/images/generations",
                    {"model": "flux", "prompt": "y", "async": True}, format="json", **headers)
        assert r1.json()["id"] == r2.json()["id"]
        assert InferenceRequest.objects.count() == 1


# --- execution ---------------------------------------------------------------


class TestExecution:
    def test_queued_image_runs_and_stores(self, user):
        _service_model(user, "image", "flux")
        job = jobs.enqueue_job(user, "IMAGE", {"model": "flux", "prompt": "x", "n": 1})
        with patch("apps.inference.openai_views.requests.post", return_value=_image_resp()):
            ran = jobs.process_jobs_inline()
        assert ran == 1
        job.refresh_from_db()
        assert job.status == "PROCESSED"
        assert job.finished_at is not None
        assert job.image_count == 1

    def test_failure_retries_then_fails(self, user):
        _service_model(user, "image", "flux")
        job = jobs.enqueue_job(user, "IMAGE", {"model": "flux", "prompt": "x"}, max_attempts=2)
        # 5xx is transient → retried. Force run_after into the past each round.
        with patch("apps.inference.openai_views.requests.post",
                   return_value=_FakeResp({"error": "boom"}, status=503)):
            jobs.process_jobs_inline()
            job.refresh_from_db()
            assert job.status == "QUEUED" and job.attempts == 1  # backed off
            job.run_after = timezone.now() - timezone.timedelta(seconds=1)
            job.save(update_fields=["run_after"])
            jobs.process_jobs_inline()
        job.refresh_from_db()
        assert job.status == "FAILED" and job.attempts == 2

    def test_4xx_is_permanent_no_retry(self, user):
        _service_model(user, "image", "flux")
        job = jobs.enqueue_job(user, "IMAGE", {"model": "flux", "prompt": "x"}, max_attempts=3)
        with patch("apps.inference.openai_views.requests.post",
                   return_value=_FakeResp({"error": "bad"}, status=400)):
            jobs.process_jobs_inline()
        job.refresh_from_db()
        assert job.status == "FAILED" and job.attempts == 1


# --- capacity ----------------------------------------------------------------


class TestCapacity:
    def test_service_max_concurrent_one_dispatches_one(self, user):
        _service_model(user, "image", "flux", max_concurrent=1)
        j1 = jobs.enqueue_job(user, "IMAGE", {"model": "flux", "prompt": "a"})
        j2 = jobs.enqueue_job(user, "IMAGE", {"model": "flux", "prompt": "b"})
        claimed = jobs.dispatch_due_jobs()
        assert claimed == [j1.id]  # only one slot; j2 stays queued
        j2.refresh_from_db()
        assert j2.status == "QUEUED"

    def test_resource_group_serializes_two_services(self, user):
        # Two services (image + video) sharing one GPU group with budget 1.
        p = _provider(user)
        ResourceGroup.objects.create(provider=p, name="gpu0", max_concurrent=1)
        _service_model(user, "image", "flux", provider=p, max_concurrent=1, resource_group="gpu0")
        _service_model(user, "video", "ltx", provider=p, max_concurrent=1, resource_group="gpu0")
        img = jobs.enqueue_job(user, "IMAGE", {"model": "flux", "prompt": "a"})
        vid = jobs.enqueue_job(user, "VIDEO", {"model": "ltx", "prompt": "b"})
        claimed = jobs.dispatch_due_jobs()
        # Group budget is 1 → only one of the two starts even though each
        # service would individually allow one.
        assert len(claimed) == 1
        assert {img.id, vid.id} >= set(claimed)


# --- cancel ------------------------------------------------------------------


class TestCancel:
    def test_cancel_queued_job(self, user):
        _service_model(user, "image", "flux")
        job = jobs.enqueue_job(user, "IMAGE", {"model": "flux", "prompt": "x"})
        assert jobs.cancel_job(job) is True
        job.refresh_from_db()
        assert job.status == "CANCELED"
        # A canceled job is never dispatched.
        assert jobs.dispatch_due_jobs() == []


# --- batches -----------------------------------------------------------------


class TestBatches:
    def test_batch_submit_and_drain(self, user):
        _service_model(user, "image", "flux")
        resp = _client(user).post(
            "/v1/batches",
            {"label": "shots", "requests": [
                {"endpoint": "/v1/images/generations", "body": {"model": "flux", "prompt": "a"}},
                {"endpoint": "/v1/images/generations", "body": {"model": "flux", "prompt": "b"}},
            ]}, format="json",
        )
        assert resp.status_code == 202, resp.content
        batch = Batch.objects.get(id=resp.json()["id"])
        assert batch.jobs.count() == 2
        assert batch.aggregate_status() == "RUNNING"
        with patch("apps.inference.openai_views.requests.post", return_value=_image_resp()):
            jobs.process_jobs_inline()
        assert batch.aggregate_status() == "DONE"

    def test_batch_rejects_unsupported_endpoint(self, user):
        resp = _client(user).post(
            "/v1/batches",
            {"requests": [{"endpoint": "/v1/audio/transcriptions", "body": {}}]},
            format="json",
        )
        assert resp.status_code == 400


# --- workflows ---------------------------------------------------------------


class TestWorkflows:
    def test_fanout_map_creates_a_job_per_item(self, user):
        _service_model(user, "image", "flux")
        spec = {
            "name": "three images",
            "steps": [
                {"id": "prompts", "kind": "transform", "op": "passthrough",
                 "input": ["a sunset", "a forest", "a city"]},
                {"id": "imgs", "kind": "map", "type": "image",
                 "model": "flux", "over": "{{steps.prompts.output}}",
                 "body": {"prompt": "{{item}}"}},
            ],
        }
        run = workflows.start_run(user, spec)
        # The map step fanned out to 3 queued jobs.
        step = run.steps.get(step_id="imgs")
        assert step.jobs.count() == 3
        with patch("apps.inference.openai_views.requests.post", return_value=_image_resp()):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "DONE"
        step.refresh_from_db()
        assert step.status == "DONE"
        assert isinstance(step.output, list) and len(step.output) == 3

    def test_llm_then_map_passes_structured_output(self, user):
        # An LLM step emits JSON; a map step fans out over it.
        _service_model(user, "llm", "qwen")
        _service_model(user, "image", "flux")
        spec = {
            "steps": [
                {"id": "plan", "kind": "inference", "endpoint": "/v1/chat/completions",
                 "model": "qwen", "extract": "json",
                 "body": {"messages": [{"role": "user", "content": "plan"}]}},
                {"id": "imgs", "kind": "map", "type": "image", "model": "flux",
                 "over": "{{steps.plan.output.sections}}",
                 "body": {"prompt": "{{item.prompt}}"}},
            ],
        }
        run = workflows.start_run(user, spec)
        llm_json = json.dumps({"sections": [{"prompt": "p1"}, {"prompt": "p2"}]})
        chat = _FakeResp({"choices": [{"message": {"role": "assistant", "content": llm_json}}]})

        def _post(url, **kw):
            return chat if "chat/completions" in url else _image_resp()

        with patch("apps.inference.openai_views.requests.post", side_effect=_post):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "DONE"
        assert run.steps.get(step_id="imgs").jobs.count() == 2

    def test_human_gate_pauses_then_resumes(self, user):
        _service_model(user, "image", "flux")
        spec = {
            "steps": [
                {"id": "img", "kind": "inference", "type": "image", "model": "flux",
                 "body": {"prompt": "x"}},
                {"id": "review", "kind": "gate", "depends_on": ["img"]},
                {"id": "img2", "kind": "inference", "type": "image", "model": "flux",
                 "depends_on": ["review"], "body": {"prompt": "y"}},
            ],
        }
        run = workflows.start_run(user, spec)
        with patch("apps.inference.openai_views.requests.post", return_value=_image_resp()):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "AWAITING"
        assert run.steps.get(step_id="review").status == "AWAITING"
        # The downstream step hasn't started.
        assert run.steps.get(step_id="img2").status == "PENDING"
        # Approve the gate → the run resumes and finishes.
        ok, err = workflows.resolve_gate(run, "review", "approve")
        assert ok, err
        with patch("apps.inference.openai_views.requests.post", return_value=_image_resp()):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "DONE"

    def test_invalid_spec_rejected(self, user):
        resp = _client(user).post(
            "/v1/workflows/runs",
            {"spec": {"steps": [{"id": "a", "kind": "bogus"}]}}, format="json",
        )
        assert resp.status_code == 400

    def test_run_detail_exposes_dag(self, user):
        _service_model(user, "image", "flux")
        spec = {"steps": [
            {"id": "img", "kind": "inference", "type": "image", "model": "flux",
             "body": {"prompt": "x"}},
            {"id": "review", "kind": "gate", "depends_on": ["img"]},
        ]}
        run = workflows.start_run(user, spec)
        resp = _client(user).get(f"/v1/workflows/runs/{run.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert {s["step_id"] for s in data["steps"]} == {"img", "review"}
        assert {"from": "img", "to": "review"} in data["edges"]
