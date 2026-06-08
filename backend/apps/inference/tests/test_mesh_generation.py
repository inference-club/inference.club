"""Image-to-3D (mesh): the /v1/3d/generations multipart proxy, service-type
routing, option validation, MinIO storage of the input image + GLB, response
shaping, serializer fields, and public-by-URL model access. Upstream (the
TRELLIS.2-speaking agent) is mocked — it returns raw GLB bytes plus an
``X-Trellis-Metadata`` header.
"""
import base64
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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
from apps.inference.serializers import (
    InferenceRequestDetailSerializer,
    InferenceRequestListSerializer,
)
from apps.inference.views import sync_provider_models_from_manifest

User = get_user_model()

# 1x1 PNG, base64 — a valid decodable source image.
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
# Minimal GLB header bytes ("glTF" magic) — enough to stand in for a real model.
GLB_BYTES = b"glTF" + b"\x02\x00\x00\x00" + b"\x00" * 16
TRELLIS_META = {"seed": 42, "resolution": "512", "vertices": 305001, "faces": 466068,
                "timing_sec": {"sample": 27.7, "bake": 5.7}}


@pytest.fixture
def user(db):
    return User.objects.create_user(email="mesh@example.com", password="x")


def _online_provider(u, host="m1"):
    return Provider.objects.create(
        user=u, name=f"node-{host}", tailnet_hostname=host,
        is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
    )


def _mesh_model(p, name="trellis2"):
    svc = ProviderService.objects.create(
        provider=p, name="mesh", engine="other", service_type="mesh",
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


def _png_upload(name="src.png"):
    return SimpleUploadedFile(name, base64.b64decode(PNG_B64), content_type="image/png")


class _FakeGlbResp:
    """A raw-bytes upstream response with the metadata header, like the agent's
    pass-through of TRELLIS.2's /generate."""

    def __init__(self, content=GLB_BYTES, status=200, meta=TRELLIS_META):
        self.content = content
        self.status_code = status
        self.ok = 200 <= status < 300
        self.headers = {"content-type": "model/gltf-binary"}
        if meta is not None:
            self.headers["X-Trellis-Metadata"] = json.dumps(meta)
        self.text = ""

    def json(self):
        return {}


# --- validation + routing --------------------------------------------------


class TestMeshManifestAndRouting:
    def test_manifest_type_mesh_valid(self):
        m = {
            "schema_version": 1, "agent": {"name": "a"},
            "hosts": [{"id": "h", "services": [{
                "name": "mesh", "type": "mesh", "engine": "other",
                "url": "http://h:8000",
            }]}],
        }
        assert validate_manifest(m) == []

    def test_mesh_request_only_matches_mesh_service(self, user):
        p = _online_provider(user)
        _mesh_model(p, "trellis2")
        assert _find_provider_for_model(user, "trellis2", service_type="mesh") is not None
        # The same name must not resolve under image routing.
        assert _find_provider_for_model(user, "trellis2", service_type="image") is None

    def test_sync_sets_mesh_modalities(self, user):
        p = _online_provider(user)
        sync_provider_models_from_manifest(p, {
            "schema_version": 1, "agent": {"name": "club-host"},
            "hosts": [{"id": "h", "services": [{
                "name": "mesh", "type": "mesh", "engine": "other",
                "url": "http://h:8000", "models": [{"id": "trellis2"}],
            }]}],
        })
        pm = ProviderModel.objects.get(provider=p, name="trellis2")
        assert pm.service.service_type == "mesh"
        assert pm.catalog_model.input_modalities == ["image"]
        assert pm.catalog_model.output_modalities == ["model"]


# --- generations -----------------------------------------------------------


class TestMeshGenerations:
    def test_happy_path_stores_input_and_model(self, user):
        p = _online_provider(user)
        _mesh_model(p)
        with patch("apps.inference.openai_views.requests.post", return_value=_FakeGlbResp()):
            resp = _client(user).post(
                "/v1/3d/generations",
                {"model": "trellis2", "image": _png_upload(),
                 "options": json.dumps({"resolution": "512"})},
                format="multipart",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"][0]["url"].startswith("http")
        assert body["data"][0]["type"] == "model/gltf-binary"
        assert body["metadata"]["vertices"] == 305001
        assert body["request_id"]
        ir = InferenceRequest.objects.get(user=user, inference_type="MESH")
        assert ir.status == "PROCESSED"
        assert ir.results["metadata"]["faces"] == 466068
        assert MediaAsset.objects.filter(user=user, kind="INPUT_IMAGE").count() == 1
        model = MediaAsset.objects.get(user=user, kind="OUTPUT_MODEL")
        assert model.content_type == "model/gltf-binary"
        assert model.metadata["seed"] == 42

    def test_options_forwarded_with_glb_forced(self, user):
        p = _online_provider(user)
        _mesh_model(p)
        captured = {}

        def _cap(url, **kw):
            captured["data"] = dict(kw.get("data") or [])
            captured["files"] = kw.get("files")
            return _FakeGlbResp()

        with patch("apps.inference.openai_views.requests.post", side_effect=_cap):
            _client(user).post(
                "/v1/3d/generations",
                {"model": "trellis2", "image": _png_upload(),
                 "options": json.dumps({"resolution": "1024", "seed": 7})},
                format="multipart",
            )
        sent = json.loads(captured["data"]["options"])
        assert sent["formats"] == ["glb"]   # always forced
        assert sent["resolution"] == "1024"
        assert sent["seed"] == 7
        assert captured["data"]["model"] == "trellis2"  # served name
        assert "image" in captured["files"]

    def test_invalid_options_json_400(self, user):
        p = _online_provider(user)
        _mesh_model(p)
        resp = _client(user).post(
            "/v1/3d/generations",
            {"model": "trellis2", "image": _png_upload(), "options": "{not json"},
            format="multipart",
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["type"] == "invalid_options"

    def test_invalid_resolution_400(self, user):
        p = _online_provider(user)
        _mesh_model(p)
        resp = _client(user).post(
            "/v1/3d/generations",
            {"model": "trellis2", "image": _png_upload(),
             "options": json.dumps({"resolution": "999"})},
            format="multipart",
        )
        assert resp.status_code == 400

    def test_missing_image_400(self, user):
        p = _online_provider(user)
        _mesh_model(p)
        resp = _client(user).post(
            "/v1/3d/generations", {"model": "trellis2"}, format="multipart"
        )
        assert resp.status_code == 400

    def test_no_mesh_provider_404(self, user):
        resp = _client(user).post(
            "/v1/3d/generations", {"model": "nope", "image": _png_upload()},
            format="multipart",
        )
        assert resp.status_code == 404

    def test_upstream_error_marks_request_and_502(self, user):
        p = _online_provider(user)
        _mesh_model(p)
        with patch("apps.inference.openai_views.requests.post",
                   return_value=_FakeGlbResp(content=b"", status=500, meta=None)):
            resp = _client(user).post(
                "/v1/3d/generations",
                {"model": "trellis2", "image": _png_upload()}, format="multipart",
            )
        assert resp.status_code == 500
        ir = InferenceRequest.objects.get(user=user, inference_type="MESH")
        assert ir.status == "REQUESTED"


# --- serializer fields -----------------------------------------------------


class TestMeshSerializers:
    def _make_request(self, user):
        p = _online_provider(user)
        _mesh_model(p)
        with patch("apps.inference.openai_views.requests.post", return_value=_FakeGlbResp()):
            _client(user).post(
                "/v1/3d/generations",
                {"model": "trellis2", "image": _png_upload()}, format="multipart",
            )
        return InferenceRequest.objects.get(user=user, inference_type="MESH")

    def _ctx(self, user):
        from rest_framework.test import APIRequestFactory
        req = APIRequestFactory().get("/")
        req.user = user
        return {"request": req}

    def test_list_serializer_exposes_model_url_and_mesh(self, user):
        ir = self._make_request(user)
        data = InferenceRequestListSerializer(ir, context=self._ctx(user)).data
        assert data["model_url"].startswith("http")
        assert data["input_image_url"].startswith("http")
        assert data["mesh"]["vertices"] == 305001

    def test_detail_serializer_exposes_model_url_and_mesh(self, user):
        ir = self._make_request(user)
        data = InferenceRequestDetailSerializer(ir, context=self._ctx(user)).data
        assert data["model_url"].startswith("http")
        assert data["mesh"]["faces"] == 466068

    def test_non_mesh_request_has_null_mesh(self, user):
        ir = InferenceRequest.objects.create(
            user=user, inference_type="LLM", payload={"messages": []}, status="PROCESSED",
        )
        data = InferenceRequestListSerializer(ir, context=self._ctx(user)).data
        assert data["mesh"] is None
        assert data["model_url"] is None


# --- public asset access ---------------------------------------------------


class TestPublicModelAssets:
    def test_output_model_served_without_auth(self, user):
        from rest_framework.test import APIClient
        p = _online_provider(user)
        _mesh_model(p)
        with patch("apps.inference.openai_views.requests.post", return_value=_FakeGlbResp()):
            _client(user).post(
                "/v1/3d/generations",
                {"model": "trellis2", "image": _png_upload()}, format="multipart",
            )
        asset = MediaAsset.objects.get(user=user, kind="OUTPUT_MODEL")
        resp = APIClient().get(f"/api/inference/assets/{asset.id}/")
        assert resp.status_code == 200
