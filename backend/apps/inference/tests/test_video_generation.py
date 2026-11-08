"""Video generation: the /v1/videos/generations proxy (text/image → MP4). The
agent forwards the JSON body to the LTX server's POST /generate and streams the
MP4 back, so from the backend's view it's a single forward that returns video
bytes — like music/TTS. We mock the agent's reply: service-type routing, public
output video, the forwarded LTX request shape, control clamping, the optional
first-frame image (stored as a public INPUT_IMAGE), and duration from the
resolved X-LTX-Params. Upstream is mocked.
"""
import base64
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.inference.models import (
    InferenceRequest, MediaAsset, Provider, ProviderModel, ProviderService, link_catalog_model,
)
from apps.inference.openai_views import _find_provider_for_model

User = get_user_model()

# A 1x1 PNG, used as the optional first-frame conditioning image.
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture
def user(db):
    return User.objects.create_user(email="video@example.com", password="x")


def _video_model(u, name="ltx-2"):
    p = Provider.objects.create(
        user=u, name="node", tailnet_hostname="n1",
        is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
    )
    svc = ProviderService.objects.create(
        provider=p, name="ltx2-video", engine="other", service_type="video",
        access_policy=ProviderService.ACCESS_AUTHENTICATED,
    )
    pm = ProviderModel(provider=p, name=name, service=svc)
    link_catalog_model(pm)
    pm.save()
    return pm


def _client(u):
    from rest_framework.test import APIClient
    c = APIClient()
    c.force_authenticate(user=u)
    return c


class _FakeVideoResp:
    def __init__(self, content, status=200, content_type="video/mp4", ltx_params=None):
        self.content = content
        self.status_code = status
        self.ok = 200 <= status < 300
        self.headers = {"content-type": content_type}
        if ltx_params is not None:
            self.headers["X-LTX-Params"] = json.dumps(ltx_params)
        self.text = content.decode("utf-8", "replace") if isinstance(content, bytes) else ""

    def json(self):
        return json.loads(self.content)


# --- routing ---------------------------------------------------------------


class TestVideoRouting:
    def test_video_request_only_matches_video(self, user):
        _video_model(user)
        assert _find_provider_for_model(user, "ltx-2", service_type="video") is not None
        assert _find_provider_for_model(user, "ltx-2", service_type="image") is None


# --- /v1/videos/generations ------------------------------------------------


class TestVideoGenerations:
    def test_happy_path_returns_video_and_stores(self, user):
        _video_model(user)
        mp4 = b"\x00\x00\x00\x18ftypmp42FAKEMP4BYTES"
        resp_obj = _FakeVideoResp(mp4, ltx_params={"num_frames": 121, "fps": 24, "width": 1280, "height": 704})
        with patch("apps.inference.openai_views.requests.post", return_value=resp_obj):
            resp = _client(user).post(
                "/v1/videos/generations",
                {"model": "ltx-2", "prompt": "a fox trotting through snow"},
                format="json",
            )
        assert resp.status_code == 200
        assert resp["content-type"] == "video/mp4"
        assert resp.content == mp4
        ir = InferenceRequest.objects.get(user=user, inference_type="VIDEO")
        assert ir.status == "PROCESSED"
        # 121 frames / 24 fps ≈ 5.04s
        assert ir.audio_seconds == pytest.approx(121 / 24, abs=0.01)
        assert ir.results["params"]["width"] == 1280
        assert MediaAsset.objects.filter(user=user, kind="OUTPUT_VIDEO").count() == 1

    def test_forwards_ltx_fields_and_clamps(self, user):
        _video_model(user)
        captured = {}

        def _cap(url, **kw):
            captured["url"] = url
            captured["json"] = kw.get("json")
            return _FakeVideoResp(b"mp4")

        with patch("apps.inference.openai_views.requests.post", side_effect=_cap):
            _client(user).post(
                "/v1/videos/generations",
                {
                    "model": "ltx-2",
                    "prompt": "neon city flythrough",
                    "negative_prompt": "blurry",
                    "duration": 999,  # clamped to 20
                    "fps": 24,
                    "width": 1280,
                    "height": 704,
                    "guidance_scale": 3,
                    "seed": 42,
                    "use_random_seed": False,
                    "enhance_prompt": True,
                },
                format="json",
            )
        body = captured["json"]
        assert captured["url"].endswith("/videos/generations")
        assert body["prompt"] == "neon city flythrough"
        assert body["negative_prompt"] == "blurry"
        assert body["duration"] == 20  # clamped
        assert body["fps"] == 24
        assert body["width"] == 1280
        assert body["seed"] == 42
        assert body["enhance_prompt"] is True
        assert "image" not in body  # text-to-video: no conditioning image

    def test_image_to_video_stores_first_frame(self, user):
        _video_model(user)
        data_uri = "data:image/png;base64," + base64.b64encode(_PNG_1PX).decode("ascii")
        captured = {}

        def _cap(url, **kw):
            captured["json"] = kw.get("json")
            return _FakeVideoResp(b"mp4")

        with patch("apps.inference.openai_views.requests.post", side_effect=_cap):
            _client(user).post(
                "/v1/videos/generations",
                {"model": "ltx-2", "prompt": "make it move", "image": data_uri, "image_strength": 0.8},
                format="json",
            )
        # The conditioning image is forwarded verbatim and stored as INPUT_IMAGE.
        assert captured["json"]["image"] == data_uri
        assert captured["json"]["image_strength"] == 0.8
        ir = InferenceRequest.objects.get(user=user, inference_type="VIDEO")
        assert ir.payload["has_image"] is True
        assert MediaAsset.objects.filter(inference_request=ir, kind="INPUT_IMAGE").count() == 1

    def test_missing_prompt_400(self, user):
        _video_model(user)
        resp = _client(user).post("/v1/videos/generations", {"model": "ltx-2"}, format="json")
        assert resp.status_code == 400

    def test_no_video_provider_404(self, user):
        resp = _client(user).post(
            "/v1/videos/generations", {"model": "nope", "prompt": "hi"}, format="json"
        )
        assert resp.status_code == 404

    def test_upstream_error_passthrough(self, user):
        _video_model(user)
        with patch(
            "apps.inference.openai_views.requests.post",
            return_value=_FakeVideoResp(b'{"error": "boom"}', status=502, content_type="application/json"),
        ):
            resp = _client(user).post(
                "/v1/videos/generations", {"model": "ltx-2", "prompt": "x"}, format="json"
            )
        assert resp.status_code == 502


# --- public output video ---------------------------------------------------


class TestPublicOutputVideo:
    def test_output_video_public(self, user):
        from rest_framework.test import APIClient
        _video_model(user)
        with patch("apps.inference.openai_views.requests.post", return_value=_FakeVideoResp(b"mp4bytes")):
            _client(user).post(
                "/v1/videos/generations",
                {"model": "ltx-2", "prompt": "ocean waves"},
                format="json",
            )
        asset = MediaAsset.objects.get(user=user, kind="OUTPUT_VIDEO")
        # Anonymous can fetch a generated video (public by URL).
        resp = APIClient().get(f"/api/inference/assets/{asset.id}/")
        assert resp.status_code == 200


def test_normalize_prompt_punct_maps_smart_punctuation_to_ascii():
    """LTX-2 encodes prompts as latin-1 and 500s on smart punctuation; the
    video runner normalizes it first (regression for the workflow video step)."""
    from apps.inference.openai_views import _normalize_prompt_punct

    out = _normalize_prompt_punct("A time‑lapse — “gazebo”… piece‑by‑piece")
    assert out == 'A time-lapse - "gazebo"... piece-by-piece'
    # whole result is latin-1 encodable now (what LTX-2 needs)
    out.encode("latin-1")
    # genuine non-latin text (CJK) is left untouched
    assert _normalize_prompt_punct("東京") == "東京"
    assert _normalize_prompt_punct(None) is None


# --- LTX-2.5 inputs: keyframes, audio, video, LoRA, asset references ---------


_WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 28
_MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32


def _capture():
    captured = {}

    def _post(url, **kw):
        captured["json"] = kw.get("json")
        captured["timeout"] = kw.get("timeout")
        return _FakeVideoResp(b"MP4DATA", ltx_params={"mode": "a2v", "num_frames": 97, "fps": 24,
                                                      "duration": 4.04, "width": 768, "height": 448})
    return captured, _post


class TestLtx25Inputs:
    def test_asset_refs_inline_forward_and_record_provenance(self, user, settings):
        """A song (OUTPUT_AUDIO) and a FLUX image (OUTPUT_IMAGE) from earlier
        generations feed audio-to-video by reference: inlined upstream as data
        URIs, recorded in the payload, linked as the output's derived_from."""
        from django.core.files.base import ContentFile

        _video_model(user, name="ltx-2.5")
        song = MediaAsset(user=user, kind=MediaAsset.OUTPUT_AUDIO, content_type="audio/wav", size_bytes=len(_WAV))
        song.file.save("song.wav", ContentFile(_WAV), save=False)
        song.save()
        img = MediaAsset(user=user, kind=MediaAsset.OUTPUT_IMAGE, content_type="image/png", size_bytes=len(_PNG_1PX))
        img.file.save("img.png", ContentFile(_PNG_1PX), save=False)
        img.save()
        captured, post = _capture()
        with patch("apps.inference.openai_views.requests.post", side_effect=post):
            resp = _client(user).post("/v1/videos/generations", {
                "model": "ltx-2.5", "prompt": "a jazz singer sings", "mode": "a2v",
                "audio": f"asset:{song.public_id}", "image": {"asset": img.public_id},
                "duration": 4,
            }, format="json")
        assert resp.status_code == 200, resp.content
        sent = captured["json"]
        assert sent["mode"] == "a2v"
        assert sent["audio"].startswith("data:audio/wav;base64,")
        assert sent["image"].startswith("data:image/png;base64,")
        assert captured["timeout"] == settings.VIDEO_UPSTREAM_TIMEOUT_SECONDS
        ir = InferenceRequest.objects.get(user=user, inference_type="VIDEO")
        assert ir.payload["inputs"] == [{"role": "audio", "asset": song.public_id}]
        assert ir.payload["image_asset"] == img.public_id
        assert "base64" not in json.dumps(ir.payload)
        out = MediaAsset.objects.get(inference_request=ir, kind=MediaAsset.OUTPUT_VIDEO)
        assert set(out.derived_from.values_list("id", flat=True)) == {song.id, img.id}
        assert out.duration_seconds == 4.04 and out.metadata["mode"] == "a2v"

    def test_inline_keyframes_and_video_stored_as_inputs(self, user):
        _video_model(user, name="ltx-2.5")
        png = "data:image/png;base64," + base64.b64encode(_PNG_1PX).decode()
        captured, post = _capture()
        with patch("apps.inference.openai_views.requests.post", side_effect=post):
            resp = _client(user).post("/v1/videos/generations", {
                "model": "ltx-2.5", "prompt": "day turns to storm",
                "images": [{"image": png, "position": "first"}, {"image": png, "position": "last", "strength": 0.8}],
                "video": "data:video/mp4;base64," + base64.b64encode(_MP4).decode(),
                "lora": "day-to-night", "lora_strength": 0.9,
            }, format="json")
        assert resp.status_code == 200, resp.content
        sent = captured["json"]
        assert [i["position"] for i in sent["images"]] == ["first", "last"]
        assert sent["images"][1]["strength"] == 0.8
        assert sent["lora"] == "day-to-night" and sent["lora_strength"] == 0.9
        ir = InferenceRequest.objects.get(user=user, inference_type="VIDEO")
        roles = [r["role"] for r in ir.payload["inputs"]]
        assert roles == ["keyframe", "keyframe", "video"]
        assert MediaAsset.objects.filter(inference_request=ir, kind=MediaAsset.INPUT_IMAGE).count() == 2
        assert MediaAsset.objects.filter(inference_request=ir, kind=MediaAsset.INPUT_VIDEO).count() == 1

    @pytest.mark.parametrize("body,msg", [
        ({"mode": "warp"}, "mode"),
        ({"lora": "../etc"}, "lora"),
        ({"images": [{"nope": 1}]}, "images[0]"),
        ({"audio": "asset:doesnotexist"}, "not found"),
        ({"retake_start": 3, "retake_end": 2}, "retake_end"),
    ])
    def test_invalid_inputs_400(self, user, body, msg):
        _video_model(user, name="ltx-2.5")
        with patch("apps.inference.openai_views.requests.post") as post:
            resp = _client(user).post("/v1/videos/generations",
                                      {"model": "ltx-2.5", "prompt": "x", **body}, format="json")
        assert resp.status_code == 400 and msg in resp.json()["error"]["message"]
        post.assert_not_called()

    def test_other_users_private_asset_rejected(self, user):
        from django.core.files.base import ContentFile

        other = User.objects.create_user(email="other@example.com", password="x")
        a = MediaAsset(user=other, kind=MediaAsset.INPUT_AUDIO, content_type="audio/wav", visibility="SECRET")
        a.file.save("x.wav", ContentFile(_WAV), save=False)
        a.save()
        _video_model(user, name="ltx-2.5")
        resp = _client(user).post("/v1/videos/generations",
                                  {"model": "ltx-2.5", "prompt": "x", "audio": f"asset:{a.public_id}"}, format="json")
        assert resp.status_code == 400

    def test_text_to_audio_stored_as_output_audio(self, user):
        _video_model(user, name="ltx-2.5")
        with patch("apps.inference.openai_views.requests.post",
                   return_value=_FakeVideoResp(_WAV, content_type="audio/wav",
                                               ltx_params={"mode": "t2a", "duration": 5.0})):
            resp = _client(user).post("/v1/videos/generations",
                                      {"model": "ltx-2.5", "prompt": "rain on a tin roof", "mode": "t2a"}, format="json")
        assert resp.status_code == 200 and resp["Content-Type"] == "audio/wav"
        ir = InferenceRequest.objects.get(user=user, inference_type="VIDEO")
        assert MediaAsset.objects.filter(inference_request=ir, kind=MediaAsset.OUTPUT_AUDIO).count() == 1
