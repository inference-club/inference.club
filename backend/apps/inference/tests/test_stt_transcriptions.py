"""Speech-to-text (STT) support: the multipart /v1/audio/transcriptions
proxy, service-type routing isolation, audio metering, and manifest plumbing.

Upstream is mocked — these exercise our proxy logic, not the ASR server.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.inference.manifest_validator import validate as validate_manifest
from apps.inference.models import (
    InferenceRequest,
    MediaAsset,
    Provider,
    ProviderModel,
    ProviderService,
    link_catalog_model,
)
from apps.inference.openai_views import _audio_seconds, _find_provider_for_model
from apps.inference.views import sync_provider_models_from_manifest

User = get_user_model()


# --- pure helpers ----------------------------------------------------------


class TestAudioSeconds:
    def test_usage_seconds(self):
        assert _audio_seconds({"text": "x", "usage": {"type": "duration", "seconds": 10}}) == 10.0

    def test_top_level_duration(self):
        assert _audio_seconds({"text": "x", "duration": 3.5}) == 3.5

    def test_none_when_absent(self):
        assert _audio_seconds({"text": "x"}) is None
        assert _audio_seconds("nope") is None


class TestManifestServiceTypeValidation:
    def _manifest(self, svc_type):
        svc = {"name": "s", "engine": "vllm", "url": "http://h:8000/v1"}
        if svc_type is not None:
            svc["type"] = svc_type
        return {
            "schema_version": 1,
            "agent": {"name": "a"},
            "hosts": [{"id": "h", "services": [svc]}],
        }

    def test_defaults_valid(self):
        assert validate_manifest(self._manifest(None)) == []

    @pytest.mark.parametrize("t", ["llm", "stt", "tts"])
    def test_known_types_valid(self, t):
        assert validate_manifest(self._manifest(t)) == []

    def test_unknown_type_rejected(self):
        errors = validate_manifest(self._manifest("bogus"))
        assert any("type" in e for e in errors)

    def test_features_list_valid(self):
        m = self._manifest("stt")
        m["hosts"][0]["services"][0]["features"] = ["timestamps"]
        assert validate_manifest(m) == []

    def test_features_non_list_rejected(self):
        m = self._manifest("stt")
        m["hosts"][0]["services"][0]["features"] = "timestamps"
        errors = validate_manifest(m)
        assert any("features" in e for e in errors)


# --- routing isolation -----------------------------------------------------


def _online_provider(user, host):
    return Provider.objects.create(
        user=user, name=f"node-{host}", tailnet_hostname=host,
        is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
    )


def _model(provider, name, service_type, features=None):
    svc = ProviderService.objects.create(
        provider=provider, name=f"svc-{name}", engine="vllm",
        service_type=service_type, access_policy=ProviderService.ACCESS_AUTHENTICATED,
        declared_features=features or [],
    )
    pm = ProviderModel(provider=provider, name=name, hf_repo_id=name, service=svc)
    link_catalog_model(pm)
    pm.save()
    return pm


@pytest.fixture
def user(db):
    return User.objects.create_user(email="u@example.com", password="x")


class TestServiceTypeRouting:
    def test_stt_request_only_matches_stt_service(self, user):
        p = _online_provider(user, "n1")
        _model(p, "whisper-1", "stt")
        pm = _find_provider_for_model(user, "whisper-1", service_type="stt")
        assert pm is not None and pm.service.service_type == "stt"

    def test_stt_request_skips_llm_service(self, user):
        p = _online_provider(user, "n1")
        _model(p, "an-llm", "llm")  # same name served as an LLM
        assert _find_provider_for_model(user, "an-llm", service_type="stt") is None

    def test_llm_path_unrestricted_still_finds_llm(self, user):
        p = _online_provider(user, "n1")
        _model(p, "an-llm", "llm")
        assert _find_provider_for_model(user, "an-llm") is not None


# --- manifest sync sets service_type + modalities --------------------------


class TestManifestSyncServiceType:
    def _sync(self, user, *, provider=None, features=None):
        p = provider or _online_provider(user, "n1")
        svc = {
            "name": "asr", "type": "stt", "engine": "vllm",
            "url": "http://h:8000/v1",
            "models": [{"id": "Qwen/Qwen3-ASR-1.7B"}],
        }
        if features is not None:
            svc["features"] = features
        sync_provider_models_from_manifest(p, {
            "schema_version": 1,
            "agent": {"name": "club-host"},
            "hosts": [{"id": "h", "services": [svc]}],
        })
        return p

    def test_stt_service_sets_type_and_modalities(self, user):
        p = self._sync(user)
        svc = ProviderService.objects.get(provider=p, name="asr")
        assert svc.service_type == "stt"
        assert svc.declared_features == []
        pm = ProviderModel.objects.get(provider=p, name="Qwen/Qwen3-ASR-1.7B")
        assert pm.catalog_model.input_modalities == ["audio"]
        assert pm.catalog_model.output_modalities == ["text"]

    def test_declared_features_captured_and_surfaced(self, user):
        """An operator who serves Qwen3-ASR with a ForcedAligner declares
        `features: [timestamps]`; it's stored per-deployment and surfaced on
        /v1/models so the playground offers the timestamp UI."""
        from apps.inference.openai_views import _model_caps
        p = self._sync(user, features=["timestamps"])
        svc = ProviderService.objects.get(provider=p, name="asr")
        assert svc.declared_features == ["timestamps"]
        pm = ProviderModel.objects.select_related("service", "catalog_model").get(
            provider=p, name="Qwen/Qwen3-ASR-1.7B"
        )
        assert "timestamps" in _model_caps(pm)["supported_features"]

    def test_features_removed_on_reupload(self, user):
        """Dropping the declaration (e.g. relaunched without the aligner)
        clears it — capability tracks the live deployment."""
        p = self._sync(user, features=["timestamps"])
        self._sync(user, provider=p, features=[])
        svc = ProviderService.objects.get(provider=p, name="asr")
        assert svc.declared_features == []


# --- the transcription proxy view (upstream mocked) ------------------------


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.ok = 200 <= status < 300
        self.headers = {"content-type": "application/json"}
        self.text = ""

    def json(self):
        return self._payload


@pytest.fixture
def stt_setup(user):
    p = _online_provider(user, "n1")
    _model(p, "Qwen/Qwen3-ASR-1.7B", "stt")
    return user, p


def _client(user):
    from rest_framework.test import APIClient
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _wav(name="a.wav"):
    from django.core.files.uploadedfile import SimpleUploadedFile
    # Minimal valid-enough bytes; upstream is mocked so content is irrelevant.
    return SimpleUploadedFile(name, b"RIFF....WAVEfmt ", content_type="audio/wav")


class TestTranscriptionView:
    def test_happy_path_records_request_and_asset(self, stt_setup):
        user, _ = stt_setup
        fake = _FakeResp({"text": "hello world", "usage": {"type": "duration", "seconds": 4}})
        with patch("apps.inference.openai_views.requests.post", return_value=fake):
            resp = _client(user).post(
                "/v1/audio/transcriptions",
                {"model": "qwen/qwen3-asr-1.7b", "file": _wav()},
                format="multipart",
            )
        assert resp.status_code == 200
        assert resp.json()["text"] == "hello world"
        ir = InferenceRequest.objects.get(user=user, inference_type="STT")
        assert ir.status == "PROCESSED"
        assert ir.audio_seconds == 4.0
        assert ir.model_name == "qwen/qwen3-asr-1.7b"
        assert MediaAsset.objects.filter(user=user, kind="INPUT_AUDIO").count() == 1

    def test_missing_file_400(self, stt_setup):
        user, _ = stt_setup
        resp = _client(user).post(
            "/v1/audio/transcriptions", {"model": "qwen/qwen3-asr-1.7b"}, format="multipart"
        )
        assert resp.status_code == 400

    def test_no_stt_provider_404(self, user):
        resp = _client(user).post(
            "/v1/audio/transcriptions",
            {"model": "nope", "file": _wav()},
            format="multipart",
        )
        assert resp.status_code == 404

    def test_verbose_json_downgraded_when_unsupported(self, stt_setup):
        """Model lacks the 'timestamps' feature → verbose_json must be sent to
        upstream as plain json so servers like Qwen3-ASR don't 400."""
        user, _ = stt_setup
        captured = {}

        def _capture(url, **kw):
            captured["data"] = dict(kw.get("data") or [])
            return _FakeResp({"text": "ok", "usage": {"seconds": 1}})

        with patch("apps.inference.openai_views.requests.post", side_effect=_capture):
            _client(user).post(
                "/v1/audio/transcriptions",
                {"model": "qwen/qwen3-asr-1.7b", "file": _wav(),
                 "response_format": "verbose_json"},
                format="multipart",
            )
        assert captured["data"].get("response_format") == "json"

    def test_verbose_json_kept_when_timestamps_declared(self, user):
        """When the STT service declares `timestamps`, verbose_json passes
        through to the (aligner-equipped) upstream instead of being downgraded."""
        p = _online_provider(user, "n1")
        _model(p, "whisper-1", "stt", features=["timestamps"])
        captured = {}

        def _capture(url, **kw):
            captured["data"] = dict(kw.get("data") or [])
            return _FakeResp({"text": "ok", "language": "en",
                              "words": [{"word": "ok", "start": 0.0, "end": 0.4}]})

        with patch("apps.inference.openai_views.requests.post", side_effect=_capture):
            resp = _client(user).post(
                "/v1/audio/transcriptions",
                {"model": "whisper-1", "file": _wav(),
                 "response_format": "verbose_json"},
                format="multipart",
            )
        assert captured["data"].get("response_format") == "verbose_json"
        # words round-trip into the structured transcription detail
        from apps.inference.models import InferenceRequest
        ir = InferenceRequest.objects.get(user=user, inference_type="STT")
        assert ir.results.get("words")

    def test_model_id_rewritten_to_served_name(self, stt_setup):
        user, _ = stt_setup
        captured = {}

        def _capture(url, **kw):
            captured["data"] = dict(kw.get("data") or [])
            return _FakeResp({"text": "ok"})

        with patch("apps.inference.openai_views.requests.post", side_effect=_capture):
            _client(user).post(
                "/v1/audio/transcriptions",
                {"model": "qwen/qwen3-asr-1.7b", "file": _wav()},
                format="multipart",
            )
        # Forwarded model must be the exact served name, not the public slug.
        assert captured["data"].get("model") == "Qwen/Qwen3-ASR-1.7B"

    def test_oversized_file_413(self, stt_setup, settings):
        user, _ = stt_setup
        settings.STT_MAX_UPLOAD_BYTES = 4
        from django.core.files.uploadedfile import SimpleUploadedFile
        big = SimpleUploadedFile("a.wav", b"x" * 100, content_type="audio/wav")
        resp = _client(user).post(
            "/v1/audio/transcriptions",
            {"model": "qwen/qwen3-asr-1.7b", "file": big},
            format="multipart",
        )
        assert resp.status_code == 413
