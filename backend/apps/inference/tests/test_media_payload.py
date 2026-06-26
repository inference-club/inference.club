"""Inline-media slimming + rendering for stored chat payloads (PRD 17 §6).

The proxy must forward inline base64 to the model but store a slim, renderable
reference — these unit-test the pure helpers that do it, plus the serializer
that turns the stored refs back into renderable media.
"""
import pytest
from django.contrib.auth import get_user_model

from apps.inference.models import InferenceRequest, MediaAsset
from apps.inference.openai_views import (
    _bind_assets_to_request,
    _slim_payload_for_storage,
    _strip_asset_ids,
)
from apps.inference.serializers import _extract_messages

User = get_user_model()
pytestmark = pytest.mark.django_db

DATA_URL = "data:image/png;base64,iVBORw0KGgoAAAANSU"


def _img_part(url=DATA_URL, asset_id=None):
    p = {"type": "image_url", "image_url": {"url": url}}
    if asset_id:
        p["asset_id"] = asset_id
    return p


def _body(*parts, text="hi"):
    content = [{"type": "text", "text": text}, *parts]
    return {"model": "m", "messages": [{"role": "user", "content": content}]}


# --- slimming ---------------------------------------------------------------


def test_text_only_payload_is_untouched():
    body = {"model": "m", "messages": [{"role": "user", "content": "hello"}]}
    slim, ids = _slim_payload_for_storage(body)
    assert slim is body and ids == []


def test_base64_image_with_asset_id_is_slimmed():
    body = _body(_img_part(asset_id="abc123"))
    slim, ids = _slim_payload_for_storage(body)
    assert ids == ["abc123"]
    part = slim["messages"][0]["content"][1]
    assert part["image_url"]["url"] == "/api/inference/assets/abc123/"
    assert part["asset_id"] == "abc123"
    # the original body still carries the base64 — it's what we forward
    assert body["messages"][0]["content"][1]["image_url"]["url"] == DATA_URL


def test_base64_without_asset_id_is_stripped_but_unrenderable():
    body = _body(_img_part())
    slim, ids = _slim_payload_for_storage(body)
    assert ids == []
    part = slim["messages"][0]["content"][1]
    assert part["image_url"]["url"] == "[stored as asset]"


def test_audio_base64_is_slimmed_to_format_only():
    body = _body({"type": "input_audio", "input_audio": {"data": "AAAA", "format": "wav"}, "asset_id": "aud1"})
    slim, ids = _slim_payload_for_storage(body)
    assert ids == ["aud1"]
    part = slim["messages"][0]["content"][1]
    assert part["input_audio"] == {"format": "wav"}
    assert "data" not in part["input_audio"]


def test_strip_asset_ids_mutates_forward_body():
    body = _body(_img_part(asset_id="abc123"))
    _strip_asset_ids(body)
    assert "asset_id" not in body["messages"][0]["content"][1]
    # but the base64 stays for forwarding
    assert body["messages"][0]["content"][1]["image_url"]["url"] == DATA_URL


# --- rendering --------------------------------------------------------------


def test_extract_messages_surfaces_media_from_asset_ref():
    body = _body(_img_part(url="/api/inference/assets/abc123/", asset_id="abc123"))
    msgs = _extract_messages(body)
    assert msgs[0]["content"] == "hi"               # media dropped from text
    assert msgs[0]["media"] == [{"kind": "image", "url": "/api/inference/assets/abc123/"}]


def test_extract_messages_skips_unrenderable_base64():
    body = _body(_img_part())  # base64, no asset ref
    assert _extract_messages(body)[0]["media"] == []


def test_extract_messages_passes_through_plain_url():
    body = _body(_img_part(url="https://cdn.example.com/x.png"))
    assert _extract_messages(body)[0]["media"] == [
        {"kind": "image", "url": "https://cdn.example.com/x.png"}
    ]


# --- binding ----------------------------------------------------------------


@pytest.fixture
def owner(db):
    return User.objects.create_user(email="owner@ex.com", password="x")


def _asset(user, public_id, request=None):
    a = MediaAsset(user=user, kind=MediaAsset.INPUT_IMAGE, inference_request=request,
                   file=f"input_image/{public_id}.png")
    a.public_id = public_id
    a.save()
    return a


def test_bind_homes_unbound_owner_assets(owner):
    a = _asset(owner, "p1")
    ir = InferenceRequest.objects.create(user=owner, inference_type="LLM", payload={}, status="PROCESSING")
    _bind_assets_to_request(owner, ir, ["p1"])
    a.refresh_from_db()
    assert a.inference_request_id == ir.id


def test_bind_leaves_already_homed_and_other_users(owner):
    other = User.objects.create_user(email="other@ex.com", password="x")
    first = InferenceRequest.objects.create(user=owner, inference_type="LLM", payload={}, status="PROCESSED")
    a = _asset(owner, "p2", request=first)            # already homed
    b = _asset(other, "p3")                            # someone else's
    second = InferenceRequest.objects.create(user=owner, inference_type="LLM", payload={}, status="PROCESSING")
    _bind_assets_to_request(owner, second, ["p2", "p3"])
    a.refresh_from_db(); b.refresh_from_db()
    assert a.inference_request_id == first.id          # not re-homed
    assert b.inference_request_id is None              # not touched (other user)
