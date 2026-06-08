"""Music generation: the /v1/music/generations proxy (text → song). The agent
hides ACE-Step's async submit/poll/download behind one reply, so from the
backend's view it's a single forward that returns audio bytes — like TTS. We
mock the agent's reply: service-type routing, public output audio, the forwarded
ACE-Step request shape, and control clamping. Upstream is mocked.
"""
import io
import wave
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.inference.models import (
    InferenceRequest, MediaAsset, Provider, ProviderModel, ProviderService, link_catalog_model,
)
from apps.inference.openai_views import _find_provider_for_model

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
    return User.objects.create_user(email="music@example.com", password="x")


def _music_model(u, name="acestep-v15-turbo"):
    p = Provider.objects.create(
        user=u, name="node", tailnet_hostname="n1",
        is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
    )
    svc = ProviderService.objects.create(
        provider=p, name="ace-step", engine="other", service_type="music",
        access_policy=ProviderService.ACCESS_AUTHENTICATED,
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


class _FakeAudioResp:
    def __init__(self, content, status=200, content_type="audio/wav"):
        self.content = content
        self.status_code = status
        self.ok = 200 <= status < 300
        self.headers = {"content-type": content_type}
        self.text = ""

    def json(self):
        import json
        return json.loads(self.content)


# --- routing ---------------------------------------------------------------


class TestMusicRouting:
    def test_music_request_only_matches_music(self, user):
        _music_model(user)
        assert _find_provider_for_model(user, "acestep-v15-turbo", service_type="music") is not None
        assert _find_provider_for_model(user, "acestep-v15-turbo", service_type="tts") is None


# --- /v1/music/generations -------------------------------------------------


class TestMusicGenerations:
    def test_happy_path_returns_audio_and_stores(self, user):
        _music_model(user)
        wav = _tiny_wav(1.0)
        with patch("apps.inference.openai_views.requests.post", return_value=_FakeAudioResp(wav)):
            resp = _client(user).post(
                "/v1/music/generations",
                {"model": "acestep-v15-turbo", "prompt": "lofi hip hop, chill"},
                format="json",
            )
        assert resp.status_code == 200
        assert resp["content-type"] == "audio/wav"
        assert resp.content == wav
        ir = InferenceRequest.objects.get(user=user, inference_type="MUSIC")
        assert ir.status == "PROCESSED"
        assert ir.audio_seconds == pytest.approx(1.0, abs=0.01)
        assert MediaAsset.objects.filter(user=user, kind="OUTPUT_AUDIO").count() == 1

    def test_forwards_acestep_fields_and_clamps(self, user):
        _music_model(user)
        captured = {}

        def _cap(url, **kw):
            captured["url"] = url
            captured["json"] = kw.get("json")
            return _FakeAudioResp(_tiny_wav())

        with patch("apps.inference.openai_views.requests.post", side_effect=_cap):
            _client(user).post(
                "/v1/music/generations",
                {
                    "model": "acestep-v15-turbo",
                    "prompt": "uplifting synthwave",
                    "lyrics": "[verse] hello",
                    "audio_duration": 9000,  # clamped to 300
                    "inference_steps": 999,  # clamped to 200
                    "seed": 42,
                    "use_random_seed": False,
                    "audio_format": "wav",
                    "bpm": 120,
                },
                format="json",
            )
        body = captured["json"]
        assert captured["url"].endswith("/music/generations")
        assert body["model"] == "acestep-v15-turbo"
        assert body["prompt"] == "uplifting synthwave"
        assert body["lyrics"] == "[verse] hello"
        assert body["task_type"] == "text2music"
        assert body["audio_duration"] == 300  # clamped
        assert body["inference_steps"] == 200  # clamped
        assert body["seed"] == 42
        assert body["use_random_seed"] is False
        assert body["bpm"] == 120

    def test_unknown_format_falls_back_to_mp3(self, user):
        _music_model(user)
        captured = {}

        def _cap(url, **kw):
            captured["json"] = kw.get("json")
            return _FakeAudioResp(_tiny_wav(), content_type="audio/mpeg")

        with patch("apps.inference.openai_views.requests.post", side_effect=_cap):
            _client(user).post(
                "/v1/music/generations",
                {"model": "acestep-v15-turbo", "prompt": "jazz", "audio_format": "bogus"},
                format="json",
            )
        assert captured["json"]["audio_format"] == "mp3"

    def test_missing_prompt_400(self, user):
        _music_model(user)
        resp = _client(user).post(
            "/v1/music/generations", {"model": "acestep-v15-turbo"}, format="json"
        )
        assert resp.status_code == 400

    def test_no_music_provider_404(self, user):
        resp = _client(user).post(
            "/v1/music/generations", {"model": "nope", "prompt": "hi"}, format="json"
        )
        assert resp.status_code == 404

    def test_upstream_error_passthrough(self, user):
        _music_model(user)
        err = b'{"error": "boom"}'
        with patch(
            "apps.inference.openai_views.requests.post",
            return_value=_FakeAudioResp(err, status=502, content_type="application/json"),
        ):
            resp = _client(user).post(
                "/v1/music/generations",
                {"model": "acestep-v15-turbo", "prompt": "x"},
                format="json",
            )
        assert resp.status_code == 502


# --- public output audio ---------------------------------------------------


class TestPublicOutputAudio:
    def test_output_audio_public(self, user):
        from rest_framework.test import APIClient
        _music_model(user)
        with patch("apps.inference.openai_views.requests.post", return_value=_FakeAudioResp(_tiny_wav())):
            _client(user).post(
                "/v1/music/generations",
                {"model": "acestep-v15-turbo", "prompt": "ambient"},
                format="json",
            )
        asset = MediaAsset.objects.get(user=user, kind="OUTPUT_AUDIO")
        # Anonymous can fetch a generated song (public by URL).
        resp = APIClient().get(f"/api/inference/assets/{asset.id}/")
        assert resp.status_code == 200
