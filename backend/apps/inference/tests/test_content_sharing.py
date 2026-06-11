"""Tests for the content-sharing feature (docs/prd/01-content-sharing.md):
visibility levels, share links, stars, bookmarks, and collections."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from social_django.models import UserSocialAuth

from apps.inference.models import (
    Bookmark,
    Collection,
    CollectionItem,
    InferenceRequest,
    Star,
)

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def alice(db):
    u = User.objects.create_user(email="alice@example.com", password="pw")
    UserSocialAuth.objects.create(
        user=u, provider="github", uid="1", extra_data={"login": "alice"}
    )
    return u


@pytest.fixture
def bob(db):
    u = User.objects.create_user(email="bob@example.com", password="pw")
    UserSocialAuth.objects.create(
        user=u, provider="github", uid="2", extra_data={"login": "bob"}
    )
    return u


def make_request(user, visibility="PUBLIC", **kw):
    ir = InferenceRequest.objects.create(
        user=user,
        inference_type="LLM",
        payload={"prompt": "hi"},
        visibility=visibility,
        **kw,
    )
    return ir


# --- visibility defaults & creation -----------------------------------------


@pytest.mark.django_db
class TestVisibilityDefaults:
    def test_new_request_inherits_account_default(self, alice):
        alice.default_request_visibility = "PRIVATE"
        alice.save()
        ir = InferenceRequest.objects.create(
            user=alice, inference_type="LLM", payload={"prompt": "x"}
        )
        assert ir.visibility == "PRIVATE"

    def test_default_falls_back_to_unlisted(self, alice):
        # Account default is the model default ("UNLISTED") out of the box.
        ir = InferenceRequest.objects.create(
            user=alice, inference_type="LLM", payload={"prompt": "x"}
        )
        assert ir.visibility == "UNLISTED"

    def test_share_token_generated_and_unique(self, alice):
        a = make_request(alice)
        b = make_request(alice)
        assert a.share_token and b.share_token
        assert a.share_token != b.share_token


# --- is_visible_to ----------------------------------------------------------


@pytest.mark.django_db
class TestIsVisibleTo:
    def test_public_visible_to_anonymous(self, alice):
        from django.contrib.auth.models import AnonymousUser

        assert make_request(alice, "PUBLIC").is_visible_to(AnonymousUser())

    def test_unlisted_visible_to_anyone_with_link(self, alice):
        from django.contrib.auth.models import AnonymousUser

        assert make_request(alice, "UNLISTED").is_visible_to(AnonymousUser())

    def test_private_members_only(self, alice, bob):
        from django.contrib.auth.models import AnonymousUser

        ir = make_request(alice, "PRIVATE")
        assert not ir.is_visible_to(AnonymousUser())
        assert ir.is_visible_to(bob)

    def test_secret_owner_only(self, alice, bob):
        ir = make_request(alice, "SECRET")
        assert ir.is_visible_to(alice)
        assert not ir.is_visible_to(bob)


# --- detail endpoint enforces visibility ------------------------------------


@pytest.mark.django_db
class TestRetrieveVisibility:
    def test_member_cannot_view_others_secret(self, api_client, alice, bob):
        ir = make_request(alice, "SECRET")
        api_client.force_authenticate(bob)
        r = api_client.get(reverse("inference:inference-detail", args=[ir.id]))
        assert r.status_code == 404

    def test_owner_can_view_own_secret(self, api_client, alice):
        ir = make_request(alice, "SECRET")
        api_client.force_authenticate(alice)
        r = api_client.get(reverse("inference:inference-detail", args=[ir.id]))
        assert r.status_code == 200
        # Owner sees their share token; others wouldn't.
        assert r.data["share_token"] == ir.share_token

    def test_member_can_view_private(self, api_client, alice, bob):
        ir = make_request(alice, "PRIVATE")
        api_client.force_authenticate(bob)
        r = api_client.get(reverse("inference:inference-detail", args=[ir.id]))
        assert r.status_code == 200
        assert r.data["share_token"] is None  # not the owner

    def test_owner_can_patch_visibility(self, api_client, alice):
        ir = make_request(alice, "PRIVATE")
        api_client.force_authenticate(alice)
        r = api_client.patch(
            reverse("inference:inference-detail", args=[ir.id]),
            {"visibility": "PUBLIC"},
            format="json",
        )
        assert r.status_code == 200
        ir.refresh_from_db()
        assert ir.visibility == "PUBLIC"

    def test_member_cannot_patch_others_visibility(self, api_client, alice, bob):
        ir = make_request(alice, "PUBLIC")
        api_client.force_authenticate(bob)
        r = api_client.patch(
            reverse("inference:inference-detail", args=[ir.id]),
            {"visibility": "SECRET"},
            format="json",
        )
        assert r.status_code == 403

    def test_invalid_visibility_rejected(self, api_client, alice):
        ir = make_request(alice, "PUBLIC")
        api_client.force_authenticate(alice)
        r = api_client.patch(
            reverse("inference:inference-detail", args=[ir.id]),
            {"visibility": "BOGUS"},
            format="json",
        )
        assert r.status_code == 400


# --- shared-by-token endpoint -----------------------------------------------


@pytest.mark.django_db
class TestSharedByToken:
    def test_anonymous_can_open_public_link(self, api_client, alice):
        ir = make_request(alice, "PUBLIC")
        r = api_client.get(reverse("inference:inference-shared", args=[ir.share_token]))
        assert r.status_code == 200
        assert r.data["id"] == ir.id

    def test_anonymous_can_open_unlisted_link(self, api_client, alice):
        ir = make_request(alice, "UNLISTED")
        r = api_client.get(reverse("inference:inference-shared", args=[ir.share_token]))
        assert r.status_code == 200

    def test_anonymous_blocked_from_private_link(self, api_client, alice):
        ir = make_request(alice, "PRIVATE")
        r = api_client.get(reverse("inference:inference-shared", args=[ir.share_token]))
        assert r.status_code == 404

    def test_anonymous_blocked_from_secret_link(self, api_client, alice):
        ir = make_request(alice, "SECRET")
        r = api_client.get(reverse("inference:inference-shared", args=[ir.share_token]))
        assert r.status_code == 404

    def test_bad_token_404(self, api_client):
        r = api_client.get(reverse("inference:inference-shared", args=["nope"]))
        assert r.status_code == 404


# --- all-requests feed honors visibility ------------------------------------


@pytest.mark.django_db
class TestAllFeedVisibility:
    def test_feed_excludes_unlisted_and_secret_of_others(self, api_client, alice, bob):
        pub = make_request(alice, "PUBLIC")
        priv = make_request(alice, "PRIVATE")
        unl = make_request(alice, "UNLISTED")
        sec = make_request(alice, "SECRET")
        api_client.force_authenticate(bob)
        r = api_client.get(reverse("inference:inference-requests-all"))
        ids = {row["id"] for row in r.data["results"]}
        assert pub.id in ids
        assert priv.id in ids
        assert unl.id not in ids
        assert sec.id not in ids

    def test_owner_sees_own_unlisted_in_feed(self, api_client, alice):
        unl = make_request(alice, "UNLISTED")
        api_client.force_authenticate(alice)
        r = api_client.get(reverse("inference:inference-requests-all"))
        ids = {row["id"] for row in r.data["results"]}
        assert unl.id in ids


# --- stars ------------------------------------------------------------------


@pytest.mark.django_db
class TestStars:
    def test_star_toggle_and_count(self, api_client, alice, bob):
        ir = make_request(alice, "PUBLIC")
        api_client.force_authenticate(bob)
        url = reverse("inference:inference-request-star", args=[ir.id])

        r = api_client.post(url)
        assert r.status_code == 200
        assert r.data == {"is_starred": True, "star_count": 1}
        ir.refresh_from_db()
        assert ir.star_count == 1

        # Idempotent
        api_client.post(url)
        ir.refresh_from_db()
        assert ir.star_count == 1

        r = api_client.delete(url)
        assert r.data == {"is_starred": False, "star_count": 0}

    def test_cannot_star_secret_of_others(self, api_client, alice, bob):
        ir = make_request(alice, "SECRET")
        api_client.force_authenticate(bob)
        r = api_client.post(reverse("inference:inference-request-star", args=[ir.id]))
        assert r.status_code == 404

    def test_starred_list(self, api_client, alice, bob):
        ir = make_request(alice, "PUBLIC")
        Star.objects.create(user=bob, request=ir)
        api_client.force_authenticate(bob)
        r = api_client.get(reverse("inference:inference-requests-starred"))
        ids = {row["id"] for row in r.data["results"]}
        assert ir.id in ids
        assert r.data["results"][0]["is_starred"] is True

    def test_sort_by_popular(self, api_client, alice, bob):
        cold = make_request(alice, "PUBLIC")
        hot = make_request(alice, "PUBLIC")
        Star.objects.create(user=bob, request=hot)
        hot.recount_stars()
        api_client.force_authenticate(alice)
        r = api_client.get(
            reverse("inference:inference-requests"), {"sort": "popular"}
        )
        ids = [row["id"] for row in r.data["results"]]
        assert ids.index(hot.id) < ids.index(cold.id)


# --- bookmarks --------------------------------------------------------------


@pytest.mark.django_db
class TestBookmarks:
    def test_bookmark_toggle(self, api_client, alice, bob):
        ir = make_request(alice, "PUBLIC")
        api_client.force_authenticate(bob)
        url = reverse("inference:inference-request-bookmark", args=[ir.id])
        assert api_client.post(url).data == {"is_bookmarked": True}
        assert Bookmark.objects.filter(user=bob, request=ir).exists()
        assert api_client.delete(url).data == {"is_bookmarked": False}

    def test_bookmarked_shows_on_public_profile(self, api_client, alice, bob):
        # bob bookmarks alice's public request; it surfaces on bob's profile.
        ir = make_request(alice, "PUBLIC")
        Bookmark.objects.create(user=bob, request=ir)
        r = api_client.get(
            reverse("public-user-requests", args=["bob"]),
            {"scope": "bookmarked"},
        )
        ids = {row["id"] for row in r.data["results"]}
        assert ir.id in ids

    def test_bookmarked_private_hidden_from_public_profile(self, api_client, alice, bob):
        ir = make_request(alice, "PRIVATE")
        Bookmark.objects.create(user=bob, request=ir)
        r = api_client.get(
            reverse("public-user-requests", args=["bob"]),
            {"scope": "bookmarked"},
        )
        ids = {row["id"] for row in r.data["results"]}
        assert ir.id not in ids


# --- public profile master switch -------------------------------------------


@pytest.mark.django_db
class TestPublicProfileSwitch:
    def test_profile_hidden_when_disabled(self, api_client, alice):
        make_request(alice, "PUBLIC")
        alice.public_profile_enabled = False
        alice.save()
        assert (
            api_client.get(
                reverse("public-user-profile", args=["alice"])
            ).status_code
            == 404
        )
        assert (
            api_client.get(
                reverse("public-user-requests", args=["alice"])
            ).status_code
            == 404
        )

    def test_public_requests_only_lists_public(self, api_client, alice):
        pub = make_request(alice, "PUBLIC")
        make_request(alice, "PRIVATE")
        make_request(alice, "UNLISTED")
        r = api_client.get(reverse("public-user-requests", args=["alice"]))
        ids = {row["id"] for row in r.data["results"]}
        assert ids == {pub.id}


# --- collections ------------------------------------------------------------


@pytest.mark.django_db
class TestCollections:
    def test_create_and_list(self, api_client, alice):
        api_client.force_authenticate(alice)
        r = api_client.post(
            reverse("inference:collection-list"),
            {"name": "My Best", "visibility": "PUBLIC"},
            format="json",
        )
        assert r.status_code == 201
        assert r.data["slug"] == "my-best"
        r = api_client.get(reverse("inference:collection-list"))
        assert len(r.data) == 1

    def test_same_name_get_or_creates(self, api_client, alice):
        # Names are unique per user: POSTing an existing name returns that
        # collection (200) instead of minting a slug-suffixed duplicate.
        api_client.force_authenticate(alice)
        url = reverse("inference:collection-list")
        a = api_client.post(url, {"name": "Dup"}, format="json")
        b = api_client.post(url, {"name": "Dup"}, format="json")
        assert a.status_code == 201 and b.status_code == 200
        assert a.data["id"] == b.data["id"]

    def test_add_and_remove_item(self, api_client, alice):
        col = Collection.objects.create(user=alice, name="C", slug="c")
        ir = make_request(alice, "PUBLIC")
        api_client.force_authenticate(alice)
        item_url = reverse(
            "inference:collection-item", args=[col.slug, ir.id]
        )
        assert api_client.post(item_url).data == {"in_collection": True}
        assert CollectionItem.objects.filter(collection=col, request=ir).exists()

        detail = api_client.get(
            reverse("inference:collection-detail", args=[col.slug])
        )
        assert {i["id"] for i in detail.data["items"]} == {ir.id}

        assert api_client.delete(item_url).data == {"in_collection": False}

    def test_public_collection_visible_anonymously(self, api_client, alice):
        col = Collection.objects.create(
            user=alice, name="Pub", slug="pub", visibility="PUBLIC"
        )
        ir = make_request(alice, "PUBLIC")
        CollectionItem.objects.create(collection=col, request=ir)
        r = api_client.get(
            reverse("public-user-collections", args=["alice"])
        )
        assert {c["slug"] for c in r.data} == {"pub"}
        detail = api_client.get(
            reverse("public-user-collection-detail", args=["alice", "pub"])
        )
        assert {i["id"] for i in detail.data["items"]} == {ir.id}

    def test_private_collection_hidden_from_public_list(self, api_client, alice):
        Collection.objects.create(
            user=alice, name="Sec", slug="sec", visibility="SECRET"
        )
        r = api_client.get(
            reverse("public-user-collections", args=["alice"])
        )
        assert r.data == []

    def test_collection_items_respect_item_visibility(self, api_client, alice):
        # A PUBLIC collection may contain a SECRET item; anonymous viewers
        # must not see that item.
        col = Collection.objects.create(
            user=alice, name="Mix", slug="mix", visibility="PUBLIC"
        )
        pub = make_request(alice, "PUBLIC")
        sec = make_request(alice, "SECRET")
        CollectionItem.objects.create(collection=col, request=pub)
        CollectionItem.objects.create(collection=col, request=sec)
        detail = api_client.get(
            reverse("public-user-collection-detail", args=["alice", "mix"])
        )
        ids = {i["id"] for i in detail.data["items"]}
        assert ids == {pub.id}
