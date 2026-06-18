"""Image generation: the /v1/images/generations (JSON) and /v1/images/edits
(multipart) proxies, service-type routing, MinIO storage, response shaping,
and public-by-URL asset access. Upstream is mocked.
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
from apps.inference.openai_views import _find_provider_for_model
from apps.inference.views import sync_provider_models_from_manifest

User = get_user_model()

# 1x1 PNG, base64 — a valid decodable image for the fake upstream.
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture
def user(db):
    return User.objects.create_user(email="img@example.com", password="x")


def _online_provider(u, host="n1"):
    return Provider.objects.create(
        user=u, name=f"node-{host}", tailnet_hostname=host,
        is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
    )


def _image_model(p, name="image-model"):
    svc = ProviderService.objects.create(
        provider=p, name="img", engine="other", service_type="image",
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


class _FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.ok = payload, status, 200 <= status < 300
        self.headers = {"content-type": "application/json"}
        self.text = ""

    def json(self):
        return self._p


def _gen_resp(n=1):
    return _FakeResp({"created": 1, "data": [{"b64_json": PNG_B64} for _ in range(n)]})


# --- validation + routing --------------------------------------------------


class TestImageManifestAndRouting:
    def test_manifest_type_image_valid(self):
        m = {
            "schema_version": 1, "agent": {"name": "a"},
            "hosts": [{"id": "h", "services": [{
                "name": "img", "type": "image", "engine": "other",
                "url": "http://h:8000/v1",
            }]}],
        }
        assert validate_manifest(m) == []

    def test_image_request_only_matches_image_service(self, user):
        p = _online_provider(user)
        _image_model(p, "image-model")
        assert _find_provider_for_model(user, "image-model", service_type="image") is not None
        # An LLM-typed model of the same name must not match image routing.
        assert _find_provider_for_model(user, "nope", service_type="image") is None

    def test_sync_sets_image_modalities(self, user):
        p = _online_provider(user)
        sync_provider_models_from_manifest(p, {
            "schema_version": 1, "agent": {"name": "club-host"},
            "hosts": [{"id": "h", "services": [{
                "name": "img", "type": "image", "engine": "other",
                "url": "http://h:8000/v1", "models": [{"id": "sdxl"}],
            }]}],
        })
        pm = ProviderModel.objects.get(provider=p, name="sdxl")
        assert pm.service.service_type == "image"
        assert pm.catalog_model.input_modalities == ["text", "image"]
        assert pm.catalog_model.output_modalities == ["image"]

    def test_modalities_reseeded_when_type_added_later(self, user):
        """Regression (prod): a model whose catalog was created before the
        service type was known (older agent dropped `type`) must get correct
        modalities on the next sync once the type is declared — even with no
        declared modalities to fall back to."""
        p = _online_provider(user)
        # First sync without a type → defaults to llm → text-in/text-out.
        manifest = {
            "schema_version": 1, "agent": {"name": "club-host"},
            "hosts": [{"id": "h", "services": [{
                "name": "img", "engine": "other",
                "url": "http://h:8000/v1", "models": [{"id": "flux-x"}],
            }]}],
        }
        sync_provider_models_from_manifest(p, manifest)
        pm = ProviderModel.objects.select_related("catalog_model").get(provider=p, name="flux-x")
        assert pm.catalog_model.input_modalities == ["text"]  # llm default
        # Now the type is declared (new agent) — re-sync must fix modalities.
        manifest["hosts"][0]["services"][0]["type"] = "image"
        sync_provider_models_from_manifest(p, manifest)
        pm.catalog_model.refresh_from_db()
        assert pm.catalog_model.input_modalities == ["text", "image"]
        assert pm.catalog_model.output_modalities == ["image"]

    def test_declared_model_capabilities_applied(self, user):
        """Operator-declared per-model capabilities flow into the CatalogModel
        and the deployment, overriding the service-type defaults."""
        p = _online_provider(user)
        manifest = {
            "schema_version": 1, "agent": {"name": "club-host"},
            "hosts": [{"id": "h", "services": [{
                "name": "llm", "engine": "vllm", "type": "llm",
                "url": "http://h:8000/v1",
                "models": [{
                    "id": "qwen3-vl",
                    "hf": "Qwen/Qwen3-VL",
                    "name": "Qwen3 VL",
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
                    "features": ["reasoning", "tools"],
                    "context_length": 32768,
                    "quantization": "fp8",
                }],
            }]}],
        }
        sync_provider_models_from_manifest(p, manifest)
        pm = ProviderModel.objects.select_related("catalog_model").get(provider=p, name="qwen3-vl")
        cat = pm.catalog_model
        assert cat.display_name == "Qwen3 VL"
        assert cat.input_modalities == ["text", "image"]
        assert cat.supported_features == ["reasoning", "tools"]
        assert cat.native_context_length == 32768
        assert pm.metadata.get("quantization") == "fp8"


# --- generations -----------------------------------------------------------


class TestImageGenerations:
    def test_happy_path_stores_and_returns_url(self, user):
        p = _online_provider(user)
        _image_model(p)
        with patch("apps.inference.openai_views.requests.post", return_value=_gen_resp()):
            resp = _client(user).post(
                "/v1/images/generations",
                {"model": "image-model", "prompt": "a cat", "size": "256x256"},
                format="json",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"][0]["url"].startswith("http")
        assert "b64_json" not in body["data"][0]
        ir = InferenceRequest.objects.get(user=user, inference_type="IMAGE")
        assert ir.status == "PROCESSED" and ir.image_count == 1
        assert MediaAsset.objects.filter(user=user, kind="OUTPUT_IMAGE").count() == 1

    def test_b64_json_returned_when_requested(self, user):
        p = _online_provider(user)
        _image_model(p)
        with patch("apps.inference.openai_views.requests.post", return_value=_gen_resp()):
            resp = _client(user).post(
                "/v1/images/generations",
                {"model": "image-model", "prompt": "a cat", "response_format": "b64_json"},
                format="json",
            )
        assert resp.json()["data"][0]["b64_json"] == PNG_B64
        # still stored
        assert MediaAsset.objects.filter(user=user, kind="OUTPUT_IMAGE").count() == 1

    def test_b64_forced_and_n_clamped_upstream(self, user, settings):
        settings.IMAGE_MAX_N = 2
        p = _online_provider(user)
        _image_model(p)
        captured = {}

        def _cap(url, **kw):
            captured["json"] = kw.get("json")
            return _gen_resp()

        with patch("apps.inference.openai_views.requests.post", side_effect=_cap):
            _client(user).post(
                "/v1/images/generations",
                {"model": "image-model", "prompt": "x", "n": 9, "response_format": "url"},
                format="json",
            )
        assert captured["json"]["response_format"] == "b64_json"  # forced
        assert captured["json"]["n"] == 2  # clamped
        assert captured["json"]["model"] == "image-model"  # served name

    def test_missing_prompt_400(self, user):
        p = _online_provider(user)
        _image_model(p)
        resp = _client(user).post(
            "/v1/images/generations", {"model": "image-model"}, format="json"
        )
        assert resp.status_code == 400

    def test_no_image_provider_404(self, user):
        resp = _client(user).post(
            "/v1/images/generations", {"model": "nope", "prompt": "x"}, format="json"
        )
        assert resp.status_code == 404


# --- edits -----------------------------------------------------------------


def _png_upload(name="src.png"):
    import base64
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, base64.b64decode(PNG_B64), content_type="image/png")


class TestImageEdits:
    def test_edit_stores_input_and_output(self, user):
        p = _online_provider(user)
        _image_model(p)
        with patch("apps.inference.openai_views.requests.post", return_value=_gen_resp()):
            resp = _client(user).post(
                "/v1/images/edits",
                {"model": "image-model", "prompt": "make it blue", "image": _png_upload()},
                format="multipart",
            )
        assert resp.status_code == 200
        assert resp.json()["data"][0]["url"].startswith("http")
        assert MediaAsset.objects.filter(user=user, kind="INPUT_IMAGE").count() == 1
        assert MediaAsset.objects.filter(user=user, kind="OUTPUT_IMAGE").count() == 1

    def test_edit_missing_image_400(self, user):
        p = _online_provider(user)
        _image_model(p)
        resp = _client(user).post(
            "/v1/images/edits", {"model": "image-model", "prompt": "x"}, format="multipart"
        )
        assert resp.status_code == 400

    def test_multi_reference_edit_forwards_image_array(self, user):
        """Several `image[]` sources are stored and forwarded as repeated
        `image[]` multipart parts (multi-reference editing, e.g. FLUX.2 Klein)."""
        p = _online_provider(user)
        _image_model(p)
        with patch("apps.inference.openai_views.requests.post", return_value=_gen_resp()) as post:
            resp = _client(user).post(
                "/v1/images/edits",
                {
                    "model": "image-model",
                    "prompt": "combine these",
                    "image[]": [_png_upload("a.png"), _png_upload("b.png")],
                },
                format="multipart",
            )
        assert resp.status_code == 200
        # Both sources stored…
        assert MediaAsset.objects.filter(user=user, kind="INPUT_IMAGE").count() == 2
        # …and forwarded upstream as two `image[]` parts (a list of tuples).
        forwarded = [name for name, _ in post.call_args.kwargs["files"]]
        assert forwarded.count("image[]") == 2
        # …and both surface in the list serializer so the UI can show every
        # reference (not just the first) on the card / detail / share views.
        ir = InferenceRequest.objects.get(user=user, inference_type="IMAGE")
        listed = _client(user).get("/api/inference/requests/").json()["results"]
        row = next(r for r in listed if str(r["id"]) == str(ir.id))
        assert len(row["input_image_urls"]) == 2
        assert row["input_image_url"] == row["input_image_urls"][0]

    def test_single_image_still_uses_image_field(self, user):
        """A lone source keeps the classic single `image` field for compat."""
        p = _online_provider(user)
        _image_model(p)
        with patch("apps.inference.openai_views.requests.post", return_value=_gen_resp()) as post:
            resp = _client(user).post(
                "/v1/images/edits",
                {"model": "image-model", "prompt": "x", "image": _png_upload()},
                format="multipart",
            )
        assert resp.status_code == 200
        forwarded = [name for name, _ in post.call_args.kwargs["files"]]
        assert forwarded == ["image"]


# --- public asset access ---------------------------------------------------


class TestPublicImageAssets:
    def test_output_image_served_without_auth(self, user):
        from rest_framework.test import APIClient
        p = _online_provider(user)
        _image_model(p)
        with patch("apps.inference.openai_views.requests.post", return_value=_gen_resp()):
            _client(user).post(
                "/v1/images/generations",
                {"model": "image-model", "prompt": "a cat"}, format="json",
            )
        asset = MediaAsset.objects.get(user=user, kind="OUTPUT_IMAGE")
        # Anonymous client (no auth) can fetch a public image asset.
        anon = APIClient()
        resp = anon.get(f"/api/inference/assets/{asset.id}/")
        assert resp.status_code == 200

    def test_input_audio_still_owner_gated(self, user):
        """Regression: making images public must not open up private audio."""
        from rest_framework.test import APIClient
        a = MediaAsset.objects.create(
            user=user, kind="INPUT_AUDIO", content_type="audio/wav", size_bytes=1,
        )
        a.file.save("x.wav", __import__("django.core.files.base", fromlist=["ContentFile"]).ContentFile(b"x"), save=False)
        a.save()
        resp = APIClient().get(f"/api/inference/assets/{a.id}/")
        assert resp.status_code in (401, 403)
