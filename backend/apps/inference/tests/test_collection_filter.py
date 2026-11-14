"""``?collection=`` on the request list endpoints (issue #16): requests filed
into a collection via the /v1 ``"collection"`` body field can be narrowed to
that collection in the gallery and the request history."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.inference.models import InferenceRequest
from apps.inference.sharing import file_into_collection

User = get_user_model()


def _ids(resp):
    assert resp.status_code == 200, resp.content
    return {r["id"] for r in resp.json()["results"]}


@pytest.fixture
def alice(db):
    return User.objects.create_user(email="alice@example.com", password="pw")


@pytest.fixture
def bob(db):
    return User.objects.create_user(email="bob@example.com", password="pw")


def _make(user, n, collection, itype="IMAGE"):
    out = []
    for i in range(n):
        ir = InferenceRequest.objects.create(
            user=user,
            inference_type=itype,
            payload={"prompt": f"{collection} {i}"},
            visibility="PUBLIC",
        )
        file_into_collection(user, ir, collection)
        out.append(ir.id)
    return set(out)


@pytest.fixture
def filed(alice):
    cats = _make(alice, 2, "Cat Pictures")
    dogs = _make(alice, 3, "Dogs")
    return cats, dogs


@pytest.mark.django_db
class TestCollectionFilter:
    def test_history_filters_by_slug_and_name(self, alice, filed):
        cats, dogs = filed
        c = APIClient()
        c.force_authenticate(alice)
        url = reverse("inference:inference-requests")
        assert _ids(c.get(url)) == cats | dogs
        assert _ids(c.get(url, {"collection": "cat-pictures"})) == cats
        assert _ids(c.get(url, {"collection": "dogs"})) == dogs  # name, case-insensitive
        assert _ids(c.get(url, {"collection": "Cat Pictures"})) == cats

    def test_gallery_composes_with_type_filter(self, alice, filed):
        cats, dogs = filed
        c = APIClient()
        c.force_authenticate(alice)
        url = reverse("inference:inference-requests-all")
        assert _ids(c.get(url, {"type": "IMAGE", "collection": "dogs"})) == dogs
        assert _ids(c.get(url, {"type": "LLM", "collection": "dogs"})) == set()

    def test_unknown_collection_is_empty(self, alice, filed):
        c = APIClient()
        c.force_authenticate(alice)
        url = reverse("inference:inference-requests-all")
        assert _ids(c.get(url, {"collection": "nope"})) == set()

    def test_only_the_callers_collections_match(self, alice, bob, filed):
        _make(bob, 1, "Dogs")
        c = APIClient()
        c.force_authenticate(bob)
        url = reverse("inference:inference-requests-all")
        bob_dogs = _ids(c.get(url, {"collection": "dogs"}))
        assert len(bob_dogs) == 1
        assert not bob_dogs & filed[1]

    def test_anonymous_collection_filter_is_empty(self, filed):
        url = reverse("inference:inference-requests-all")
        assert _ids(APIClient().get(url, {"collection": "dogs"})) == set()
