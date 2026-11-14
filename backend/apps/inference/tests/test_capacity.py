"""Device capacity: one budget shared by sync /v1 calls, async jobs, agent
tools and retries (capacity.py). Upstream is mocked."""
import io
import wave
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.inference import jobs
from apps.inference.models import (
    InferenceRequest, MediaAsset, Provider, ProviderModel, ProviderService, link_catalog_model,
)

User = get_user_model()


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.ASYNC_ENABLED = True
    settings.SYNC_CAPACITY_WAIT_SECONDS = 0  # don't sleep in tests
    settings.SYNC_CAPACITY_POLL_SECONDS = 0.01


@pytest.fixture
def user(db):
    return User.objects.create_user(email="cap@example.com", password="x")


def _wav(seconds=0.5, rate=8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


def _model(u, *, stype="music", name="acestep", online=True, max_concurrent=1):
    p = Provider.objects.create(
        user=u, name=f"node-{stype}", tailnet_hostname=f"n-{stype}",
        is_active=True, accepting_requests=True,
        last_seen_at=timezone.now() if online else timezone.now() - timezone.timedelta(days=1),
    )
    svc = ProviderService.objects.create(
        provider=p, name=f"svc-{stype}", engine="other", service_type=stype,
        access_policy=ProviderService.ACCESS_AUTHENTICATED, max_concurrent=max_concurrent,
    )
    pm = ProviderModel(provider=p, name=name, service=svc)
    link_catalog_model(pm)
    pm.save()
    return pm


def _client(u):
    from rest_framework.test import APIClient
    c = APIClient()
    c.force_authenticate(user=u)
    return c


class _Resp:
    def __init__(self, content, status=200, ct="audio/wav"):
        self.content = content
        self.status_code = status
        self.ok = 200 <= status < 300
        self.headers = {"content-type": ct}
        self.text = ""

    def json(self):
        import json
        return json.loads(self.content)


def _busy(pm, *, is_async=True, started=None):
    """An in-flight request occupying pm's device."""
    return InferenceRequest.objects.create(
        user=pm.provider.user, provider=pm.provider, model_name="acestep",
        inference_type="MUSIC", status="PROCESSING", is_async=is_async,
        job_service_type=pm.service.service_type, started_at=started or timezone.now(),
        payload={"prompt": "x"},
    )


def _music(c, **extra):
    return c.post("/v1/music/generations", {"model": "acestep", "prompt": "lofi", **extra},
                  format="json")


class TestSyncGate:
    def test_free_device_runs_and_records_slot(self, user):
        _model(user)
        with patch("apps.inference.openai_views.requests.post", return_value=_Resp(_wav())):
            resp = _music(_client(user))
        assert resp.status_code == 200
        ir = InferenceRequest.objects.get(inference_type="MUSIC")
        assert ir.status == "PROCESSED"
        assert ir.job_service_type == "music"
        assert ir.started_at is not None
        # byte mode names the request + stored asset
        assert resp["X-Inference-Request-Id"] == str(ir.id)
        assert resp["X-Asset-Id"]

    def test_busy_device_rejects_with_retry_after(self, user):
        pm = _model(user)
        _busy(pm)
        with patch("apps.inference.openai_views.requests.post") as up:
            resp = _music(_client(user))
        assert resp.status_code == 429
        assert resp.json()["error"]["type"] == "at_capacity"
        assert int(resp["Retry-After"]) >= 5
        up.assert_not_called()  # the GPU never saw it

    def test_sync_busy_counts_too(self, user):
        from apps.inference import capacity

        pm = _model(user)
        row = _busy(pm, is_async=False)
        lease = capacity.start_lease(row.id)  # a live sync request holds a lease
        try:
            with patch("apps.inference.openai_views.requests.post") as up:
                resp = _music(_client(user))
        finally:
            if lease:
                lease.stop()
        assert resp.status_code == 429
        up.assert_not_called()

    def test_stale_sync_slot_is_ignored(self, user):
        pm = _model(user)
        _busy(pm, is_async=False, started=timezone.now() - timezone.timedelta(hours=2))
        with patch("apps.inference.openai_views.requests.post", return_value=_Resp(_wav())):
            resp = _music(_client(user))
        assert resp.status_code == 200

    def test_max_concurrent_two_allows_second(self, user):
        pm = _model(user, max_concurrent=2)
        _busy(pm)
        with patch("apps.inference.openai_views.requests.post", return_value=_Resp(_wav())):
            assert _music(_client(user)).status_code == 200

    def test_resource_group_shared_between_services(self, user):
        from apps.inference.models import ResourceGroup

        music = _model(user)
        # a TTS service on the SAME provider sharing one GPU group
        tts_svc = ProviderService.objects.create(
            provider=music.provider, name="tts", engine="other", service_type="tts",
            access_policy=ProviderService.ACCESS_AUTHENTICATED, max_concurrent=4,
            resource_group="gpu0",
        )
        music.service.resource_group = "gpu0"
        music.service.max_concurrent = 4
        music.service.save()
        ResourceGroup.objects.create(provider=music.provider, name="gpu0", max_concurrent=1)
        InferenceRequest.objects.create(
            user=user, provider=music.provider, model_name="kokoro", inference_type="TTS",
            status="PROCESSING", is_async=True, job_service_type="tts", payload={},
        )
        assert tts_svc.id
        with patch("apps.inference.openai_views.requests.post") as up:
            resp = _music(_client(user))
        assert resp.status_code == 429
        up.assert_not_called()

    def test_abandoned_slot_released_when_view_crashes(self, user):
        _model(user)
        with patch("apps.inference.openai_views.requests.post", side_effect=RuntimeError("boom")):
            c = _client(user)
            c.raise_request_exception = False
            _music(c)
        ir = InferenceRequest.objects.get(inference_type="MUSIC")
        assert ir.status != "PROCESSING"


class TestAutoMode:
    def test_auto_busy_queues_job(self, user):
        pm = _model(user)
        _busy(pm)
        with patch("apps.inference.openai_views.requests.post") as up, \
                patch("apps.inference.jobs.kick_dispatch"):
            resp = _music(_client(user), **{"async": "auto"})
        assert resp.status_code == 202
        body = resp.json()
        assert body["queued_reason"] == "at_capacity"
        assert body["poll_url"] == f"/v1/jobs/{body['id']}"
        assert InferenceRequest.objects.get(id=body["id"]).status == "QUEUED"
        up.assert_not_called()

    def test_auto_free_runs_inline(self, user):
        _model(user)
        with patch("apps.inference.openai_views.requests.post", return_value=_Resp(_wav())):
            resp = _music(_client(user), **{"async": "auto", "delivery": "url"})
        assert resp.status_code == 200
        d = resp.json()
        assert d["object"] == "inference.result"
        assert d["data"][0]["kind"] == "audio"
        assert d["data"][0]["url"]

    def test_auto_offline_provider_queues(self, user):
        _model(user, online=False)
        with patch("apps.inference.jobs.kick_dispatch"):
            resp = _music(_client(user), **{"async": "auto"})
        assert resp.status_code == 202
        assert resp.json()["queued_reason"] == "no_provider"

    def test_auto_unknown_model_still_404(self, user):
        _model(user, online=False)
        resp = _client(user).post(
            "/v1/music/generations", {"model": "nope", "prompt": "x", "async": "auto"},
            format="json",
        )
        assert resp.status_code == 404

    def test_auto_joins_back_of_line(self, user):
        pm = _model(user)
        jobs.enqueue_job(user, "MUSIC", {"model": "acestep", "prompt": "first"},
                         model_name="acestep")
        assert pm
        with patch("apps.inference.openai_views.requests.post") as up, \
                patch("apps.inference.jobs.kick_dispatch"):
            resp = _music(_client(user), **{"async": "auto"})
        assert resp.status_code == 202
        up.assert_not_called()


class TestDispatcherSharesLedger:
    def test_async_job_waits_for_sync_slot(self, user):
        from apps.inference import capacity

        pm = _model(user)
        sync_row = _busy(pm, is_async=False)
        lease = capacity.start_lease(sync_row.id)
        job = jobs.enqueue_job(user, "MUSIC", {"model": "acestep", "prompt": "x"},
                               model_name="acestep")
        assert jobs.dispatch_due_jobs() == []
        if lease:
            lease.stop()
        sync_row.status = "PROCESSED"
        sync_row.save()
        assert jobs.dispatch_due_jobs() == [job.id]

    def test_llm_jobs_respect_max_concurrent(self, user):
        pm = _model(user, stype="llm", name="qwen")
        InferenceRequest.objects.create(
            user=user, provider=pm.provider, model_name="qwen", inference_type="LLM",
            status="PROCESSING", is_async=True, job_service_type="", payload={},
        )
        jobs.enqueue_job(user, "LLM", {"model": "qwen", "messages": []}, model_name="qwen")
        assert jobs.dispatch_due_jobs() == []  # "" (job) ≡ "llm" (service)


class TestJobResultAndCapacityEndpoint:
    def test_job_exposes_output_text_and_media(self, user):
        ir = InferenceRequest.objects.create(
            user=user, model_name="qwen", inference_type="LLM", status="PROCESSED",
            is_async=True, payload={},
            results={"choices": [{"message": {"role": "assistant", "content": "x" * 5000}}]},
        )
        d = _client(user).get(f"/v1/jobs/{ir.id}").json()
        assert d["output_text"] == "x" * 5000
        assert d["media"] == []

    def test_job_media_items(self, user):
        from django.core.files.base import ContentFile

        ir = InferenceRequest.objects.create(
            user=user, model_name="acestep", inference_type="MUSIC", status="PROCESSED",
            is_async=True, payload={},
        )
        a = MediaAsset(user=user, inference_request=ir, kind=MediaAsset.OUTPUT_AUDIO,
                       content_type="audio/wav", size_bytes=4)
        a.file.save("x.wav", ContentFile(b"RIFF"), save=False)
        a.save()
        d = _client(user).get(f"/v1/jobs/{ir.id}").json()
        assert d["media"][0]["kind"] == "audio"
        assert d["media"][0]["id"] == a.id

    def test_capacity_endpoint(self, user):
        pm = _model(user)
        _busy(pm)
        d = _client(user).get("/v1/capacity").json()
        row = next(r for r in d["data"] if r["service_type"] == "music")
        assert row["in_flight"] == 1
        assert row["max_concurrent"] == 1
        assert row["available"] is False


class TestLeases:
    """With a shared cache, a sync slot only counts while its owner heartbeats —
    a worker that died mid-request frees the device within LEASE_TTL."""

    def test_dead_sync_slot_does_not_block(self, user, settings):
        settings.CAPACITY_FORCE_LEASES = True
        pm = _model(user)
        _busy(pm, is_async=False)  # PROCESSING row, but no live lease (owner died)
        with patch("apps.inference.openai_views.requests.post", return_value=_Resp(_wav())):
            assert _music(_client(user)).status_code == 200

    def test_live_lease_blocks_then_releases(self, user, settings):
        from apps.inference import capacity

        settings.CAPACITY_FORCE_LEASES = True
        pm = _model(user)
        row = _busy(pm, is_async=False)
        lease = capacity.start_lease(row.id)
        try:
            with patch("apps.inference.openai_views.requests.post") as up:
                assert _music(_client(user)).status_code == 429
            up.assert_not_called()
        finally:
            lease.stop()
        with patch("apps.inference.openai_views.requests.post", return_value=_Resp(_wav())):
            assert _music(_client(user)).status_code == 200

    def test_view_lease_is_released_after_request(self, user, settings):
        from django.core.cache import cache

        from apps.inference import capacity

        settings.CAPACITY_FORCE_LEASES = True
        _model(user)
        with patch("apps.inference.openai_views.requests.post", return_value=_Resp(_wav())):
            assert _music(_client(user)).status_code == 200
        ir = InferenceRequest.objects.get(inference_type="MUSIC")
        assert cache.get(capacity._lease_key(ir.id)) is None
