"""Central video compose (PRD 12 §5.5): the RENDER runner (real FFmpeg over
tiny inputs), the /v1/videos/compose enqueue, and central dispatch (no provider).
"""
import io
import wave

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from PIL import Image

from apps.inference import jobs, render
from apps.inference.models import InferenceRequest, MediaAsset

User = get_user_model()
pytestmark = pytest.mark.django_db


def _png(size=(64, 64), color=(40, 80, 160)):
    """A real, properly-sized solid-color PNG. A 1x1 PNG looped by FFmpeg
    triggers a parser-buffer overflow and hangs, so renders must run over an
    image of realistic dimensions — exactly what the IMAGE modality produces."""
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


PNG = _png()


def _wav(seconds=0.3, rate=8000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="compose@example.com", password="x")


def _asset(user, kind, data, ct, name):
    a = MediaAsset(user=user, kind=kind, content_type=ct, size_bytes=len(data))
    a.file.save(name, ContentFile(data), save=False)
    a.save()
    return a


def _media(user):
    imgs = [_asset(user, MediaAsset.OUTPUT_IMAGE, PNG, "image/png", f"i{i}.png") for i in range(2)]
    auds = [_asset(user, MediaAsset.OUTPUT_AUDIO, _wav(), "audio/wav", f"a{i}.wav") for i in range(2)]
    return imgs, auds


def _client(u):
    from rest_framework.test import APIClient
    c = APIClient()
    c.force_authenticate(user=u)
    return c


# --- the runner (real ffmpeg) ------------------------------------------------


def test_render_job_produces_a_video_with_provenance(user):
    imgs, auds = _media(user)
    ir = InferenceRequest.objects.create(
        user=user, inference_type="RENDER", status="PROCESSING",
        payload={"images": [i.id for i in imgs], "audio": [a.id for a in auds]},
    )
    ok, err = render.run_render_job(ir)
    assert ok, err
    ir.refresh_from_db()
    assert ir.status == "PROCESSED"
    vid = MediaAsset.objects.get(id=ir.results["video_asset_id"])
    assert vid.kind == MediaAsset.OUTPUT_VIDEO
    assert vid.size_bytes > 0
    assert vid.duration_seconds and vid.duration_seconds > 0
    assert ir.results["sections"] == 2
    # the video traces back to its section assets
    assert set(vid.derived_from.values_list("id", flat=True)) == {
        imgs[0].id, imgs[1].id, auds[0].id, auds[1].id
    }


def test_render_job_lays_a_music_bed_with_provenance(user):
    """V4: an optional music track is ducked under the narration; the video
    records it as metadata + provenance."""
    imgs, auds = _media(user)
    music = _asset(user, MediaAsset.OUTPUT_AUDIO, _wav(seconds=1.0), "audio/wav", "bed.wav")
    ir = InferenceRequest.objects.create(
        user=user, inference_type="RENDER", status="PROCESSING",
        payload={"images": [i.id for i in imgs], "audio": [a.id for a in auds],
                 "music": music.id},
    )
    ok, err = render.run_render_job(ir)
    assert ok, err
    vid = MediaAsset.objects.get(id=ir.results["video_asset_id"])
    assert vid.metadata.get("music") is True
    assert ir.results["music"] is True
    assert music.id in set(vid.derived_from.values_list("id", flat=True))


def test_render_job_accepts_step_output_dicts(user):
    """The workflow passes [{asset_id: N, ...}] lists, not bare ids."""
    imgs, auds = _media(user)
    ir = InferenceRequest.objects.create(
        user=user, inference_type="RENDER", status="PROCESSING",
        payload={
            "images": [{"asset_id": i.id, "url": "x"} for i in imgs],
            "audio": [{"asset_id": a.id} for a in auds],
        },
    )
    ok, err = render.run_render_job(ir)
    assert ok, err
    assert MediaAsset.objects.filter(
        inference_request=ir, kind=MediaAsset.OUTPUT_VIDEO).exists()


def test_caption_text_strips_speaker_tags_and_whitespace():
    """Burned-in subtitles must read as clean spoken text — no [S1]/[S2]."""
    assert render._caption_text("[S1] Hey, what's up?\n[S2]   Not much!  ") == \
        "Hey, what's up?\nNot much!"
    assert render._caption_text({"text": "  [S1] Single line.  "}) == "Single line."
    assert render._caption_text("[S1]") == ""


def test_render_job_without_assets_fails_cleanly(user):
    ir = InferenceRequest.objects.create(
        user=user, inference_type="RENDER", status="PROCESSING",
        payload={"images": [], "audio": []},
    )
    ok, err = render.run_render_job(ir)
    assert not ok and "images" in err


# --- the /v1/videos/compose endpoint ----------------------------------------


def test_compose_view_enqueues_a_render_job(user, settings):
    settings.ASYNC_ENABLED = True
    imgs, auds = _media(user)
    r = _client(user).post(
        "/v1/videos/compose",
        {"images": [i.id for i in imgs], "audio": [a.id for a in auds]},
        format="json",
    )
    assert r.status_code == 202, r.content
    job = InferenceRequest.objects.filter(inference_type="RENDER", is_async=True).latest("created_on")
    assert job.status == "QUEUED"
    assert job.job_service_type == "render"


def test_compose_view_requires_images_and_audio(user, settings):
    settings.ASYNC_ENABLED = True
    assert _client(user).post("/v1/videos/compose", {"images": []}, format="json").status_code == 400


# --- central dispatch (no provider) + execution ------------------------------


def test_render_dispatches_centrally_and_runs(user, settings):
    settings.ASYNC_ENABLED = True
    imgs, auds = _media(user)
    job = jobs.enqueue_job(
        user, "RENDER",
        {"images": [i.id for i in imgs], "audio": [a.id for a in auds]},
    )
    assert job.status == "QUEUED"

    claimed = jobs.dispatch_due_jobs()
    assert job.id in claimed  # claimed with NO provider (central)
    job.refresh_from_db()
    assert job.status == "PROCESSING" and job.provider_id is None

    jobs.run_job(job.id)
    job.refresh_from_db()
    assert job.status == "PROCESSED", job.error
    assert job.results.get("video_asset_id")
