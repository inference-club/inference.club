"""Sharing a collection by link: the share action, the shared view, and the
rule that a shared collection only shows items that are PUBLIC or UNLISTED."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.inference.models import Collection, CollectionItem, InferenceRequest

User = get_user_model()


@pytest.fixture
def owner(db):
    return User.objects.create_user(email="owner@example.com", password="pw")


def _req(user, visibility):
    return InferenceRequest.objects.create(
        user=user,
        inference_type="IMAGE",
        status="PROCESSED",
        visibility=visibility,
        payload={},
    )


@pytest.fixture
def album(owner):
    col = Collection.objects.create(
        user=owner, name="Album", slug="album", visibility="SECRET"
    )
    for i, v in enumerate(["PUBLIC", "UNLISTED", "PRIVATE", "SECRET"]):
        CollectionItem.objects.create(collection=col, request=_req(owner, v), position=i)
    return col


def _client(user=None):
    c = APIClient()
    if user:
        c.force_authenticate(user)
    return c


def test_collection_gets_a_share_token(album):
    assert album.share_token and len(album.share_token) >= 16


def test_unshared_collection_link_404s_for_others_but_opens_for_owner(album, owner):
    url = f"/api/inference/shared-collections/{album.share_token}/"
    assert _client().get(url).status_code == 404
    assert _client(owner).get(url).status_code == 200


def test_share_refuses_until_items_are_included(album, owner):
    r = _client(owner).post("/api/inference/collections/album/share/", {}, format="json")
    assert r.status_code == 409
    assert r.data["unshareable_count"] == 2
    album.refresh_from_db()
    assert album.visibility == "SECRET"


def test_share_with_items_raises_them_to_unlisted(album, owner):
    r = _client(owner).post(
        "/api/inference/collections/album/share/",
        {"include_items": True},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["visibility"] == "UNLISTED"
    assert r.data["items_raised"] == 2
    assert r.data["unshareable_count"] == 0
    # Already-public items are left alone.
    vis = sorted(
        InferenceRequest.objects.filter(collection_items__collection=album)
        .values_list("visibility", flat=True)
    )
    assert vis == ["PUBLIC", "UNLISTED", "UNLISTED", "UNLISTED"]
    shared = _client().get(f"/api/inference/shared-collections/{album.share_token}/")
    assert shared.status_code == 200
    assert len(shared.data["items"]) == 4
    assert shared.data["share_token"] is None  # owner-only


def test_item_made_private_later_drops_out_of_the_shared_view(album, owner):
    _client(owner).post(
        "/api/inference/collections/album/share/", {"include_items": True}, format="json"
    )
    item = InferenceRequest.objects.filter(collection_items__collection=album).first()
    item.visibility = "SECRET"
    item.save()
    shared = _client().get(f"/api/inference/shared-collections/{album.share_token}/")
    assert len(shared.data["items"]) == 3


def test_someone_elses_items_are_never_raised(album, owner):
    other = User.objects.create_user(email="other@example.com", password="pw")
    theirs = _req(other, "SECRET")
    CollectionItem.objects.create(collection=album, request=theirs, position=9)
    _client(owner).post(
        "/api/inference/collections/album/share/", {"include_items": True}, format="json"
    )
    theirs.refresh_from_db()
    assert theirs.visibility == "SECRET"


def test_only_the_owner_can_share(album):
    other = User.objects.create_user(email="x@example.com", password="pw")
    r = _client(other).post("/api/inference/collections/album/share/", {}, format="json")
    assert r.status_code == 404


def test_share_rejects_a_non_shareable_visibility(album, owner):
    r = _client(owner).post(
        "/api/inference/collections/album/share/",
        {"visibility": "SECRET", "include_items": True},
        format="json",
    )
    assert r.status_code == 400
