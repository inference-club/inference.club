"""Text-to-speech: the OpenAI-compatible /v1/audio/speech proxy (adapting to
Riva's synthesize), the /v1/audio/voices helper, service-type routing, public
output audio, and WAV-duration metering. Upstream is mocked.
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
from apps.inference.openai_views import _find_provider_for_model, _flatten_voices, _riva_encoding

User = get_user_model()


def _tiny_wav(seconds=0.5, rate=8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="tts@example.com", password="x")


def _tts_model(u, name="magpie"):
    p = Provider.objects.create(
        user=u, name="node", tailnet_hostname="n1",
        is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
    )
    svc = ProviderService.objects.create(
        provider=p, name="riva", engine="other", service_type="tts",
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

    def raise_for_status(self):
        if not self.ok:
            raise Exception("http error")


# --- pure helpers ----------------------------------------------------------


class TestHelpers:
    def test_flatten_voices_nested(self):
        data = {"en-US,es-US": {"voices": ["A", "B"]}, "de-DE": {"voices": ["C", "A"]}}
        assert _flatten_voices(data) == ["A", "B", "C"]

    def test_riva_encoding_defaults_wav(self):
        assert _riva_encoding(None) == ("LINEAR_PCM", "audio/wav", "wav")
        assert _riva_encoding("mp3") == ("LINEAR_PCM", "audio/wav", "wav")
        assert _riva_encoding("opus")[0] == "OGGOPUS"


# --- routing ---------------------------------------------------------------


class TestTtsRouting:
    def test_tts_request_only_matches_tts(self, user):
        _tts_model(user, "magpie")
        assert _find_provider_for_model(user, "magpie", service_type="tts") is not None
        assert _find_provider_for_model(user, "magpie", service_type="stt") is None


# --- /v1/audio/speech ------------------------------------------------------


class TestAudioSpeech:
    def test_happy_path_returns_audio_and_stores(self, user):
        _tts_model(user)
        wav = _tiny_wav(0.5)
        with patch("apps.inference.openai_views.requests.post", return_value=_FakeAudioResp(wav)):
            resp = _client(user).post(
                "/v1/audio/speech",
                {"model": "magpie", "input": "hello world"},
                format="json",
            )
        assert resp.status_code == 200
        assert resp["content-type"] == "audio/wav"
        assert resp.content == wav
        ir = InferenceRequest.objects.get(user=user, inference_type="TTS")
        assert ir.status == "PROCESSED"
        assert ir.audio_seconds == pytest.approx(0.5, abs=0.01)
        assert MediaAsset.objects.filter(user=user, kind="OUTPUT_AUDIO").count() == 1

    def test_forwards_riva_fields(self, user):
        _tts_model(user)
        captured = {}

        def _cap(url, **kw):
            captured["url"] = url
            captured["files"] = {k: v[1] for k, v in (kw.get("files") or {}).items()}
            return _FakeAudioResp(_tiny_wav())

        with patch("apps.inference.openai_views.requests.post", side_effect=_cap):
            _client(user).post(
                "/v1/audio/speech",
                {"model": "magpie", "input": "hi", "voice": "Magpie-Multilingual.EN-US.Jason"},
                format="json",
            )
        assert captured["url"].endswith("/audio/synthesize")
        assert captured["files"]["text"] == "hi"
        assert captured["files"]["voice"] == "Magpie-Multilingual.EN-US.Jason"
        assert captured["files"]["encoding"] == "LINEAR_PCM"

    def test_default_voice_when_omitted(self, user, settings):
        settings.TTS_DEFAULT_VOICE = "Default.Voice"
        _tts_model(user)
        captured = {}

        def _cap(url, **kw):
            captured["files"] = {k: v[1] for k, v in (kw.get("files") or {}).items()}
            return _FakeAudioResp(_tiny_wav())

        with patch("apps.inference.openai_views.requests.post", side_effect=_cap):
            _client(user).post("/v1/audio/speech", {"model": "magpie", "input": "hi"}, format="json")
        assert captured["files"]["voice"] == "Default.Voice"

    def test_missing_input_400(self, user):
        _tts_model(user)
        resp = _client(user).post("/v1/audio/speech", {"model": "magpie"}, format="json")
        assert resp.status_code == 400

    def test_no_tts_provider_404(self, user):
        resp = _client(user).post("/v1/audio/speech", {"model": "nope", "input": "hi"}, format="json")
        assert resp.status_code == 404


# --- /v1/audio/voices ------------------------------------------------------


class TestAudioVoices:
    def test_returns_flattened_voices(self, user):
        import json
        _tts_model(user)
        riva = json.dumps({"en-US": {"voices": ["Mia", "Jason"]}}).encode()
        with patch("apps.inference.openai_views.requests.get", return_value=_FakeAudioResp(riva, content_type="application/json")):
            resp = _client(user).get("/v1/audio/voices?model=magpie")
        assert resp.status_code == 200
        assert resp.json()["voices"] == ["Jason", "Mia"]

    def test_no_provider_404(self, user):
        resp = _client(user).get("/v1/audio/voices?model=nope")
        assert resp.status_code == 404


# --- public output audio ---------------------------------------------------


class TestPublicOutputAudio:
    def test_output_audio_public(self, user):
        from rest_framework.test import APIClient
        _tts_model(user)
        with patch("apps.inference.openai_views.requests.post", return_value=_FakeAudioResp(_tiny_wav())):
            _client(user).post("/v1/audio/speech", {"model": "magpie", "input": "hi"}, format="json")
        asset = MediaAsset.objects.get(user=user, kind="OUTPUT_AUDIO")
        # Anonymous can fetch generated speech (public by URL).
        resp = APIClient().get(f"/api/inference/assets/{asset.id}/")
        assert resp.status_code == 200
