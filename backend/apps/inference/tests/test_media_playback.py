"""Tests for the media-playback feature (docs/prd/06-media-playback-experience.md):
ordered collections (append-at-end + bulk reorder), playlist count annotations,
and cover art linking for tracks and collections."""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse
from rest_framework.test import APIClient

from apps.inference.models import (
    Collection,
    CollectionItem,
    InferenceRequest,
    MediaAsset,
)

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def alice(db):
    return User.objects.create_user(email="alice@example.com", password="pw")


@pytest.fixture
def bob(db):
    return User.objects.create_user(email="bob@example.com", password="pw")


def make_request(user, inference_type="LLM", visibility="PUBLIC", **kw):
    return InferenceRequest.objects.create(
        user=user,
        inference_type=inference_type,
        payload={"prompt": "hi"},
        visibility=visibility,
        **kw,
    )


def make_image_request(user, **kw):
    """An IMAGE request with a stored OUTPUT_IMAGE asset — valid cover art."""
    ir = make_request(user, "IMAGE", **kw)
    asset = MediaAsset(user=user, inference_request=ir, kind=MediaAsset.OUTPUT_IMAGE)
    asset.file.save("cover.png", ContentFile(b"fakepng"), save=False)
    asset.save()
    return ir


def add_item(api_client, col, ir):
    return api_client.post(
        reverse("inference:collection-item", args=[col.slug, ir.id])
    )


# --- ordering ----------------------------------------------------------------


@pytest.mark.django_db
class TestCollectionOrdering:
    def test_add_appends_at_end(self, api_client, alice):
        col = Collection.objects.create(user=alice, name="P", slug="p")
        api_client.force_authenticate(alice)
        first, second, third = (make_request(alice) for _ in range(3))
        for ir in (first, second, third):
            add_item(api_client, col, ir)
        detail = api_client.get(
            reverse("inference:collection-detail", args=[col.slug])
        )
        assert [i["id"] for i in detail.data["items"]] == [
            first.id,
            second.id,
            third.id,
        ]

    def test_re_add_keeps_position(self, api_client, alice):
        col = Collection.objects.create(user=alice, name="P", slug="p")
        api_client.force_authenticate(alice)
        a, b = make_request(alice), make_request(alice)
        add_item(api_client, col, a)
        add_item(api_client, col, b)
        add_item(api_client, col, a)  # idempotent — does not move to end
        detail = api_client.get(
            reverse("inference:collection-detail", args=[col.slug])
        )
        assert [i["id"] for i in detail.data["items"]] == [a.id, b.id]

    def test_reorder_full_list(self, api_client, alice):
        col = Collection.objects.create(user=alice, name="P", slug="p")
        api_client.force_authenticate(alice)
        irs = [make_request(alice) for _ in range(3)]
        for ir in irs:
            add_item(api_client, col, ir)
        new_order = [irs[2].id, irs[0].id, irs[1].id]
        r = api_client.put(
            reverse("inference:collection-order", args=[col.slug]),
            {"request_ids": new_order},
            format="json",
        )
        assert r.status_code == 200
        assert [i["id"] for i in r.data["items"]] == new_order

    def test_reorder_partial_list_keeps_rest_after(self, api_client, alice):
        col = Collection.objects.create(user=alice, name="P", slug="p")
        api_client.force_authenticate(alice)
        irs = [make_request(alice) for _ in range(4)]
        for ir in irs:
            add_item(api_client, col, ir)
        # Only name the last item; the other three keep relative order after it.
        r = api_client.put(
            reverse("inference:collection-order", args=[col.slug]),
            {"request_ids": [irs[3].id]},
            format="json",
        )
        assert [i["id"] for i in r.data["items"]] == [
            irs[3].id,
            irs[0].id,
            irs[1].id,
            irs[2].id,
        ]

    def test_reorder_ignores_unknown_ids(self, api_client, alice):
        col = Collection.objects.create(user=alice, name="P", slug="p")
        api_client.force_authenticate(alice)
        ir = make_request(alice)
        add_item(api_client, col, ir)
        r = api_client.put(
            reverse("inference:collection-order", args=[col.slug]),
            {"request_ids": [999999, ir.id]},
            format="json",
        )
        assert r.status_code == 200
        assert [i["id"] for i in r.data["items"]] == [ir.id]

    def test_reorder_rejects_bad_body(self, api_client, alice):
        col = Collection.objects.create(user=alice, name="P", slug="p")
        api_client.force_authenticate(alice)
        url = reverse("inference:collection-order", args=[col.slug])
        assert api_client.put(url, {}, format="json").status_code == 400
        assert (
            api_client.put(url, {"request_ids": "nope"}, format="json").status_code
            == 400
        )

    def test_reorder_owner_only(self, api_client, alice, bob):
        col = Collection.objects.create(user=alice, name="P", slug="p")
        api_client.force_authenticate(bob)
        r = api_client.put(
            reverse("inference:collection-order", args=[col.slug]),
            {"request_ids": []},
            format="json",
        )
        assert r.status_code == 404


# --- playlist count annotations -----------------------------------------------


@pytest.mark.django_db
class TestCollectionCounts:
    def test_modality_counts_and_runtime(self, api_client, alice):
        col = Collection.objects.create(user=alice, name="Mix", slug="mix")
        api_client.force_authenticate(alice)
        song1 = make_request(alice, "MUSIC", audio_seconds=120.0)
        song2 = make_request(alice, "MUSIC", audio_seconds=60.5)
        video = make_request(alice, "VIDEO")
        chat = make_request(alice, "LLM")
        for ir in (song1, song2, video, chat):
            add_item(api_client, col, ir)
        r = api_client.get(reverse("inference:collection-list"))
        data = next(c for c in r.data if c["slug"] == "mix")
        assert data["item_count"] == 4
        assert data["audio_count"] == 2
        assert data["video_count"] == 1
        assert data["total_audio_seconds"] == pytest.approx(180.5)


# --- cover art ------------------------------------------------------------------


@pytest.mark.django_db
class TestCoverArt:
    def cover_url(self, api_client, alice, target, cover_id):
        return api_client.patch(
            reverse("inference:inference-request-cover", args=[target.id]),
            {"cover_request_id": cover_id},
            format="json",
        )

    def test_set_and_clear_track_cover(self, api_client, alice):
        api_client.force_authenticate(alice)
        song = make_request(alice, "MUSIC")
        art = make_image_request(alice)
        r = self.cover_url(api_client, alice, song, art.id)
        assert r.status_code == 200
        assert r.data["cover_image_url"]
        song.refresh_from_db()
        assert song.cover_request_id == art.id

        r = self.cover_url(api_client, alice, song, None)
        assert r.status_code == 200
        assert r.data["cover_image_url"] is None

    def test_cover_appears_in_list_serializer(self, api_client, alice):
        api_client.force_authenticate(alice)
        song = make_request(alice, "MUSIC")
        art = make_image_request(alice)
        self.cover_url(api_client, alice, song, art.id)
        r = api_client.get(reverse("inference:inference-requests"))
        row = next(x for x in r.data["results"] if x["id"] == song.id)
        assert row["cover_image_url"]

    def test_cover_must_be_image_with_output(self, api_client, alice):
        api_client.force_authenticate(alice)
        song = make_request(alice, "MUSIC")
        not_image = make_request(alice, "LLM")
        assert self.cover_url(api_client, alice, song, not_image.id).status_code == 400
        empty_image = make_request(alice, "IMAGE")
        assert (
            self.cover_url(api_client, alice, song, empty_image.id).status_code == 400
        )

    def test_cover_must_be_own_request(self, api_client, alice, bob):
        api_client.force_authenticate(alice)
        song = make_request(alice, "MUSIC")
        bobs_art = make_image_request(bob)
        assert self.cover_url(api_client, alice, song, bobs_art.id).status_code == 404

    def test_cannot_cover_self(self, api_client, alice):
        api_client.force_authenticate(alice)
        art = make_image_request(alice)
        assert self.cover_url(api_client, alice, art, art.id).status_code == 400

    def test_cover_owner_only_target(self, api_client, alice, bob):
        api_client.force_authenticate(bob)
        song = make_request(alice, "MUSIC")
        art = make_image_request(bob)
        assert self.cover_url(api_client, bob, song, art.id).status_code == 404

    def test_collection_cover_via_patch(self, api_client, alice):
        col = Collection.objects.create(user=alice, name="P", slug="p")
        api_client.force_authenticate(alice)
        art = make_image_request(alice)
        r = api_client.patch(
            reverse("inference:collection-detail", args=[col.slug]),
            {"cover_request_id": art.id},
            format="json",
        )
        assert r.status_code == 200
        assert r.data["cover_image_url"]
        # null clears it again
        r = api_client.patch(
            reverse("inference:collection-detail", args=[col.slug]),
            {"cover_request_id": None},
            format="json",
        )
        assert r.status_code == 200
        assert r.data["cover_image_url"] is None
