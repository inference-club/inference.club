"""Narration Studio data spine (PRD 12 §5.4): Episode/Segment/Variant CRUD,
reorder, segment-edit undo stash, and selecting the active take. Owner-scoped."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.inference.models import Episode, Segment, Variant

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user(email="studio@example.com", password="x")


@pytest.fixture
def client(owner):
    c = APIClient()
    c.force_authenticate(owner)
    return c


# --- episodes ----------------------------------------------------------------


def test_create_list_and_get_episode(client):
    r = client.post("/v1/episodes", {"title": "My show", "description": "hi"}, format="json")
    assert r.status_code == 201
    eid = r.json()["id"]

    lst = client.get("/v1/episodes").json()["data"]
    assert any(e["id"] == eid and e["segment_count"] == 0 for e in lst)

    detail = client.get(f"/v1/episodes/{eid}").json()
    assert detail["title"] == "My show" and detail["segments"] == []


def test_episode_requires_title(client):
    assert client.post("/v1/episodes", {"description": "x"}, format="json").status_code == 400


def test_patch_and_delete_episode(client):
    eid = client.post("/v1/episodes", {"title": "A"}, format="json").json()["id"]
    assert client.patch(f"/v1/episodes/{eid}", {"title": "B"}, format="json").json()["title"] == "B"
    assert client.delete(f"/v1/episodes/{eid}").status_code == 204
    assert client.get(f"/v1/episodes/{eid}").status_code == 404


# --- segments ----------------------------------------------------------------


def test_add_segments_get_sequential_positions(client):
    eid = client.post("/v1/episodes", {"title": "A"}, format="json").json()["id"]
    s1 = client.post(f"/v1/episodes/{eid}/segments", {"text": "one"}, format="json").json()
    s2 = client.post(f"/v1/episodes/{eid}/segments", {"text": "two"}, format="json").json()
    assert s1["position"] == 0 and s2["position"] == 1


def test_editing_text_stashes_original_once(client):
    eid = client.post("/v1/episodes", {"title": "A"}, format="json").json()["id"]
    sid = client.post(f"/v1/episodes/{eid}/segments", {"text": "first"}, format="json").json()["id"]
    r1 = client.patch(f"/v1/segments/{sid}", {"text": "second"}, format="json").json()
    assert r1["text"] == "second" and r1["original_text"] == "first"
    # a second edit keeps the ORIGINAL original, not the intermediate
    r2 = client.patch(f"/v1/segments/{sid}", {"text": "third"}, format="json").json()
    assert r2["original_text"] == "first"


def test_reorder_segments(client):
    eid = client.post("/v1/episodes", {"title": "A"}, format="json").json()["id"]
    a = client.post(f"/v1/episodes/{eid}/segments", {"text": "a"}, format="json").json()["id"]
    b = client.post(f"/v1/episodes/{eid}/segments", {"text": "b"}, format="json").json()["id"]
    c = client.post(f"/v1/episodes/{eid}/segments", {"text": "c"}, format="json").json()["id"]
    ep = client.post(f"/v1/episodes/{eid}/segments/reorder", {"order": [c, a, b]}, format="json").json()
    by_id = {s["id"]: s["position"] for s in ep["segments"]}
    assert by_id[c] == 0 and by_id[a] == 1 and by_id[b] == 2


def test_delete_segment(client):
    eid = client.post("/v1/episodes", {"title": "A"}, format="json").json()["id"]
    sid = client.post(f"/v1/episodes/{eid}/segments", {"text": "x"}, format="json").json()["id"]
    assert client.delete(f"/v1/segments/{sid}").status_code == 204
    assert client.get(f"/v1/episodes/{eid}").json()["segments"] == []


# --- variants / take selection ----------------------------------------------


def test_select_variant_marks_segment_ready(client, owner):
    eid = client.post("/v1/episodes", {"title": "A"}, format="json").json()["id"]
    sid = client.post(f"/v1/episodes/{eid}/segments", {"text": "hi"}, format="json").json()["id"]
    seg = Segment.objects.get(id=sid)
    v1 = Variant.objects.create(segment=seg, text="hi")
    v2 = Variant.objects.create(segment=seg, text="hi")

    out = client.post(f"/v1/segments/{sid}/variants/{v2.id}/select", format="json").json()
    assert out["selected_variant_id"] == v2.id
    assert out["status"] == "ready"
    assert {v["id"] for v in out["variants"]} == {v1.id, v2.id}


def test_cannot_select_a_variant_from_another_segment(client):
    eid = client.post("/v1/episodes", {"title": "A"}, format="json").json()["id"]
    s1 = client.post(f"/v1/episodes/{eid}/segments", {"text": "a"}, format="json").json()["id"]
    s2 = client.post(f"/v1/episodes/{eid}/segments", {"text": "b"}, format="json").json()["id"]
    foreign = Variant.objects.create(segment=Segment.objects.get(id=s2), text="b")
    assert client.post(f"/v1/segments/{s1}/variants/{foreign.id}/select", format="json").status_code == 404


# --- ownership ---------------------------------------------------------------


def test_episodes_are_owner_scoped(client, owner):
    eid = client.post("/v1/episodes", {"title": "secret"}, format="json").json()["id"]
    other = User.objects.create_user(email="intruder@example.com", password="x")
    c2 = APIClient()
    c2.force_authenticate(other)
    assert c2.get(f"/v1/episodes/{eid}").status_code == 404
    assert eid not in [e["id"] for e in c2.get("/v1/episodes").json()["data"]]
