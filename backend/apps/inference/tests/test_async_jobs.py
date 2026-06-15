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

    def test_auto_resolves_model_when_step_omits_it(self, user):
        # A portable template step omits `model`; the engine fills in the
        # user's available image model at run time.
        _service_model(user, "image", "flux")
        spec = {"steps": [
            {"id": "img", "kind": "inference", "type": "image", "body": {"prompt": "x"}},
        ]}
        run = workflows.start_run(user, spec)
        job = run.steps.get(step_id="img").jobs.first()
        assert job is not None
        assert job.model_name  # resolved, not blank
        with patch("apps.inference.openai_views.requests.post", return_value=_image_resp()):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "DONE"

    def test_start_run_from_template(self, user):
        # image-variations chains chat → image, so the user needs a provider for
        # both modalities or preflight (PRD 12 graceful-fail) rejects the run.
        _service_model(user, "llm", "qwen")
        _service_model(user, "image", "flux")
        resp = _client(user).post(
            "/v1/workflows/runs",
            {"template": "image-variations",
             "inputs": {"subject": "a teapot", "count": 2}}, format="json",
        )
        assert resp.status_code == 202, resp.content
        data = resp.json()
        # The chat→image fan-out DAG was created from the template.
        assert {s["step_id"] for s in data["steps"]} == {"prompts", "images"}

    def test_storyboard_conditions_video_on_frames(self, user):
        # Regression: the clips step must animate each *generated frame*
        # (image-to-video) at the chosen square size — not blind text-to-video.
        _service_model(user, "llm", "qwen")
        _service_model(user, "image", "flux")
        _service_model(user, "video", "ltx")
        resp = _client(user).post(
            "/v1/workflows/runs",
            {"template": "storyboard-to-video",
             "inputs": {"concept": "a sprout", "shots": 2, "size": 640}}, format="json",
        )
        assert resp.status_code == 202, resp.content
        run = WorkflowRun.objects.get(id=resp.json()["id"])
        shots = json.dumps({"shots": [
            {"image_prompt": "p1", "motion": "m1"},
            {"image_prompt": "p2", "motion": "m2"}]})
        chat = _FakeResp({"choices": [{"message": {"role": "assistant", "content": shots}}]})

        def _post(url, **kw):
            if "chat/completions" in url:
                return chat
            if "images/generations" in url:
                return _image_resp()
            if "videos/generations" in url:
                return _FakeResp(b"\x00mp4bytes", content_type="video/mp4")
            return _FakeResp({})

        with patch("apps.inference.openai_views.requests.post", side_effect=_post):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "AWAITING"  # paused at the frame-review gate
        ok, err = workflows.resolve_gate(run, "review", "approve")
        assert ok, err
        with patch("apps.inference.openai_views.requests.post", side_effect=_post):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "DONE"

        clips = list(run.steps.get(step_id="clips").jobs.all())
        assert len(clips) == 2
        for v in clips:
            # Each clip is image-conditioned on its frame, at the square size.
            assert v.payload.get("has_image") is True
            assert v.payload.get("width") == 640 and v.payload.get("height") == 640
            assert v.assets.filter(kind="INPUT_IMAGE").exists()

    def test_template_missing_required_input_400(self, user):
        resp = _client(user).post(
            "/v1/workflows/runs",
            {"template": "illustrated-story", "inputs": {}}, format="json",
        )
        assert resp.status_code == 400

    def test_templates_list_endpoint(self, user):
        resp = _client(user).get("/v1/workflows/templates")
        assert resp.status_code == 200
        keys = {t["key"] for t in resp.json()["data"]}
        assert "illustrated-story" in keys and "song-and-cover" in keys
        # Each template advertises a renderable input schema.
        for tpl in resp.json()["data"]:
            assert isinstance(tpl["inputs"], list)

    def test_queue_summary_reports_dispatcher_health(self, user):
        _service_model(user, "image", "flux")
        jobs.enqueue_job(user, "IMAGE", {"model": "flux", "prompt": "x"})
        resp = _client(user).get("/api/inference/queue/summary/")
        assert resp.status_code == 200
        body = resp.json()
        assert "worker_stalled" in body and "async_enabled" in body

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


# --- URL → video, full graph (PRD 12) ----------------------------------------


def _real_png_b64():
    """Base64 of a real, properly-sized PNG. A 1x1 PNG (like _image_resp) makes
    the compose ffmpeg pass hang, so the end-to-end test needs a real image —
    exactly what the IMAGE modality produces in practice."""
    import base64
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (96, 96), (30, 90, 150)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _wav_bytes(seconds=0.3, rate=8000):
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


class TestUrlToVideoEndToEnd:
    """The whole hn.fm flow as one inference.club workflow: scrape → dialog →
    split → tts + image fan-out → (gate) → compose. Upstream providers are
    mocked; compose runs real FFmpeg centrally; the result is a captioned MP4
    that traces back to its section assets (PRD 12)."""

    def _post_factory(self, img_b64, wav, dialog):
        def _post(url, **kw):
            if "/scrape" in url:
                return _FakeResp(
                    b"# Lighthouses\n\nThey guide ships home.",
                    content_type="text/markdown",
                    headers={"X-Scrape-Title": "Lighthouses"},
                )
            if "chat/completions" in url:
                return _FakeResp(
                    {"choices": [{"message": {"role": "assistant", "content": dialog}}]}
                )
            if "audio/synthesize" in url:
                return _FakeResp(wav, content_type="audio/wav")
            if "images/generations" in url:
                return _FakeResp({"created": 1, "data": [{"b64_json": img_b64}]})
            return _FakeResp({})
        return _post

    def test_url_to_video_renders_a_captioned_mp4_with_provenance(self, user):
        from apps.inference.models import MediaAsset

        # A provider for every modality the template needs (compose/RENDER is
        # central and needs none).
        _service_model(user, "scrape", "firecrawl")
        _service_model(user, "llm", "qwen")
        _service_model(user, "tts", "dia")
        _service_model(user, "image", "flux")

        dialog = ("[S1] Welcome to the show.\n[S2] Today: lighthouses.\n"
                  "[S1] They guide ships home.\n[S2] A beacon in the dark.")
        _post = self._post_factory(_real_png_b64(), _wav_bytes(), dialog)

        resp = _client(user).post(
            "/v1/workflows/runs",
            {"template": "url-to-video", "inputs": {"url": "https://example.com/x"}},
            format="json",
        )
        assert resp.status_code == 202, resp.content
        run = WorkflowRun.objects.get(id=resp.json()["id"])

        with patch("apps.inference.openai_views.requests.post", side_effect=_post):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "AWAITING"  # paused at the review gate

        ok, err = workflows.resolve_gate(run, "review", "approve")
        assert ok, err
        with patch("apps.inference.openai_views.requests.post", side_effect=_post):
            jobs.process_jobs_inline()
        run.refresh_from_db()
        assert run.status == "DONE", run.steps.filter(status="FAILED").values("step_id", "error")

        # Two sections (4 dialog lines / 2) → two narrated, illustrated clips.
        assert run.steps.get(step_id="speech").jobs.count() == 2
        assert run.steps.get(step_id="art").jobs.count() == 2

        # The compose step produced one real MP4, captioned, tracing back to
        # every section's audio + image.
        vid_job = run.steps.get(step_id="video").jobs.get()
        vid = vid_job.assets.get(kind=MediaAsset.OUTPUT_VIDEO)
        assert vid.size_bytes > 0 and vid.duration_seconds and vid.duration_seconds > 0
        assert vid.metadata.get("captions") is True
        assert vid.metadata.get("sections") == 2
        assert vid.derived_from.filter(kind=MediaAsset.OUTPUT_AUDIO).count() == 2
        assert vid.derived_from.filter(kind=MediaAsset.OUTPUT_IMAGE).count() == 2

    def test_url_to_video_fails_fast_without_providers(self, user):
        # No providers online → preflight rejects the run up front (409), before
        # any job runs, and names every missing service (PRD 12 graceful-fail).
        resp = _client(user).post(
            "/v1/workflows/runs",
            {"template": "url-to-video", "inputs": {"url": "https://example.com/x"}},
            format="json",
        )
        assert resp.status_code == 409, resp.content
        err = resp.json()["error"]
        assert err["type"] == "services_unavailable"
        assert set(err["missing"]) == {
            "web scraping", "chat / LLM", "text-to-speech", "image generation",
        }
        assert WorkflowRun.objects.count() == 0
