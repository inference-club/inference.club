"""The /v1/files Media Library API (PRD 17 §5)."""
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

from apps.inference.models import MediaAsset

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user(email="owner@ex.com", password="x")


@pytest.fixture
def other(db):
    return User.objects.create_user(email="other@ex.com", password="x")


def _client(user=None):
    c = APIClient()
    if user:
        c.force_authenticate(user)
    return c


def _png(name="img.png"):
    return SimpleUploadedFile(name, b"PNGDATA", content_type="image/png")


def test_upload_creates_owner_only_asset(owner):
    c = _client(owner)
    resp = c.post("/v1/files", {"file": _png()}, format="multipart")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["kind"] == "INPUT_IMAGE"
    assert body["visibility"] == "SECRET"          # private by default
    assert body["public_id"]
    assert body["url"].endswith(f"/api/inference/assets/{body['public_id']}/")
    # the row exists, owned by the uploader, unbound to any request
    asset = MediaAsset.objects.get(public_id=body["public_id"])
    assert asset.user_id == owner.id and asset.inference_request_id is None


def test_upload_requires_a_file(owner):
    resp = _client(owner).post("/v1/files", {}, format="multipart")
    assert resp.status_code == 400
    assert resp.json()["error"]["type"] == "missing_file"


def test_anonymous_cannot_upload(owner):
    resp = APIClient().post("/v1/files", {"file": _png()}, format="multipart")
    assert resp.status_code in (401, 403)


@override_settings(IMAGE_MAX_UPLOAD_BYTES=4)
def test_oversized_upload_rejected(owner):
    resp = _client(owner).post("/v1/files", {"file": _png()}, format="multipart")
    assert resp.status_code == 413
    assert resp.json()["error"]["type"] == "file_too_large"


def test_wrong_type_for_forced_kind_rejected(owner):
    txt = SimpleUploadedFile("a.txt", b"hello", content_type="text/plain")
    resp = _client(owner).post(
        "/v1/files", {"file": txt, "kind": "INPUT_IMAGE"}, format="multipart"
    )
    assert resp.status_code == 415


def test_list_is_owner_scoped(owner, other):
    _client(owner).post("/v1/files", {"file": _png()}, format="multipart")
    mine = _client(owner).get("/v1/files").json()
    assert mine["total"] == 1 and mine["data"][0]["kind"] == "INPUT_IMAGE"
    # a different user sees none of it
    assert _client(other).get("/v1/files").json()["total"] == 0


def test_list_filters_by_kind_and_bound(owner):
    _client(owner).post("/v1/files", {"file": _png()}, format="multipart")
    c = _client(owner)
    assert c.get("/v1/files?kind=INPUT_IMAGE").json()["total"] == 1
    assert c.get("/v1/files?kind=INPUT_AUDIO").json()["total"] == 0
    assert c.get("/v1/files?bound=false").json()["total"] == 1
    assert c.get("/v1/files?bound=true").json()["total"] == 0


def test_publish_makes_it_visible_to_others(owner, other):
    pid = _client(owner).post(
        "/v1/files", {"file": _png()}, format="multipart"
    ).json()["public_id"]
    # before: other user is denied
    assert _client(other).get(f"/v1/files/{pid}").status_code == 403
    # owner publishes it
    r = _client(owner).patch(
        f"/v1/files/{pid}", {"visibility": "PUBLIC"}, format="json"
    )
    assert r.status_code == 200 and r.json()["visibility"] == "PUBLIC"
    # after: other user (and anonymous) can read it
    assert _client(other).get(f"/v1/files/{pid}").status_code == 200
    assert APIClient().get(f"/v1/files/{pid}").status_code == 200


def test_non_owner_cannot_patch_or_delete(owner, other):
    pid = _client(owner).post(
        "/v1/files", {"file": _png()}, format="multipart"
    ).json()["public_id"]
    assert _client(other).patch(
        f"/v1/files/{pid}", {"visibility": "PUBLIC"}, format="json"
    ).status_code == 403
    assert _client(other).delete(f"/v1/files/{pid}").status_code == 403


def test_delete_removes_the_asset(owner):
    pid = _client(owner).post(
        "/v1/files", {"file": _png()}, format="multipart"
    ).json()["public_id"]
    assert _client(owner).delete(f"/v1/files/{pid}").status_code == 204
    assert not MediaAsset.objects.filter(public_id=pid).exists()


def test_content_route_serves_bytes_to_owner(owner, other):
    pid = _client(owner).post(
        "/v1/files", {"file": _png()}, format="multipart"
    ).json()["public_id"]
    r = _client(owner).get(f"/v1/files/{pid}/content")
    assert r.status_code == 200
    assert b"".join(r.streaming_content) == b"PNGDATA"
    # a stranger is gated out of the bytes too
    assert _client(other).get(f"/v1/files/{pid}/content").status_code == 403


def test_guest_cannot_publish(owner):
    owner.account_type = "GUEST"
    owner.save(update_fields=["account_type"])
    pid = _client(owner).post(
        "/v1/files", {"file": _png()}, format="multipart"
    ).json()["public_id"]
    r = _client(owner).patch(
        f"/v1/files/{pid}", {"visibility": "PUBLIC"}, format="json"
    )
    # clamped down to UNLISTED — guests never make content fully public
    assert r.json()["visibility"] == "UNLISTED"
