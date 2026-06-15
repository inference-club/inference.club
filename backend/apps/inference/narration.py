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


def run_trim_job(ir):
    """TRIM job runner (central, no provider). Payload: ``{audio_asset_id, words,
    [pad, gap_threshold, max_gap]}``. Trims silence/pauses and stores the result
    as a new OUTPUT_AUDIO (original untouched). Returns ``(ok, error)``."""
    from django.core.files.base import ContentFile

    from .models import MediaAsset

    payload = ir.payload or {}
    aid = payload.get("audio_asset_id")
    src = MediaAsset.objects.filter(id=aid, user=ir.user).first() if aid else None
    if src is None or not src.file:
        return _fail(ir, "trim could not load the source audio asset.")
    words = normalize_words(payload.get("words"))

    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory() as td:
            ext = (src.content_type or "audio/wav").rsplit("/", 1)[-1] or "wav"
            in_path = os.path.join(td, f"in.{ext}")
            with src.file.open("rb") as f, open(in_path, "wb") as dst:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    dst.write(chunk)
            duration = _probe_duration(in_path)

            def _f(key, default):
                try:
                    return float(payload[key])
                except (KeyError, TypeError, ValueError):
                    return default

            intervals = plan_trim_intervals(
                words, duration, pad=_f("pad", TRIM_PAD),
                gap_threshold=_f("gap_threshold", TRIM_GAP_THRESHOLD),
                max_gap=_f("max_gap", TRIM_MAX_GAP),
            )
            out_path = os.path.join(td, "trimmed.wav")
            if intervals:
                trim_audio(in_path, out_path, intervals)
            else:
                # No word timestamps → nothing to trim on; pass the audio through.
                out_path = in_path
            out_dur = _probe_duration(out_path)
            with open(out_path, "rb") as fh:
                audio = fh.read()
    except subprocess.TimeoutExpired:
        return _fail(ir, "trim timed out.")
    except Exception as e:
        logger.exception("trim job %s failed", ir.id)
        return _fail(ir, f"trim failed: {e}")

    asset = MediaAsset(
        user=ir.user, inference_request=ir, kind=MediaAsset.OUTPUT_AUDIO,
        content_type="audio/wav", size_bytes=len(audio), duration_seconds=out_dur,
        metadata={"trimmed_from": src.id, "saved_seconds": round(duration - out_dur, 3)},
    )
    asset.file.save("trimmed.wav", ContentFile(audio), save=False)
    asset.save()
    asset.record_derivation([src])

    ir.status = "PROCESSED"
    ir.audio_seconds = out_dur
    ir.results = {
        "audio_asset_id": asset.id, "content_type": "audio/wav",
        "duration": out_dur, "source_duration": duration,
        "source_asset_id": src.id,
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
