"""Narration pipeline primitives (PRD 12 V3): word normalization, the central
FFmpeg TRIM runner (real ffmpeg over silence/pauses), and transcription grading.
"""
import io
import math
import struct
import wave

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

from apps.inference import jobs, narration
from apps.inference.models import InferenceRequest, MediaAsset

User = get_user_model()
pytestmark = pytest.mark.django_db


def _wav(segments, rate=16000):
    """Build a mono WAV from ``segments`` = [(seconds, freq)]; freq 0 = silence."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for secs, freq in segments:
            for i in range(int(rate * secs)):
                s = int(0.4 * 32767 * math.sin(2 * math.pi * freq * i / rate)) if freq else 0
                frames += struct.pack("<h", s)
        w.writeframes(bytes(frames))
    return buf.getvalue()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="narr@example.com", password="x")


# --- word normalization ------------------------------------------------------


def test_normalize_words_accepts_both_shapes_and_seconds():
    riva = [{"word": "hi", "start_ms": 500, "duration_ms": 500}]
    assert narration.normalize_words(riva) == [{"word": "hi", "start": 0.5, "end": 1.0}]
    openai = {"words": [{"text": "yo", "start": 1.0, "end": 1.4}, {"word": "", "start": 2}]}
    assert narration.normalize_words(openai) == [{"word": "yo", "start": 1.0, "end": 1.4}]
    assert narration.normalize_words(None) == []


def test_plan_trim_intervals_trims_edges_and_collapses_gaps():
    words = [{"word": "a", "start": 0.5, "end": 1.0}, {"word": "b", "start": 2.0, "end": 2.5}]
    ivals = narration.plan_trim_intervals(words, 3.0)
    # two kept ranges around the two words; the 1.0s mid gap is collapsed
    assert len(ivals) == 2
    assert ivals[0][0] == pytest.approx(0.44, abs=0.01)   # head trimmed (0.5 - pad)
    assert ivals[-1][1] == pytest.approx(2.56, abs=0.01)  # tail trimmed (2.5 + pad)
    kept = sum(b - a for a, b in ivals)
    assert kept < 1.6                                     # ~1.4s vs 3.0s source
    assert narration.plan_trim_intervals([], 3.0) == []  # no words → no-op


# --- central TRIM runner (real ffmpeg) ---------------------------------------


def _audio_asset(user, data):
    a = MediaAsset(user=user, kind=MediaAsset.OUTPUT_AUDIO, content_type="audio/wav",
                   size_bytes=len(data))
    a.file.save("src.wav", ContentFile(data), save=False)
    a.save()
    return a


def test_trim_job_removes_silence_and_pauses(user):
    src = _audio_asset(user, _wav([(0.5, 0), (0.5, 440), (1.0, 0), (0.5, 440), (0.5, 0)]))
    ir = InferenceRequest.objects.create(
        user=user, inference_type="TRIM", status="PROCESSING",
        payload={"audio_asset_id": src.id,
                 "words": [{"word": "a", "start": 0.5, "end": 1.0},
                           {"word": "b", "start": 2.0, "end": 2.5}]},
    )
    ok, err = narration.run_trim_job(ir)
    assert ok, err
    ir.refresh_from_db()
    out = MediaAsset.objects.get(id=ir.results["audio_asset_id"])
    assert out.kind == MediaAsset.OUTPUT_AUDIO
    assert 1.0 < out.duration_seconds < 1.9         # 3.0s source trimmed to ~1.4s
    assert ir.results["source_duration"] > out.duration_seconds
    assert src.id in set(out.derived_from.values_list("id", flat=True))


def test_trim_job_without_words_passes_audio_through(user):
    src = _audio_asset(user, _wav([(1.0, 440)]))
    ir = InferenceRequest.objects.create(
        user=user, inference_type="TRIM", status="PROCESSING",
        payload={"audio_asset_id": src.id, "words": []},
    )
    ok, err = narration.run_trim_job(ir)
    assert ok, err
    ir.refresh_from_db()
    assert MediaAsset.objects.filter(id=ir.results["audio_asset_id"]).exists()


def test_trim_dispatches_centrally_and_runs(user, settings):
    settings.ASYNC_ENABLED = True
    src = _audio_asset(user, _wav([(0.4, 0), (0.6, 330), (0.4, 0)]))
    job = jobs.enqueue_job(user, "TRIM", {
        "audio_asset_id": src.id,
        "words": [{"word": "x", "start": 0.4, "end": 1.0}],
    })
    claimed = jobs.dispatch_due_jobs()
    assert job.id in claimed
    job.refresh_from_db()
    assert job.status == "PROCESSING" and job.provider_id is None  # central
    jobs.run_job(job.id)
    job.refresh_from_db()
    assert job.status == "PROCESSED", job.error


# --- grading -----------------------------------------------------------------


def test_fallback_grade_scores_similarity():
    good = narration.fallback_grade("the quick brown fox", "the quick brown fox")
    assert good["score"] == pytest.approx(10.0) and good["should_regenerate"] is False
    bad = narration.fallback_grade("the quick brown fox", "completely different words here")
    assert bad["score"] < 8.0 and bad["should_regenerate"] is True


def test_grade_transcription_falls_back_without_llm(user):
    # No LLM provider for this user → grade_transcription uses the similarity path.
    res = narration.grade_transcription(user, "hello world", "hello world")
    assert res["method"] == "similarity" and res["score"] == pytest.approx(10.0)
    guard = narration.grade_transcription(user, "", "x")
    assert guard["method"] == "guard" and guard["should_regenerate"] is True
