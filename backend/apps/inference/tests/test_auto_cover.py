"""Automatic cover art for finished songs (apps/inference/covers.py)."""
from unittest.mock import patch

import pytest

from apps.inference import covers, jobs
from apps.inference.models import InferenceRequest

from test_async_jobs import _client, _image_resp, _service_model, user  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _on(settings):
    settings.ASYNC_ENABLED = True
    settings.AUTO_COVER_ART = True


@pytest.fixture(autouse=True)
def _no_broker():
    # No Celery in tests: jobs are run with process_jobs_inline.
    with patch("apps.inference.jobs.kick_dispatch"):
        yield


def _song(u, status="PROCESSED", **payload):
    return InferenceRequest.objects.create(
        user=u, inference_type="MUSIC", status=status, visibility="PUBLIC",
        payload={"prompt": "mellow lofi piano", **payload},
    )


def _cover_jobs(song):
    return InferenceRequest.objects.filter(idempotency_key=f"cover:{song.id}")


def test_finished_song_gets_a_cover(user, django_capture_on_commit_callbacks):  # noqa: F811
    _service_model(user, "image", "flux")
    with django_capture_on_commit_callbacks(execute=True):
        song = _song(user)

    job = _cover_jobs(song).get()
    assert job.inference_type == "IMAGE" and job.status == "QUEUED"
    assert job.payload["cover_for"] == song.id
    assert job.payload["size"] == "1024x1024"
    assert "mellow lofi piano" in job.payload["prompt"]
    assert job.visibility == "PUBLIC"

    with django_capture_on_commit_callbacks(execute=True):
        with patch("apps.inference.openai_views.requests.post", return_value=_image_resp()):
            jobs.process_jobs_inline()

    song.refresh_from_db()
    assert song.cover_request_id == job.id


def test_saving_the_song_again_does_not_queue_a_second_cover(user, django_capture_on_commit_callbacks):  # noqa: F811
    _service_model(user, "image", "flux")
    with django_capture_on_commit_callbacks(execute=True):
        song = _song(user)
        song.save()
        song.save(update_fields=["visibility"])
    assert _cover_jobs(song).count() == 1


def test_a_cover_chosen_by_hand_is_kept(user, django_capture_on_commit_callbacks):  # noqa: F811
    _service_model(user, "image", "flux")
    with django_capture_on_commit_callbacks(execute=True):
        song = _song(user)
    mine = InferenceRequest.objects.create(
        user=user, inference_type="IMAGE", status="PROCESSED", payload={}
    )
    InferenceRequest.objects.filter(id=song.id).update(cover_request=mine)

    with django_capture_on_commit_callbacks(execute=True):
        with patch("apps.inference.openai_views.requests.post", return_value=_image_resp()):
            jobs.process_jobs_inline()

    song.refresh_from_db()
    assert song.cover_request_id == mine.id


@pytest.mark.parametrize("status", ["PROCESSING", "QUEUED", "ERROR"])
def test_unfinished_songs_are_left_alone(user, status, django_capture_on_commit_callbacks):  # noqa: F811
    _service_model(user, "image", "flux")
    with django_capture_on_commit_callbacks(execute=True):
        song = _song(user, status=status)
    assert not _cover_jobs(song).exists()


def test_no_image_model_means_no_job(user, django_capture_on_commit_callbacks):  # noqa: F811
    with django_capture_on_commit_callbacks(execute=True):
        song = _song(user)
    assert not _cover_jobs(song).exists()


def test_switch_off(user, settings, django_capture_on_commit_callbacks):  # noqa: F811
    settings.AUTO_COVER_ART = False
    _service_model(user, "image", "flux")
    with django_capture_on_commit_callbacks(execute=True):
        song = _song(user)
    assert not _cover_jobs(song).exists()


def test_backfill_endpoint(user, django_capture_on_commit_callbacks):  # noqa: F811
    # Songs made before an image model existed.
    with django_capture_on_commit_callbacks(execute=True):
        songs = [_song(user) for _ in range(3)]
    _service_model(user, "image", "flux")
    c = _client(user)

    assert c.get("/api/inference/covers/missing/").json() == {"missing": 3}
    resp = c.post("/api/inference/covers/missing/", {"limit": 2}, format="json")
    assert resp.status_code == 202
    assert resp.json() == {"queued": 2, "missing": 1}
    assert sum(_cover_jobs(s).count() for s in songs) == 2


def test_prompt_varies_by_song_and_skips_structure_tags(user):  # noqa: F811
    a = _song(user, lyrics="[verse] rain on the window [chorus] stay")
    b = _song(user)
    pa, pb = covers.cover_prompt(a), covers.cover_prompt(b)
    assert "rain on the window" in pa and "[verse]" not in pa
    assert pa != pb
    assert "No text" in pa


# --- titles -------------------------------------------------------------------


class _Chat:
    status_code = 200

    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._text}}]}


def test_client_title_is_used_without_calling_a_model(user):  # noqa: F811
    song = _song(user, title="  Rain   Window ")
    with patch("requests.post") as post:
        assert covers.name_song(song.id) == "Rain Window"
    post.assert_not_called()
    song.refresh_from_db()
    assert song.title == "Rain Window"


def test_untitled_song_is_named_by_the_llm(user):  # noqa: F811
    _service_model(user, "llm", "nemo")
    song = _song(user)
    with patch("requests.post", return_value=_Chat('Title: "Quiet Hours."\nextra')):
        assert covers.name_song(song.id) == "Quiet Hours"
    song.refresh_from_db()
    assert song.title == "Quiet Hours"


def test_no_llm_leaves_the_song_untitled(user):  # noqa: F811
    song = _song(user)
    assert covers.name_song(song.id) == ""


def test_existing_title_is_not_replaced(user):  # noqa: F811
    _service_model(user, "llm", "nemo")
    song = _song(user)
    InferenceRequest.objects.filter(id=song.id).update(title="Mine")
    with patch("requests.post", return_value=_Chat("Other")) as post:
        assert covers.name_song(song.id) == ""
    post.assert_not_called()


def test_owner_can_rename(user):  # noqa: F811
    song = _song(user)
    c = _client(user)
    resp = c.patch(f"/api/inference/requests/{song.id}/title/", {"title": " New  Name "}, format="json")
    assert resp.status_code == 200 and resp.json() == {"title": "New Name"}
    listed = c.get("/api/inference/requests/?type=MUSIC").json()["results"][0]
    assert listed["title"] == "New Name"

    from django.contrib.auth import get_user_model
    other = get_user_model().objects.create_user(email="other@example.com", password="x")
    assert _client(other).patch(
        f"/api/inference/requests/{song.id}/title/", {"title": "x"}, format="json"
    ).status_code == 404
