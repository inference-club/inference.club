"""Sharing extensions on the /v1 generation endpoints: per-request
``visibility``/``collection`` body params, account defaults (default
visibility + default collection), and collection get-or-create by name.
Upstream is mocked.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.inference.models import (
    Collection,
    CollectionItem,
    InferenceRequest,
    Provider,
    ProviderModel,
    ProviderService,
    link_catalog_model,
)

User = get_user_model()

# 1x1 PNG, base64 — a valid decodable image for the fake image upstream.
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture
def user(db):
    return User.objects.create_user(email="share@example.com", password="x")


def _provider(u, host="n1"):
    return Provider.objects.create(
        user=u, name=f"node-{host}", tailnet_hostname=host,
        is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
    )


def _model(p, service_type, name):
    svc = ProviderService.objects.create(
        provider=p, name=f"{service_type}-svc", engine="other",
        service_type=service_type,
        access_policy=ProviderService.ACCESS_AUTHENTICATED,
    )
    pm = ProviderModel(provider=p, name=name, service=svc)
    link_catalog_model(pm)
    pm.save()
    return pm


def _client(u):
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


def _image_resp():
    return _FakeResp({"created": 1, "data": [{"b64_json": PNG_B64}]})


def _chat_resp():
    return _FakeResp(
        {
            "object": "chat.completion",
            "model": "llm-model",
            "choices": [{"message": {"role": "assistant", "content": "hi"}}],
        }
    )


def _gen_image(user, extra=None, mock=None):
    body = {"model": "image-model", "prompt": "a cat", **(extra or {})}
    with patch(
        "apps.inference.openai_views.requests.post",
        return_value=_image_resp(),
    ) as m:
        resp = _client(user).post("/v1/images/generations", body, format="json")
    if mock is not None:
        mock.append(m)
    return resp


@pytest.mark.django_db
class TestVisibilityParam:
    def test_visibility_override_applies(self, user):
        _model(_provider(user), "image", "image-model")
        resp = _gen_image(user, {"visibility": "PUBLIC"})
        assert resp.status_code == 200
        ir = InferenceRequest.objects.get(user=user)
        assert ir.visibility == "PUBLIC"

    def test_visibility_falls_back_to_account_default(self, user):
        user.default_request_visibility = "SECRET"
        user.save()
        _model(_provider(user), "image", "image-model")
        _gen_image(user)
        assert InferenceRequest.objects.get(user=user).visibility == "SECRET"

    def test_invalid_visibility_ignored(self, user):
        _model(_provider(user), "image", "image-model")
        resp = _gen_image(user, {"visibility": "EVERYONE"})
        assert resp.status_code == 200
        assert InferenceRequest.objects.get(user=user).visibility == "UNLISTED"

    def test_sharing_params_not_forwarded_upstream_chat(self, user):
        _model(_provider(user), "llm", "llm-model")
        with patch(
            "apps.inference.openai_views.requests.post",
            return_value=_chat_resp(),
        ) as m:
            resp = _client(user).post(
                "/v1/chat/completions",
                {
                    "model": "llm-model",
                    "messages": [{"role": "user", "content": "hi"}],
                    "visibility": "PUBLIC",
                    "collection": "Chats",
                },
                format="json",
            )
        assert resp.status_code == 200
        forwarded = m.call_args.kwargs["json"]
        assert "visibility" not in forwarded
        assert "collection" not in forwarded
        ir = InferenceRequest.objects.get(user=user)
        assert ir.visibility == "PUBLIC"
        # The stored payload is the cleaned body too.
        assert "visibility" not in ir.payload
        assert ir.collection_items.get().collection.name == "Chats"

    def test_sharing_params_not_forwarded_upstream_images(self, user):
        _model(_provider(user), "image", "image-model")
        mocks = []
        _gen_image(user, {"visibility": "PUBLIC", "collection": "Art"}, mock=mocks)
        forwarded = mocks[0].call_args.kwargs["json"]
        assert "visibility" not in forwarded
        assert "collection" not in forwarded


@pytest.mark.django_db
class TestCollectionParam:
    def test_collection_created_on_first_use(self, user):
        _model(_provider(user), "image", "image-model")
        _gen_image(user, {"collection": "Synthwave"})
        col = Collection.objects.get(user=user)
        assert col.name == "Synthwave" and col.slug == "synthwave"
        ir = InferenceRequest.objects.get(user=user)
        assert CollectionItem.objects.filter(collection=col, request=ir).exists()

    def test_collection_name_matches_case_insensitively(self, user):
        _model(_provider(user), "image", "image-model")
        _gen_image(user, {"collection": "Synthwave"})
        _gen_image(user, {"collection": "SYNTHWAVE"})
        assert Collection.objects.filter(user=user).count() == 1
        assert Collection.objects.get(user=user).items.count() == 2

    def test_items_append_in_order(self, user):
        _model(_provider(user), "image", "image-model")
        _gen_image(user, {"collection": "C"})
        _gen_image(user, {"collection": "C"})
        positions = list(
            CollectionItem.objects.filter(collection__user=user)
            .order_by("position")
            .values_list("position", flat=True)
        )
        assert positions == sorted(positions) and len(positions) == 2

    def test_new_collection_inherits_request_visibility(self, user):
        _model(_provider(user), "image", "image-model")
        _gen_image(user, {"visibility": "PUBLIC", "collection": "Showcase"})
        assert Collection.objects.get(user=user).visibility == "PUBLIC"

    def test_existing_collection_visibility_untouched(self, user):
        Collection.objects.create(
            user=user, name="Showcase", slug="showcase", visibility="SECRET"
        )
        _model(_provider(user), "image", "image-model")
        _gen_image(user, {"visibility": "PUBLIC", "collection": "Showcase"})
        assert Collection.objects.get(user=user).visibility == "SECRET"

    def test_default_collection_from_account(self, user):
        user.default_collection_name = "My Stuff"
        user.save()
        _model(_provider(user), "image", "image-model")
        _gen_image(user)
        col = Collection.objects.get(user=user)
        assert col.name == "My Stuff"
        assert col.items.count() == 1

    def test_explicit_collection_beats_account_default(self, user):
        user.default_collection_name = "My Stuff"
        user.save()
        _model(_provider(user), "image", "image-model")
        _gen_image(user, {"collection": "Other"})
        assert set(
            Collection.objects.filter(user=user).values_list("name", flat=True)
        ) == {"Other"}

    def test_no_collection_when_unset(self, user):
        _model(_provider(user), "image", "image-model")
        _gen_image(user)
        assert not Collection.objects.filter(user=user).exists()


@pytest.mark.django_db
class TestCollectionNameApi:
    def test_post_existing_name_returns_existing(self, user):
        c = _client(user)
        url = reverse("inference:collection-list")
        a = c.post(url, {"name": "Dup"}, format="json")
        assert a.status_code == 201
        b = c.post(url, {"name": "dup"}, format="json")
        assert b.status_code == 200
        assert b.data["id"] == a.data["id"]
        assert Collection.objects.filter(user=user).count() == 1

    def test_rename_collision_rejected(self, user):
        Collection.objects.create(user=user, name="A", slug="a")
        Collection.objects.create(user=user, name="B", slug="b")
        c = _client(user)
        r = c.patch(
            reverse("inference:collection-detail", args=["b"]),
            {"name": "a"},
            format="json",
        )
        assert r.status_code == 400

    def test_rename_to_own_name_ok(self, user):
        Collection.objects.create(user=user, name="A", slug="a")
        c = _client(user)
        r = c.patch(
            reverse("inference:collection-detail", args=["a"]),
            {"name": "A", "description": "x"},
            format="json",
        )
        assert r.status_code == 200


@pytest.mark.django_db
class TestAccountDefaultCollectionSetting:
    def test_patch_and_read_back(self, user):
        c = _client(user)
        r = c.patch(
            "/api/account/", {"default_collection_name": "  Faves  "}, format="json"
        )
        assert r.status_code == 200
        assert r.data["default_collection_name"] == "Faves"
        assert c.get("/api/account/").data["default_collection_name"] == "Faves"

    def test_clearable(self, user):
        user.default_collection_name = "Faves"
        user.save()
        c = _client(user)
        r = c.patch("/api/account/", {"default_collection_name": ""}, format="json")
        assert r.status_code == 200
        assert r.data["default_collection_name"] == ""
