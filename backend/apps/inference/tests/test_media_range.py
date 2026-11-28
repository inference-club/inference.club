"""Byte-range serving on the gated asset route.

Media elements need 206 responses to seek, and Safari will not play audio or
video at all from a server that ignores ``Range``.
"""
import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from apps.inference.models import InferenceRequest, MediaAsset
from apps.inference.views import _parse_byte_range

User = get_user_model()
pytestmark = pytest.mark.django_db

BODY = bytes(range(256)) * 4  # 1024 distinct-ish bytes


@pytest.fixture
def asset_url(db):
    owner = User.objects.create_user(email="range@ex.com", password="x")
    ir = InferenceRequest.objects.create(
        user=owner, inference_type="MUSIC", payload={}, status="PROCESSED",
        visibility="PUBLIC",
    )
    asset = MediaAsset(
        user=owner, inference_request=ir, kind=MediaAsset.OUTPUT_AUDIO,
        content_type="audio/mpeg",
    )
    asset.file.save("song.mp3", ContentFile(BODY), save=False)
    asset.save()
    return f"/api/inference/assets/{asset.public_id}/"


def body(resp):
    return b"".join(resp.streaming_content) if resp.streaming else resp.content


def test_whole_file_advertises_ranges(asset_url):
    resp = APIClient().get(asset_url)
    assert resp.status_code == 200
    assert resp["Accept-Ranges"] == "bytes"
    assert int(resp["Content-Length"]) == len(BODY)
    assert body(resp) == BODY


@pytest.mark.parametrize(
    "header, start, end",
    [
        ("bytes=0-1", 0, 1),  # Safari's first probe
        ("bytes=100-199", 100, 199),
        ("bytes=1000-", 1000, 1023),
        ("bytes=-24", 1000, 1023),
        ("bytes=1000-5000", 1000, 1023),  # end clamps to the file
    ],
)
def test_partial_content(asset_url, header, start, end):
    resp = APIClient().get(asset_url, HTTP_RANGE=header)
    assert resp.status_code == 206
    assert resp["Content-Range"] == f"bytes {start}-{end}/{len(BODY)}"
    assert int(resp["Content-Length"]) == end - start + 1
    assert body(resp) == BODY[start : end + 1]


def test_range_past_the_end_is_416(asset_url):
    resp = APIClient().get(asset_url, HTTP_RANGE="bytes=5000-6000")
    assert resp.status_code == 416
    assert resp["Content-Range"] == f"bytes */{len(BODY)}"


@pytest.mark.parametrize("header", ["bytes=0-1,5-9", "items=0-1", "bytes=abc-", ""])
def test_unusable_ranges_fall_back_to_the_whole_file(asset_url, header):
    resp = APIClient().get(asset_url, HTTP_RANGE=header)
    assert resp.status_code == 200
    assert body(resp) == BODY


def test_parse_byte_range():
    assert _parse_byte_range("bytes=0-0", 10) == (0, 0)
    assert _parse_byte_range("bytes=-0", 10) is False
    assert _parse_byte_range("bytes=10-", 10) is False
    assert _parse_byte_range(None, 10) is None
