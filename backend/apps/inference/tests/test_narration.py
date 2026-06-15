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


# --- per-segment orchestrator + endpoint -------------------------------------

import json as _json
from unittest.mock import patch
from apps.inference.models import (Episode, Provider, ProviderModel,
                                   ProviderService, Segment, Variant, link_catalog_model)


class _FakeResp:
    def __init__(self, content=b"", status=200, content_type="application/json"):
        self.content = content if isinstance(content, bytes) else _json.dumps(content).encode()
        self.status_code = status
        self.ok = 200 <= status < 300
        self.headers = {"content-type": content_type}
        self.text = self.content.decode(errors="replace")

    def json(self):
        return _json.loads(self.content)


def _service_model(u, service_type, model_name, features=None):
    p = Provider.objects.create(
        user=u, name=f"n-{service_type}", tailnet_hostname=f"h-{service_type}",
        is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
    )
    svc = ProviderService.objects.create(
        provider=p, name=f"{service_type}-svc", engine="other",
        service_type=service_type, access_policy=ProviderService.ACCESS_AUTHENTICATED,
        declared_features=features or [],
    )
    pm = ProviderModel(provider=p, name=model_name, service=svc)
    link_catalog_model(pm)
    pm.save()
    return p


from django.utils import timezone  # noqa: E402  (used by _service_model)


def _segment_with_audio(user, text):
    ep = Episode.objects.create(user=user, title="ep")
    seg = Segment.objects.create(episode=ep, position=0, text=text)
    audio = _audio_asset(user, _wav([(0.4, 0), (0.6, 440), (0.4, 0)]))  # 1.4s, speech 0.4–1.0
    v = Variant.objects.create(segment=seg, text=text, audio=audio, duration_seconds=1.4)
    seg.selected_variant = v
    seg.save(update_fields=["selected_variant"])
    return seg, v, audio


def test_process_segment_runs_full_pipeline(user):
    _service_model(user, "audio-enhance", "maxine-studio-voice")
    _service_model(user, "stt", "qwen3-asr")
    text = "the quick brown fox jumps"
    seg, variant, original = _segment_with_audio(user, text)
    cleaned_wav = _wav([(0.4, 0), (0.6, 330), (0.4, 0)])
    words = [{"word": w, "start": round(0.4 + i * 0.1, 3), "end": round(0.5 + i * 0.1, 3)}
             for i, w in enumerate(text.split())]

    def _post(url, **kw):
        if "audio/enhance" in url:
            return _FakeResp(cleaned_wav, content_type="audio/wav")
        if "audio/transcriptions" in url:
            return _FakeResp({"text": text, "words": words})
        return _FakeResp({})

    with patch("apps.inference.openai_views.requests.post", side_effect=_post):
        res = narration.process_segment(seg)
    assert res["ok"], res
    seg.refresh_from_db()
    variant.refresh_from_db()
    assert variant.clean_status == Variant.CLEAN_DONE
    assert variant.cleaned_audio_id and variant.cleaned_audio_id != original.id  # trimmed copy
    assert variant.cleaned_audio.duration_seconds < 1.4                          # silence trimmed
    assert variant.words and variant.transcript == text
    assert variant.grade["method"] == "similarity" and variant.grade["score"] > 8.0
    assert seg.status == Segment.STATUS_READY


def test_process_segment_flags_a_bad_transcription(user):
    _service_model(user, "stt", "qwen3-asr")  # no enhance → clean unavailable, still runs
    seg, variant, _ = _segment_with_audio(user, "the lighthouse keeper waved")
    words = [{"word": "totally", "start": 0.4, "end": 0.7},
             {"word": "wrong", "start": 0.7, "end": 1.0}]

    def _post(url, **kw):
        if "audio/transcriptions" in url:
            return _FakeResp({"text": "totally wrong", "words": words})
        return _FakeResp({})

    with patch("apps.inference.openai_views.requests.post", side_effect=_post):
        narration.process_segment(seg)
    seg.refresh_from_db()
    assert seg.status == Segment.STATUS_FLAGGED       # grade said regenerate
    assert variant.refresh_from_db() or seg.selected_variant.grade["should_regenerate"]


def test_process_endpoint_runs_inline_and_returns_202(user, settings):
    settings.ASYNC_ENABLED = False  # inline path
    _service_model(user, "stt", "qwen3-asr")
    text = "hello there friend"
    seg, _, _ = _segment_with_audio(user, text)
    words = [{"word": w, "start": 0.4 + i * 0.1, "end": 0.5 + i * 0.1} for i, w in enumerate(text.split())]

    def _post(url, **kw):
        if "audio/transcriptions" in url:
            return _FakeResp({"text": text, "words": words})
        return _FakeResp({})

    from rest_framework.test import APIClient
    c = APIClient(); c.force_authenticate(user)
    with patch("apps.inference.openai_views.requests.post", side_effect=_post):
        r = c.post(f"/v1/segments/{seg.id}/process", {}, format="json")
    assert r.status_code == 202, r.content
    assert r.json()["status"] == Segment.STATUS_READY


def test_process_endpoint_409_without_audio(user):
    from rest_framework.test import APIClient
    ep = Episode.objects.create(user=user, title="ep")
    seg = Segment.objects.create(episode=ep, position=0, text="no take yet")
    c = APIClient(); c.force_authenticate(user)
    assert c.post(f"/v1/segments/{seg.id}/process", {}, format="json").status_code == 409


def test_regenerate_segment_generates_take_then_processes(user):
    # Dia (voice-cloning tts) for generation + stt for ASR; no enhance is fine.
    _service_model(user, "tts", "dia", features=["voice-cloning"])
    _service_model(user, "stt", "qwen3-asr")
    from apps.inference.models import Episode
    ep = Episode.objects.create(user=user, title="ep")
    seg = Segment.objects.create(episode=ep, position=0, text="once upon a time")
    take_wav = _wav([(0.3, 0), (0.7, 440), (0.3, 0)])
    words = [{"word": w, "start": 0.3 + i * 0.1, "end": 0.4 + i * 0.1}
             for i, w in enumerate("once upon a time".split())]

    def _post(url, **kw):
        if "voice/generations" in url:
            return _FakeResp(take_wav, content_type="audio/wav")
        if "audio/transcriptions" in url:
            return _FakeResp({"text": "once upon a time", "words": words})
        return _FakeResp({})

    with patch("apps.inference.openai_views.requests.post", side_effect=_post):
        res = narration.regenerate_segment(seg)
    assert res["ok"], res
    seg.refresh_from_db()
    assert seg.selected_variant_id is not None              # a fresh take was made + selected
    v = seg.selected_variant
    assert v.audio_id and v.cleaned_audio_id                # generated + processed
    assert v.transcript == "once upon a time"
    assert seg.status == Segment.STATUS_READY
    assert seg.variants.count() == 1


def test_regenerate_endpoint_inline(user, settings):
    settings.ASYNC_ENABLED = False
    _service_model(user, "tts", "dia", features=["voice-cloning"])
    _service_model(user, "stt", "qwen3-asr")
    from apps.inference.models import Episode
    ep = Episode.objects.create(user=user, title="ep")
    seg = Segment.objects.create(episode=ep, position=0, text="hello world")
    wav = _wav([(0.3, 0), (0.6, 440), (0.3, 0)])
    words = [{"word": "hello", "start": 0.3, "end": 0.6}, {"word": "world", "start": 0.6, "end": 0.9}]

    def _post(url, **kw):
        if "voice/generations" in url:
            return _FakeResp(wav, content_type="audio/wav")
        if "audio/transcriptions" in url:
            return _FakeResp({"text": "hello world", "words": words})
        return _FakeResp({})

    from rest_framework.test import APIClient
    c = APIClient(); c.force_authenticate(user)
    with patch("apps.inference.openai_views.requests.post", side_effect=_post):
        r = c.post(f"/v1/segments/{seg.id}/regenerate", {"seed": 7}, format="json")
    assert r.status_code == 202, r.content
    assert r.json()["status"] == Segment.STATUS_READY


def test_regenerate_without_voice_provider_errors(user):
    from apps.inference.models import Episode
    ep = Episode.objects.create(user=user, title="ep")
    seg = Segment.objects.create(episode=ep, position=0, text="no voice provider")
    res = narration.regenerate_segment(seg)
    assert res["ok"] is False
    seg.refresh_from_db()
    assert seg.status == Segment.STATUS_ERROR


# --- text → chunks (Phase 2) -------------------------------------------------


def test_split_into_segments_groups_toward_target_and_strips_tags():
    text = ("First sentence here. Second one follows. A third sentence. And a "
            "fourth. Fifth sentence now. Sixth and final one here today.")
    segs = narration.split_into_segments(text, target_words=8)
    assert len(segs) >= 2
    for s in segs:                                   # each near the target, whole sentences
        assert s.endswith((".", "!", "?"))
        assert 4 <= len(s.split()) <= 16
    assert narration.split_into_segments("[S1] Hi there. [S2] Bye now.", 8) == ["Hi there. Bye now."]
    assert narration.split_into_segments("   ", 8) == []


def test_chunk_transform_op_returns_indexed_sections():
    from apps.inference import workflows
    out = workflows._run_transform(
        {"op": "chunk", "input": "One two three four. Five six seven eight.", "target_words": 4},
        {},
    )
    assert isinstance(out, list) and out[0]["index"] == 0 and "text" in out[0]


def test_episode_from_text_creates_episode_with_segments(user):
    from rest_framework.test import APIClient
    c = APIClient(); c.force_authenticate(user)
    # target_words below the 8-word floor clamps to 8; use enough sentences to
    # split into multiple segments at that size.
    text = ("First sentence here now. Second one follows along. A third sentence "
            "appears. And then a fourth. Fifth sentence arrives soon. Sixth and "
            "final sentence here today.")
    r = c.post("/v1/episodes/from-text", {"text": text, "target_words": 8, "title": "T"}, format="json")
    assert r.status_code == 201, r.content
    data = r.json()
    assert data["title"] == "T"
    assert len(data["segments"]) >= 2
    assert all(s["text"] for s in data["segments"])
    # positions are sequential
    assert [s["position"] for s in data["segments"]] == list(range(len(data["segments"])))


def test_episode_from_text_requires_text(user):
    from rest_framework.test import APIClient
    c = APIClient(); c.force_authenticate(user)
    assert c.post("/v1/episodes/from-text", {"text": "   "}, format="json").status_code == 400
