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
import re
import subprocess
import tempfile
import time

logger = logging.getLogger("django")

# Dia speaker tags ([S1]/[S2]/…) drive narration but must never appear in the
# burned-in subtitles — strip them (and surrounding whitespace) from captions.
_SPEAKER_TAG_RE = re.compile(r"\[S\d+\]")

# A render of a handful of sections is quick, but FFmpeg encode time scales with
# total duration; cap a single compose so a runaway can't pin a worker forever.
RENDER_TIMEOUT_SECONDS = 600

# 720p canvas — every section is scaled to fit and padded, so mixed aspect
# ratios concatenate cleanly with -c copy (identical codec params).
_VF = (
    "scale=1280:720:force_original_aspect_ratio=decrease,"
    "pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p,fps=30"
)

# Subtitle style for burned-in captions (PRD 12, compose-full): bottom-centered
# white text with an outline + translucent box so it stays legible over any
# illustration. PlayRes matches the 720p canvas.
_BURN_ASS_HEADER = (
    "[Script Info]\n"
    "ScriptType: v4.00+\n"
    "PlayResX: 1280\n"
    "PlayResY: 720\n\n"
    "[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, "
    "BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, "
    "MarginR, MarginV\n"
    "Style: Default,Arial,40,&H00FFFFFF,&H00000000,&H66000000,1,3,2,1,2,"
    "60,60,50\n\n"
    "[Events]\n"
    "Format: Layer, Start, End, Style, Text\n"
)


def _caption_text(item) -> str:
    """The on-screen caption for a section. Accepts a bare string or a section
    dict (``{index, lines, text}``) — what split_sections emits. Strips Dia
    speaker tags ([S1]/[S2]) and trims whitespace per line so the subtitle reads
    as clean spoken text, never the raw narration script."""
    if isinstance(item, dict):
        item = item.get("text") or item.get("caption") or ""
    text = _SPEAKER_TAG_RE.sub("", str(item or ""))
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def _ass_escape(text: str) -> str:
    """Make caption text safe inside an ASS Dialogue line: newlines become hard
    breaks and ``{}`` (override-tag delimiters) are stripped."""
    return text.replace("{", "(").replace("}", ")").replace("\r", "").replace("\n", "\\N")


def _write_caption_ass(text: str, path: str) -> bool:
    """Write a one-cue ASS file holding ``text`` for the whole clip (a generous
    end time; the section clip ends first via -shortest). Returns False for
    blank text so the caller can skip the subtitles filter."""
    text = _ass_escape(text)
    if not text:
        return False
    with open(path, "w") as f:
        f.write(_BURN_ASS_HEADER)
        f.write(f"Dialogue: 0,0:00:00.00,9:59:59.99,Default,{text}\n")
    return True


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


def _run_ffmpeg(args, cwd=None) -> None:
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *args],
        capture_output=True, text=True, timeout=RENDER_TIMEOUT_SECONDS, cwd=cwd,
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


def render_slideshow(image_assets, audio_assets, out_path, captions=None) -> float:
    """Build a narrated slideshow: section *i* shows ``image_assets[i]`` for the
    length of ``audio_assets[i]``. If ``captions`` is given, ``captions[i]`` is
    burned in over that section (PRD 12 compose-full). Returns the total
    duration (seconds)."""
    n = min(len(image_assets), len(audio_assets))
    if n == 0:
        raise RuntimeError("compose needs at least one (image, audio) pair.")
    captions = captions or []

    with tempfile.TemporaryDirectory() as td:
        clip_paths = []
        for i in range(n):
            img = os.path.join(td, f"img{i}{_ext_for(image_assets[i].content_type, '.png')}")
            aud = os.path.join(td, f"aud{i}{_ext_for(audio_assets[i].content_type, '.wav')}")
            _download(image_assets[i], img)
            _download(audio_assets[i], aud)
            clip = os.path.join(td, f"clip{i}.mp4")
            # Burn this section's caption (if any) in the same encode pass. The
            # subtitles filter is referenced by a bare name with cwd=td so the
            # path needs no shell/filter escaping.
            vf = _VF
            cap_text = _caption_text(captions[i]) if i < len(captions) else ""
            if cap_text and _write_caption_ass(cap_text, os.path.join(td, f"cap{i}.ass")):
                vf = f"{_VF},subtitles=cap{i}.ass"
            # One section: loop the still over its narration; -shortest ends the
            # clip exactly when the audio does. Uniform codec params so the
            # clips concat losslessly below.
            _run_ffmpeg([
                "-loop", "1", "-i", img, "-i", aud,
                "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-vf", vf,
                "-shortest", "-movflags", "+faststart", clip,
            ], cwd=td)
            clip_paths.append(clip)

        concat_list = os.path.join(td, "clips.txt")
        with open(concat_list, "w") as f:
            for c in clip_paths:
                f.write(f"file '{c}'\n")
        _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", out_path])

        return _probe_duration(out_path)


def _probe_duration(path) -> float:
    """Container duration in seconds (0.0 if it can't be read)."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, timeout=60,
    )
    try:
        return float(json.loads(probe.stdout)["format"]["duration"])
    except (ValueError, KeyError):
        return 0.0


def mix_music_bed(video_path, music_path, out_path) -> None:
    """Lay a music bed under a narrated video (PRD 12 V4). The music is looped to
    the video's length, attenuated, and side-chain-ducked by the narration so it
    drops under speech and swells in the gaps; the video stream is copied. The
    output runs as long as the narration (``duration=first``)."""
    _run_ffmpeg([
        "-i", video_path, "-stream_loop", "-1", "-i", music_path,
        "-filter_complex",
        "[1:a]volume=0.25[bg];"
        "[bg][0:a]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=400[duck];"
        "[0:a][duck]amix=inputs=2:duration=first:normalize=0[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", out_path,
    ])


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

    captions = payload.get("captions")
    captions = captions if isinstance(captions, list) else []

    # Optional music bed (V4): a single track ducked under the narration.
    music_ids = workflows._extract_asset_ids(payload.get("music"))
    music = _ordered_assets(music_ids, ir.user)[:1]

    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "video.mp4")
            duration = render_slideshow(images, audios, out, captions=captions)
            if music:
                mus = os.path.join(td, f"music{_ext_for(music[0].content_type, '.wav')}")
                _download(music[0], mus)
                mixed = os.path.join(td, "video_music.mp4")
                mix_music_bed(out, mus, mixed)
                out = mixed
                duration = _probe_duration(out)
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
        metadata={
            "sections": min(len(images), len(audios)),
            "captions": bool([c for c in captions if _caption_text(c)]),
            "music": bool(music),
        },
    )
    asset.file.save("video.mp4", ContentFile(video), save=False)
    asset.save()
    # Provenance: the composed video derives from its section assets — plus the
    # music bed when present (PRD 12).
    asset.record_derivation([*images, *audios, *music])

    ir.status = "PROCESSED"
    ir.audio_seconds = duration
    ir.results = {
        "video_asset_id": asset.id,
        "content_type": "video/mp4",
        "duration": duration,
        "sections": min(len(images), len(audios)),
        "music": bool(music),
    }
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=["status", "audio_seconds", "results", "latency_ms", "modified_on"])
    return True, None


def _fail(ir, message):
    ir.status = "REQUESTED"
    ir.results = {"error": message}
    ir.save(update_fields=["status", "results", "modified_on"])
    return False, message
