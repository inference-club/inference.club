"""Narration Studio pipeline primitives (PRD 12 V3).

Pure-ish helpers + a central (worker-side) audio trimmer for the per-segment
narration pipeline: clean (StudioVoice) → ASR (word timestamps) → TRIM (here) →
grade. Like ``render.py``, the trim runs on the worker with FFmpeg (no provider)
— it's a deterministic transform over audio we already store.

- ``normalize_words`` canonicalizes ASR word lists to ``[{word,start,end}]`` (s).
- ``plan_trim_intervals`` turns word timestamps into keep-ranges: trims leading/
  trailing silence and collapses long internal pauses.
- ``run_trim_job`` is the TRIM job runner (central, no provider).
- ``grade_transcription`` scores ASR-vs-original with an LLM (SequenceMatcher
  fallback), ported from inference-club-studio.
"""
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from difflib import SequenceMatcher

logger = logging.getLogger("django")

TRIM_TIMEOUT_SECONDS = 300

# Trim defaults (seconds). Word-timestamp-driven; tunable per job via payload.
TRIM_PAD = 0.06          # keep this much audio around speech at head/tail
TRIM_GAP_THRESHOLD = 0.6  # only collapse internal gaps longer than this
TRIM_MAX_GAP = 0.3        # ...down to about this much


def normalize_words(raw) -> list[dict]:
    """Canonicalize an ASR word list to ``[{word, start, end}]`` in SECONDS.

    Accepts the shapes we see in the wild: ``{word, start_ms, duration_ms}``
    (hn.fm / Riva), ``{word|text, start, end}`` (seconds, OpenAI-ish), and
    tolerates a ``{words: [...]}`` wrapper. Skips blanks; gives a zero-length
    word a small floor so downstream math stays sane."""
    if isinstance(raw, dict):
        raw = raw.get("words")
    if not isinstance(raw, list):
        return []
    out = []
    for w in raw:
        if not isinstance(w, dict):
            continue
        text = str(w.get("word") or w.get("text") or "").strip()
        if not text:
            continue
        if "start_ms" in w or "duration_ms" in w:
            start = float(w.get("start_ms") or 0) / 1000.0
            end = start + float(w.get("duration_ms") or 0) / 1000.0
        else:
            start = float(w.get("start") or 0)
            end = float(w.get("end") or start)
        if end <= start:
            end = start + 0.05
        out.append({"word": text, "start": round(start, 3), "end": round(end, 3)})
    out.sort(key=lambda x: x["start"])
    return out


def plan_trim_intervals(words, duration, *, pad=TRIM_PAD,
                        gap_threshold=TRIM_GAP_THRESHOLD, max_gap=TRIM_MAX_GAP):
    """Keep-ranges ``[(start, end), …]`` (seconds) for trimming. Trims silence
    before the first / after the last word (leaving ``pad``), and where the gap
    between two words exceeds ``gap_threshold`` it drops the excess so only about
    ``max_gap`` of pause remains. Returns ``[]`` when there's nothing to do
    (no words), signalling the caller to keep the original audio."""
    words = [w for w in (words or []) if isinstance(w, dict) and "start" in w]
    if not words:
        return []
    duration = float(duration or 0) or (words[-1]["end"] + pad)
    keep = max(0.0, max_gap / 2.0)

    intervals = []
    seg_start = max(0.0, words[0]["start"] - pad)
    prev_end = words[0]["end"]
    for w in words[1:]:
        gap = w["start"] - prev_end
        if gap > gap_threshold:
            # Close this run a touch after the last word, reopen a touch before
            # the next — removing (gap - max_gap) of dead air in between.
            intervals.append((seg_start, min(prev_end + keep, w["start"])))
            seg_start = max(w["start"] - keep, prev_end)
        prev_end = w["end"]
    intervals.append((seg_start, min(duration, words[-1]["end"] + pad)))
    # Drop empty/inverted ranges that can arise from very tight word spacing.
    return [(round(a, 3), round(b, 3)) for a, b in intervals if b - a > 0.01]


def _aselect_filter(intervals) -> str:
    """An ffmpeg ``aselect`` expression that keeps only ``intervals`` and resets
    timestamps so the kept pieces play back-to-back (no gaps where we cut)."""
    between = "+".join(f"between(t,{a},{b})" for a, b in intervals)
    return f"aselect='{between}',asetpts=N/SR/TB"


def trim_audio(in_path, out_path, intervals) -> None:
    """Apply the keep-``intervals`` to ``in_path`` → ``out_path`` in one ffmpeg
    pass via the aselect filter (PCM WAV out)."""
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", in_path,
         "-af", _aselect_filter(intervals), "-c:a", "pcm_s16le", out_path],
        capture_output=True, text=True, timeout=TRIM_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg trim failed: {proc.stderr.strip()[:500]}")


def _probe_duration(path) -> float:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, timeout=60,
    )
    try:
        return float(json.loads(probe.stdout)["format"]["duration"])
    except (ValueError, KeyError):
        return 0.0


def remap_words(words, intervals):
    """Shift word timestamps onto the trimmed timeline. A word fully inside a
    kept interval moves to its new position (kept-length before it + offset into
    its interval); words that fell in a removed gap are dropped."""
    spans, cum = [], 0.0
    for a, b in intervals:
        spans.append((a, b, cum))
        cum += (b - a)
    out = []
    for w in words:
        for a, b, off in spans:
            if w["start"] >= a - 1e-6 and w["end"] <= b + 1e-6:
                out.append({"word": w["word"],
                            "start": round(off + (w["start"] - a), 3),
                            "end": round(off + (w["end"] - a), 3)})
                break
    return out


def trim_asset(user, src, words, *, pad=TRIM_PAD, gap_threshold=TRIM_GAP_THRESHOLD,
               max_gap=TRIM_MAX_GAP, inference_request=None):
    """Trim silence/pauses from ``src`` (a MediaAsset) using ``words``; store the
    result as a new OUTPUT_AUDIO (original untouched) and return
    ``(asset, remapped_words, src_duration, out_duration)``. If there are no
    words to trim on, returns the source unchanged."""
    from django.core.files.base import ContentFile

    from .models import MediaAsset

    words = normalize_words(words)
    with tempfile.TemporaryDirectory() as td:
        ext = (src.content_type or "audio/wav").rsplit("/", 1)[-1] or "wav"
        in_path = os.path.join(td, f"in.{ext}")
        with src.file.open("rb") as f, open(in_path, "wb") as dst:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                dst.write(chunk)
        src_dur = _probe_duration(in_path)
        intervals = plan_trim_intervals(words, src_dur, pad=pad,
                                        gap_threshold=gap_threshold, max_gap=max_gap)
        if not intervals:
            return src, words, src_dur, src_dur  # nothing to trim on
        out_path = os.path.join(td, "trimmed.wav")
        trim_audio(in_path, out_path, intervals)
        out_dur = _probe_duration(out_path)
        with open(out_path, "rb") as fh:
            audio = fh.read()

    asset = MediaAsset(
        user=user, inference_request=inference_request, kind=MediaAsset.OUTPUT_AUDIO,
        content_type="audio/wav", size_bytes=len(audio), duration_seconds=out_dur,
        metadata={"trimmed_from": src.id, "saved_seconds": round(src_dur - out_dur, 3)},
    )
    asset.file.save("trimmed.wav", ContentFile(audio), save=False)
    asset.save()
    asset.record_derivation([src])
    return asset, remap_words(words, intervals), src_dur, out_dur


def run_trim_job(ir):
    """TRIM job runner (central, no provider). Payload: ``{audio_asset_id, words,
    [pad, gap_threshold, max_gap]}``. Returns ``(ok, error)``."""
    from .models import MediaAsset

    payload = ir.payload or {}
    aid = payload.get("audio_asset_id")
    src = MediaAsset.objects.filter(id=aid, user=ir.user).first() if aid else None
    if src is None or not src.file:
        return _fail(ir, "trim could not load the source audio asset.")

    def _f(key, default):
        try:
            return float(payload[key])
        except (KeyError, TypeError, ValueError):
            return default

    started = time.monotonic()
    try:
        asset, words_out, src_dur, out_dur = trim_asset(
            ir.user, src, payload.get("words"), pad=_f("pad", TRIM_PAD),
            gap_threshold=_f("gap_threshold", TRIM_GAP_THRESHOLD),
            max_gap=_f("max_gap", TRIM_MAX_GAP), inference_request=ir,
        )
    except subprocess.TimeoutExpired:
        return _fail(ir, "trim timed out.")
    except Exception as e:
        logger.exception("trim job %s failed", ir.id)
        return _fail(ir, f"trim failed: {e}")

    ir.status = "PROCESSED"
    ir.audio_seconds = out_dur
    ir.results = {
        "audio_asset_id": asset.id, "content_type": "audio/wav",
        "duration": out_dur, "source_duration": src_dur,
        "source_asset_id": src.id, "words": words_out,
    }
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=["status", "audio_seconds", "results", "latency_ms", "modified_on"])
    return True, None


def _fail(ir, message):
    ir.status = "REQUESTED"
    ir.results = {"error": message}
    ir.save(update_fields=["status", "results", "modified_on"])
    return False, message


# --- transcription grading (ported from inference-club-studio) ---------------

QUALITY_THRESHOLD = 8.0  # accept a take whose score is >= this (0–10)

_QUALITY_PROMPT = (
    "You evaluate text-to-speech output quality using the original script and an "
    "ASR transcription of the generated audio.\n\n"
    "Return ONLY valid JSON with this exact schema:\n"
    "{\"score\": number, \"should_regenerate\": boolean, \"reason\": string}\n"
    "- score: 0 to 10 (higher is better)\n"
    "- should_regenerate: true if quality is not acceptable\n"
    "- reason: short reason (max 160 chars)\n\n"
    "Scoring: 9-10 near-perfect; 7-8 minor issues, acceptable; 4-6 noticeable "
    "errors; 0-3 severe mismatch. Ignore punctuation/casing unless meaning "
    "changes. On major omissions, substitutions, hallucinations, or wrong "
    "names/numbers set should_regenerate=true. Respond with ONLY the JSON."
)


def _normalize_for_similarity(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fallback_grade(original: str, transcript: str) -> dict:
    """No-LLM grade: normalized string similarity → 0–10."""
    ratio = SequenceMatcher(
        None, _normalize_for_similarity(original), _normalize_for_similarity(transcript)
    ).ratio()
    score = max(0.0, min(10.0, ratio * 10.0))
    return {
        "score": round(score, 2),
        "should_regenerate": score < QUALITY_THRESHOLD,
        "reason": f"Fallback similarity {int(round(ratio * 100))}%",
        "method": "similarity",
    }


def grade_transcription(user, original: str, transcript: str) -> dict:
    """Grade ASR ``transcript`` against the intended ``original`` text. Uses the
    user's LLM (JSON judge); falls back to string similarity if no LLM is
    reachable or the reply doesn't parse. Returns
    ``{score, should_regenerate, reason, method}``."""
    if not (original or "").strip() or not (transcript or "").strip():
        return {"score": 0.0, "should_regenerate": True,
                "reason": "Missing text or transcript.", "method": "guard"}
    try:
        import requests

        from . import jobs
        from .models import Provider  # noqa: F401
        from .openai_views import _find_provider_for_model, _retry_endpoint, _tailnet_proxies, UPSTREAM_TIMEOUT_SECONDS

        model = jobs.auto_model_for(user, "")
        pm = _find_provider_for_model(user, model, service_type=None) if model else None
        if pm is None:
            return fallback_grade(original, transcript)
        body = {
            "model": pm.name or model,
            "messages": [
                {"role": "system", "content": _QUALITY_PROMPT},
                {"role": "user", "content":
                    f"Original text:\n{original.strip()}\n\nTranscription:\n{transcript.strip()}"},
            ],
            "max_tokens": 256, "temperature": 0.1, "stream": False,
        }
        r = requests.post(
            _retry_endpoint(pm.provider, "/chat/completions"), json=body,
            timeout=UPSTREAM_TIMEOUT_SECONDS, verify=False, proxies=_tailnet_proxies(),
        )
        if not r.ok:
            return fallback_grade(original, transcript)
        content = r.json()["choices"][0]["message"].get("content") or ""
        parsed = _parse_quality_json(content)
        if parsed is None:
            return fallback_grade(original, transcript)
        return parsed
    except Exception:
        logger.warning("grade_transcription LLM path failed; using fallback", exc_info=True)
        return fallback_grade(original, transcript)


def _parse_quality_json(content: str):
    s = (content or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[4:] if s.lower().startswith("json") else s
        s = s.strip()
    # Tolerate prose around the JSON object.
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group())
    except ValueError:
        return None
    try:
        score = max(0.0, min(10.0, float(data.get("score"))))
    except (TypeError, ValueError):
        return None
    return {
        "score": round(score, 2),
        "should_regenerate": bool(data.get("should_regenerate", score < QUALITY_THRESHOLD)),
        "reason": str(data.get("reason") or "")[:200],
        "method": "llm",
    }


# --- ASR helper + per-segment orchestrator -----------------------------------


def _synthesize_words(text: str, duration: float) -> list[dict]:
    """Uniformly distribute words across ``duration`` when the ASR engine returns
    text but no timestamps (e.g. Qwen3-ASR). Better than nothing for the editor."""
    toks = (text or "").split()
    if not toks or not duration or duration <= 0:
        return []
    slice_s = duration / len(toks)
    return [{"word": t, "start": round(i * slice_s, 3), "end": round((i + 1) * slice_s, 3)}
            for i, t in enumerate(toks)]


def transcribe_asset(user, audio_asset):
    """ASR an audio MediaAsset → ``(text, words)`` with word timestamps. Forwards
    to the user's STT provider (verbose_json); synthesizes uniform timestamps if
    the engine returns only text. Returns ``("", [])`` if no STT is reachable."""
    import requests

    from . import jobs
    from .openai_views import (UPSTREAM_TIMEOUT_SECONDS, _find_provider_for_model,
                               _retry_endpoint, _tailnet_proxies)

    model = jobs.auto_model_for(user, "stt")
    pm = _find_provider_for_model(user, model, service_type="stt") if model else None
    if pm is None or not audio_asset or not audio_asset.file:
        return "", []
    try:
        with audio_asset.file.open("rb") as f:
            data = f.read()
    except Exception:
        return "", []
    ct = audio_asset.content_type or "audio/wav"
    ext = ct.rsplit("/", 1)[-1] or "wav"
    try:
        r = requests.post(
            _retry_endpoint(pm.provider, "/audio/transcriptions"),
            files={"file": (f"audio.{ext}", data, ct)},
            data=[("model", pm.name or model), ("response_format", "verbose_json")],
            timeout=UPSTREAM_TIMEOUT_SECONDS, verify=False, proxies=_tailnet_proxies(),
        )
    except requests.RequestException:
        logger.warning("transcribe_asset: STT request failed", exc_info=True)
        return "", []
    if not r.ok:
        return "", []
    try:
        payload = r.json()
    except ValueError:
        return r.text or "", []
    text = (payload.get("text") or "").strip()
    words = normalize_words(payload.get("words"))
    if not words and text:
        words = _synthesize_words(text, audio_asset.duration_seconds or 0)
    return text, words


def process_segment(segment):
    """Run the per-segment narration pipeline on the segment's selected take:
    clean (StudioVoice) → ASR (word timestamps) → trim (silence/pauses) → grade
    (ASR vs intended text). Updates the Variant (cleaned_audio/words/transcript/
    grade) and the Segment status (ready vs flagged). Returns a summary dict.

    Non-destructive: the original ``Variant.audio`` is untouched; each stage
    degrades gracefully if its provider is unavailable."""
    from .models import InferenceRequest, MediaAsset, Segment, Variant
    from . import jobs
    from .openai_views import _find_provider_for_model, _rerun_enhance

    variant = segment.selected_variant
    if variant is None or variant.audio_id is None:
        return {"ok": False, "error": "Segment has no audio take to process."}
    user = segment.episode.user
    segment.status = Segment.STATUS_GENERATING
    segment.save(update_fields=["status", "modified_on"])

    base = variant.audio

    # 1) Clean (StudioVoice). Reuses the ENHANCE runner (reads by asset id).
    cleaned = base
    enh_model = jobs.auto_model_for(user, "audio-enhance")
    pm = _find_provider_for_model(user, enh_model, service_type="audio-enhance") if enh_model else None
    if pm is not None:
        ir = InferenceRequest.objects.create(
            user=user, provider=pm.provider, inference_type="ENHANCE",
            status="PROCESSING", model_name=enh_model,
            payload={"audio_asset_id": base.id, "model": enh_model},
        )
        ok, _err = _rerun_enhance(ir, pm)
        cid = (ir.results or {}).get("audio_asset_id") if ok else None
        if cid:
            cleaned = MediaAsset.objects.get(id=cid)
            variant.clean_status = Variant.CLEAN_DONE
        else:
            variant.clean_status = Variant.CLEAN_ERROR
    else:
        variant.clean_status = Variant.CLEAN_UNAVAILABLE

    # 2) ASR the cleaned audio for word timestamps + transcript.
    text, words = transcribe_asset(user, cleaned)

    # 3) Trim silence + long pauses (central FFmpeg), remapping words.
    try:
        final, words_out, _src_dur, out_dur = trim_asset(user, cleaned, words)
    except Exception:
        logger.exception("process_segment: trim failed for segment %s", segment.id)
        final, words_out, out_dur = cleaned, words, cleaned.duration_seconds

    variant.cleaned_audio = final
    variant.words = words_out
    variant.duration_seconds = out_dur
    variant.transcript = text

    # 4) Grade the transcript against the intended text.
    grade = grade_transcription(user, variant.text or segment.text, text)
    variant.grade = grade
    variant.save(update_fields=[
        "cleaned_audio", "words", "duration_seconds", "transcript", "grade",
        "clean_status", "modified_on",
    ])

    segment.status = (Segment.STATUS_FLAGGED if grade.get("should_regenerate")
                      else Segment.STATUS_READY)
    segment.save(update_fields=["status", "modified_on"])
    return {"ok": True, "status": segment.status, "grade": grade,
            "duration": out_dur, "audio_asset_id": final.id if final else None}
