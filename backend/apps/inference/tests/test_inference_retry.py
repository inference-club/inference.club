"""Retry a failed inference request in place: ownership, state guards, and the
re-run of representative modalities (JSON payload: music/image; file input:
mesh; missing-input: stt). Upstream is mocked.
"""
import base64
import io
import json
import wave
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.inference.models import (
    InferenceRequest, MediaAsset, Provider, ProviderModel, ProviderService, link_catalog_model,
)

User = get_user_model()


def _tiny_wav(seconds=1.0, rate=8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="retry@example.com", password="x")


def _model(u, service_type, name):
    p = Provider.objects.create(
        user=u, name="node", tailnet_hostname="n1",
        is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
    )
    svc = ProviderService.objects.create(
        provider=p, name=f"{service_type}-svc", engine="other", service_type=service_type,
        access_policy=ProviderService.ACCESS_AUTHENTICATED,
    )
    pm = ProviderModel(provider=p, name=name, service=svc)
    link_catalog_model(pm)
    pm.save()
    return p, pm


def _failed_request(u, provider, itype, model_name, payload):
    return InferenceRequest.objects.create(
        user=u, provider=provider, model_name=model_name, inference_type=itype,
        payload=payload, status="REQUESTED", results={"error": "boom"},
    )


def _client(u):
    from rest_framework.test import APIClient
    c = APIClient()
    c.force_authenticate(user=u)
    return c


class _FakeResp:
    def __init__(self, content=b"", status=200, content_type="application/json", headers=None):
        self.content = content
        self.status_code = status
        self.ok = 200 <= status < 300
        self.headers = {"content-type": content_type, **(headers or {})}
        self.text = content.decode(errors="replace") if isinstance(content, bytes) else str(content)

    def json(self):
        return json.loads(self.content)


def _url(ir):
    return f"/api/inference/requests/{ir.id}/retry/"


# --- guards ----------------------------------------------------------------


class TestRetryGuards:
    def test_only_owner_can_retry(self, user):
        other = User.objects.create_user(email="other@example.com", password="x")
        p, _ = _model(user, "music", "acestep-v15-turbo")
        ir = _failed_request(user, p, "MUSIC", "acestep-v15-turbo", {"prompt": "x"})
        assert _client(other).post(_url(ir)).status_code == 403

    def test_cannot_retry_succeeded(self, user):
        p, _ = _model(user, "music", "acestep-v15-turbo")
        ir = _failed_request(user, p, "MUSIC", "acestep-v15-turbo", {"prompt": "x"})
        ir.status = "PROCESSED"
        ir.save(update_fields=["status"])
        assert _client(user).post(_url(ir)).status_code == 409

    def test_missing_request_404(self, user):
        assert _client(user).post("/api/inference/requests/999999/retry/").status_code == 404


# --- re-runs ---------------------------------------------------------------


class TestRetryReruns:
    def test_music_rerun_succeeds_in_place(self, user):
        p, _ = _model(user, "music", "acestep-v15-turbo")
        ir = _failed_request(
            user, p, "MUSIC", "acestep-v15-turbo",
            {"model": "acestep-v15-turbo", "prompt": "lofi", "lyrics": "",
             "audio_format": "wav", "audio_duration": 30, "inference_steps": 8,
             "guidance_scale": 7.0, "seed": -1, "use_random_seed": True},
        )
        wav = _tiny_wav(1.0)
        with patch("apps.inference.openai_views.requests.post",
                   return_value=_FakeResp(wav, content_type="audio/wav")):
            resp = _client(user).post(_url(ir))
        assert resp.status_code == 200
        ir.refresh_from_db()
        assert ir.status == "PROCESSED"
        assert ir.id == resp.json()["id"]  # same row — in place
        assert MediaAsset.objects.filter(inference_request=ir, kind="OUTPUT_AUDIO").count() == 1

    def test_music_rerun_forwards_stored_params(self, user):
        p, _ = _model(user, "music", "acestep-v15-turbo")
        ir = _failed_request(
            user, p, "MUSIC", "acestep-v15-turbo",
            {"model": "acestep-v15-turbo", "prompt": "reggae", "lyrics": "[verse] hi",
             "audio_format": "wav", "audio_duration": 45, "inference_steps": 12,
             "guidance_scale": 6.0, "seed": 7, "use_random_seed": False, "bpm": 90},
        )
        captured = {}

        def _cap(url, **kw):
            captured["url"] = url
            captured["json"] = kw.get("json")
            return _FakeResp(_tiny_wav(), content_type="audio/wav")

        with patch("apps.inference.openai_views.requests.post", side_effect=_cap):
            assert _client(user).post(_url(ir)).status_code == 200
        body = captured["json"]
        assert captured["url"].endswith("/music/generations")
        assert body["prompt"] == "reggae"
        assert body["lyrics"] == "[verse] hi"
        assert body["audio_duration"] == 45
        assert body["inference_steps"] == 12
        assert body["seed"] == 7 and body["use_random_seed"] is False
        assert body["bpm"] == 90

    def test_image_rerun_stores_output(self, user):
        p, _ = _model(user, "image", "flux")
        ir = _failed_request(
            user, p, "IMAGE", "flux",
            {"model": "flux", "prompt": "a cat", "n": 1, "response_format": "url"},
        )
        png = base64.b64encode(b"fakepng").decode()
        body = json.dumps({"created": 1, "data": [{"b64_json": png}]}).encode()
        with patch("apps.inference.openai_views.requests.post",
                   return_value=_FakeResp(body, content_type="application/json")):
            resp = _client(user).post(_url(ir))
        assert resp.status_code == 200
        ir.refresh_from_db()
        assert ir.status == "PROCESSED"
        assert ir.image_count == 1
        assert MediaAsset.objects.filter(inference_request=ir, kind="OUTPUT_IMAGE").count() == 1

    def test_mesh_rerun_uses_stored_input_image(self, user):
        p, _ = _model(user, "mesh", "trellis-2")
        ir = _failed_request(
            user, p, "MESH", "trellis-2",
            {"model": "trellis-2", "options": {"resolution": "512"}, "source_filename": "in.png"},
        )
        # Stored source image (kept across the retry).
        src = MediaAsset(user=user, inference_request=ir, kind=MediaAsset.INPUT_IMAGE,
                         content_type="image/png", size_bytes=7)
        src.file.save("in.png", ContentFile(b"fakepng"), save=False)
        src.save()
        glb = b"glTF-bytes"
        with patch("apps.inference.openai_views.requests.post",
                   return_value=_FakeResp(glb, content_type="model/gltf-binary",
                                          headers={"X-Trellis-Metadata": json.dumps({"vertices": 10})})):
            resp = _client(user).post(_url(ir))
        assert resp.status_code == 200
        ir.refresh_from_db()
        assert ir.status == "PROCESSED"
        assert MediaAsset.objects.filter(inference_request=ir, kind="OUTPUT_MODEL").count() == 1
        # Input image preserved.
        assert MediaAsset.objects.filter(inference_request=ir, kind="INPUT_IMAGE").count() == 1

    def test_stt_without_stored_audio_fails_clean(self, user):
        p, _ = _model(user, "stt", "whisper")
        ir = _failed_request(user, p, "STT", "whisper", {"model": "whisper"})
        resp = _client(user).post(_url(ir))
        assert resp.status_code == 502
        ir.refresh_from_db()
        assert ir.status == "REQUESTED"
        assert "wasn't stored" in (ir.results or {}).get("error", "")

    def test_rerun_no_provider_online(self, user):
        # A failed request whose model no longer has any online provider.
        p, _ = _model(user, "music", "acestep-v15-turbo")
        ir = _failed_request(user, p, "MUSIC", "gone-model", {"model": "gone-model", "prompt": "x"})
        resp = _client(user).post(_url(ir))
        assert resp.status_code == 502
        ir.refresh_from_db()
        assert ir.status == "REQUESTED"
