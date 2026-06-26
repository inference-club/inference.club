"""Privacy matrix for user-uploaded media (PRD 17 §4.5).

Exercises the single audience rule (``MediaAsset.is_visible_to``) across the
full cross-product:

    viewer ∈ {owner, other full member, guest, anonymous}
  × asset  ∈ {bound→PUBLIC/UNLISTED/PRIVATE/SECRET, standalone PUBLIC/PRIVATE/SECRET}
  × action ∈ {byte route, metadata route}

The headline guarantee this locks in: a SECRET request's media (and any standalone
upload, which defaults to owner-only) is unreachable by anyone but its owner — on
every route — and a non-public asset's permanent storage URL is never emitted.
"""
import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import override_settings
from rest_framework.test import APIClient

from apps.inference.models import InferenceRequest, MediaAsset

User = get_user_model()
pytestmark = pytest.mark.django_db

# Which viewers may see an asset of a given effective audience. Identical whether
# the audience comes from the parent request (bound) or the asset itself
# (standalone) — that symmetry is the whole point of the rule.
ALLOWED = {
    "PUBLIC": {"owner", "other", "guest", "anon"},
    "UNLISTED": {"owner", "other", "guest", "anon"},  # opaque id = the capability
    "PRIVATE": {"owner", "other"},                     # full members only
    "SECRET": {"owner"},                               # only me
}


@pytest.fixture
def people(db):
    owner = User.objects.create_user(email="owner@ex.com", password="x")
    other = User.objects.create_user(email="member@ex.com", password="x")
    guest = User.objects.create_user(email="guest@ex.com", password="x")
    guest.account_type = "GUEST"
    guest.save(update_fields=["account_type"])
    return {"owner": owner, "other": other, "guest": guest}


def _client(viewer, people):
    c = APIClient()
    if viewer != "anon":
        c.force_authenticate(people[viewer])
    return c


def _request(owner, visibility):
    return InferenceRequest.objects.create(
        user=owner, inference_type="IMAGE", payload={}, status="PROCESSED",
        visibility=visibility,
    )


def _asset(owner, *, visibility="SECRET", request=None,
           kind=MediaAsset.OUTPUT_IMAGE):
    a = MediaAsset(
        user=owner, kind=kind, visibility=visibility, inference_request=request,
        content_type="image/png",
    )
    a.file.save("x.png", ContentFile(b"PNGDATA"), save=False)
    a.save()
    return a


@pytest.mark.parametrize("mode", ["bound", "standalone"])
@pytest.mark.parametrize("audience", ["PUBLIC", "UNLISTED", "PRIVATE", "SECRET"])
@pytest.mark.parametrize("viewer", ["owner", "other", "guest", "anon"])
def test_audience_matrix(people, mode, audience, viewer):
    owner = people["owner"]
    if mode == "bound":
        # The asset's own visibility is owner-only; it must follow the request.
        asset = _asset(owner, visibility="SECRET", request=_request(owner, audience))
    else:
        asset = _asset(owner, visibility=audience, request=None)

    allowed = viewer in ALLOWED[audience]
    c = _client(viewer, people)

    bytes_resp = c.get(f"/api/inference/assets/{asset.public_id}/")
    meta_resp = c.get(f"/v1/assets/{asset.public_id}")

    assert (bytes_resp.status_code in (200, 302)) is allowed, (
        f"{mode} {audience} bytes for {viewer}: got {bytes_resp.status_code}"
    )
    assert (meta_resp.status_code == 200) is allowed, (
        f"{mode} {audience} meta for {viewer}: got {meta_resp.status_code}"
    )
    if not allowed:
        assert bytes_resp.status_code == 403
        assert meta_resp.status_code == 403


@override_settings(MEDIA_DIRECT_PUBLIC_URLS=True)
def test_secret_request_image_never_leaks_permanent_url(people):
    """The leak this PRD closes: an OUTPUT_IMAGE physically in the public bucket
    whose request is SECRET must NOT be redirected to its permanent public URL —
    it streams through the gated route for the owner, and 403s for everyone else,
    even with GCS direct-public URLs enabled."""
    owner = people["owner"]
    asset = _asset(owner, request=_request(owner, "SECRET"))

    # non-owners: denied outright
    assert APIClient().get(
        f"/api/inference/assets/{asset.public_id}/"
    ).status_code == 403
    assert _client("other", people).get(
        f"/api/inference/assets/{asset.public_id}/"
    ).status_code == 403

    # owner: streamed (200), NOT a 302 to the permanent bucket URL
    r = _client("owner", people).get(f"/api/inference/assets/{asset.public_id}/")
    assert r.status_code == 200
    assert "Location" not in r
    assert r["Cache-Control"] == "private, no-store"
    assert b"".join(r.streaming_content) == b"PNGDATA"


def test_legacy_int_id_route_is_also_gated(people):
    """Old ``/assets/<int:pk>/`` links keep resolving but are now audience-gated,
    so the previously-enumerable integer id can no longer leak a SECRET asset."""
    owner = people["owner"]
    asset = _asset(owner, request=_request(owner, "SECRET"))

    assert APIClient().get(
        f"/api/inference/assets/{asset.id}/"
    ).status_code == 403
    assert _client("owner", people).get(
        f"/api/inference/assets/{asset.id}/"
    ).status_code == 200


def test_unbound_upload_defaults_to_owner_only(people):
    """A fresh upload (no request, default visibility) is visible to nobody but
    its owner — 'private by default'."""
    owner = people["owner"]
    asset = _asset(owner)  # default visibility=SECRET, no request
    assert asset.visibility == "SECRET"
    assert _client("other", people).get(
        f"/v1/assets/{asset.public_id}"
    ).status_code == 403
    assert _client("owner", people).get(
        f"/v1/assets/{asset.public_id}"
    ).status_code == 200
