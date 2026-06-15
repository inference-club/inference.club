"""Central video compositing (PRD 12 §5.5): the ``compose`` node renders here,
on the worker, with FFmpeg — not on a provider cluster. The inputs (per-section
audio + images) are already MediaAssets in our own storage, so we fetch them,
build a narrated slideshow MP4 (each image held for the length of its paired
audio clip), and store the result as an OUTPUT_VIDEO asset.

Deterministic, CPU-bound, provider-free: a RENDER job's runner calls
``run_render_job`` (see openai_views._rerun_render). Heavy/long renders are
bounded by the dedicated render-concurrency cap in the dispatcher.
"""
import json
import logging
import os
import subprocess
import tempfile
import time

logger = logging.getLogger("django")

# A render of a handful of sections is quick, but FFmpeg encode time scales with
# total duration; cap a single compose so a runaway can't pin a worker forever.
RENDER_TIMEOUT_SECONDS = 600

# 720p canvas — every section is scaled to fit and padded, so mixed aspect
# ratios concatenate cleanly with -c copy (identical codec params).
_VF = (
    "scale=1280:720:force_original_aspect_ratio=decrease,"
    "pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p,fps=30"
)


def _ext_for(content_type: str, default: str) -> str:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    return {
        "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
        "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a", "audio/aac": ".aac", "audio/ogg": ".ogg",
    }.get(ct, default)


def _download(asset, path) -> None:
    """Stream a MediaAsset's bytes to a local file FFmpeg can read."""
    with asset.file.open("rb") as src, open(path, "wb") as dst:
        for chunk in iter(lambda: src.read(1 << 20), b""):
            dst.write(chunk)


def _run_ffmpeg(args) -> None:
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *args],
        capture_output=True, text=True, timeout=RENDER_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[:500]}")


def _ordered_assets(ids, user):
    """MediaAssets owned by ``user`` in the order their ids appear (so section
    alignment is preserved). Skips ids the user doesn't own."""
    from .models import MediaAsset

    by_id = {
        a.id: a
        for a in MediaAsset.objects.filter(id__in=ids, user=user)
    }
    return [by_id[i] for i in ids if i in by_id]


def render_slideshow(image_assets, audio_assets, out_path) -> float:
    """Build a narrated slideshow: section *i* shows ``image_assets[i]`` for the
    length of ``audio_assets[i]``. Returns the total duration (seconds)."""
    n = min(len(image_assets), len(audio_assets))
    if n == 0:
        raise RuntimeError("compose needs at least one (image, audio) pair.")

    with tempfile.TemporaryDirectory() as td:
        clip_paths = []
        for i in range(n):
            img = os.path.join(td, f"img{i}{_ext_for(image_assets[i].content_type, '.png')}")
            aud = os.path.join(td, f"aud{i}{_ext_for(audio_assets[i].content_type, '.wav')}")
            _download(image_assets[i], img)
            _download(audio_assets[i], aud)
            clip = os.path.join(td, f"clip{i}.mp4")
            # One section: loop the still over its narration; -shortest ends the
            # clip exactly when the audio does. Uniform codec params so the
            # clips concat losslessly below.
            _run_ffmpeg([
                "-loop", "1", "-i", img, "-i", aud,
                "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-vf", _VF,
                "-shortest", "-movflags", "+faststart", clip,
            ])
            clip_paths.append(clip)

        concat_list = os.path.join(td, "clips.txt")
        with open(concat_list, "w") as f:
            for c in clip_paths:
                f.write(f"file '{c}'\n")
        _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", out_path])

        # Total duration via ffprobe (sum of section audio lengths).
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", out_path],
            capture_output=True, text=True, timeout=60,
        )
        try:
            return float(json.loads(probe.stdout)["format"]["duration"])
        except (ValueError, KeyError):
            return 0.0


def run_render_job(ir):
    """RENDER job runner (central): pair the job's image + audio assets, render a
    slideshow MP4, store it as an OUTPUT_VIDEO asset, and finalize ``ir``.
    Returns ``(ok, error)`` like the modality runners."""
    from django.core.files.base import ContentFile

    from . import workflows
    from .models import MediaAsset

    payload = ir.payload or {}
    image_ids = workflows._extract_asset_ids(payload.get("images"))
    audio_ids = workflows._extract_asset_ids(payload.get("audio"))
    if not image_ids or not audio_ids:
        return _fail(ir, "compose needs non-empty `images` and `audio` lists of assets.")

    images = _ordered_assets(image_ids, ir.user)
    audios = _ordered_assets(audio_ids, ir.user)
    if not images or not audios:
        return _fail(ir, "compose could not load the referenced image/audio assets.")

    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "video.mp4")
            duration = render_slideshow(images, audios, out)
            with open(out, "rb") as fh:
                video = fh.read()
    except subprocess.TimeoutExpired:
        return _fail(ir, "compose timed out.")
    except Exception as e:
        logger.exception("render job %s failed", ir.id)
        return _fail(ir, f"compose failed: {e}")

    asset = MediaAsset(
        user=ir.user, inference_request=ir, kind=MediaAsset.OUTPUT_VIDEO,
        content_type="video/mp4", size_bytes=len(video), duration_seconds=duration,
        metadata={"sections": min(len(images), len(audios))},
    )
    asset.file.save("video.mp4", ContentFile(video), save=False)
    asset.save()
    # Provenance: the composed video derives from its section assets (PRD 12).
    asset.record_derivation([*images, *audios])

    ir.status = "PROCESSED"
    ir.audio_seconds = duration
    ir.results = {
        "video_asset_id": asset.id,
        "content_type": "video/mp4",
        "duration": duration,
        "sections": min(len(images), len(audios)),
    }
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=["status", "audio_seconds", "results", "latency_ms", "modified_on"])
    return True, None


def _fail(ir, message):
    ir.status = "REQUESTED"
    ir.results = {"error": message}
    ir.save(update_fields=["status", "results", "modified_on"])
    return False, message
