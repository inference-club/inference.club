"""Narrate this: a link or some text in, one finished narration out.

The Studio (narration.py) already knows how to voice a line well: make a
take with the cloned voice, clean it, cut the dead air, check the words came
out right, and try again when they did not. This module is the path around
that for someone who just has an article:

    read      find the article behind the link: title, author, date, text
    plan      write the script (an opening line, then the article in
              speakable pieces) and a pronunciation list for odd terms
    voice     every piece through the Studio's take → clean → trim → check
              → retake loop, in the same cloned voice
    mix       join the chosen takes into one file
    cover     a title image, made alongside

Progress lives on the episode (``Episode.production``) so any client can show
where things stand by reading the episode: the stage, which models are doing
what, a short log of what happened, and each segment's own status.

``start()`` creates the episode and hands the rest to a worker.
``run()`` is that work. ``mix()`` can be called again after edits.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from datetime import date

from django.utils import timezone

from . import article as article_mod
from . import narration

logger = logging.getLogger(__name__)

STAGES = ("reading", "planning", "voicing", "mixing", "done")
GAP_SECONDS = 0.4  # silence between pieces
GAP_AFTER_HEADING = 0.75
GAP_AFTER_INTRO = 0.9
MAX_WORDS = 12_000  # about 80 minutes of speech; a guard, not a product limit
MAX_EVENTS = 60
SCRAPE_WAIT_SECONDS = 75
ACTIVE = ("reading", "planning", "voicing", "mixing")


# --- Progress ---------------------------------------------------------------


def _save(ep, **patch):
    ep.production = {**(ep.production or {}), **patch}
    ep.save(update_fields=["production", "modified_on"])


def _log(ep, message, **patch):
    """Add one line to the run's log and optionally change other fields."""
    events = list((ep.production or {}).get("events") or [])
    events.append({"at": timezone.now().isoformat(), "message": message})
    _save(ep, events=events[-MAX_EVENTS:], **patch)


def _cancelled(ep) -> bool:
    ep.refresh_from_db(fields=["production"])
    return bool((ep.production or {}).get("cancel"))


def is_active(ep) -> bool:
    return (ep.production or {}).get("stage") in ACTIVE


# --- Reading ----------------------------------------------------------------


def _club_scrape(user, url):
    """Ask the club's scrape service for the page. Returns (markdown, meta) or
    None. Runs as an ordinary queued job so it shows up like any other
    request; a failure here is fine, the caller fetches the page itself."""
    from .jobs import async_enabled, auto_model_for, enqueue_job, kick_dispatch
    from .models import MediaAsset

    if not async_enabled():
        return None
    model = auto_model_for(user, "scrape")
    if not model:
        return None
    job = enqueue_job(user, "SCRAPE", {"url": url, "model": model}, model_name=model,
                      visibility="SECRET", max_attempts=1)
    kick_dispatch()
    deadline = time.monotonic() + SCRAPE_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(1.5)
        job.refresh_from_db(fields=["status"])
        if job.status == "PROCESSED":
            doc = job.assets.filter(kind=MediaAsset.OUTPUT_DOC).first()
            if doc is None:
                return None
            with doc.file.open("rb") as fh:
                return fh.read().decode("utf-8", errors="replace"), dict(doc.metadata or {})
        if job.status in ("REQUESTED", "FAILED", "CANCELED"):
            return None
    return None


# --- Planning ---------------------------------------------------------------

_SPOKEN = [
    (re.compile(r"https?://\S+"), ""),
    (re.compile(r"(\d)\s?%"), r"\1 percent"),
    (re.compile(r"\s&\s"), " and "),
    (re.compile(r"\s[–—]\s|—"), ", "),
    (re.compile(r"\[(\d+|citation needed)\]"), ""),  # footnote marks
    (re.compile(r"\s+([,.;:!?])"), r"\1"),
    (re.compile(r"\s{2,}"), " "),
]


def speakable(text: str) -> str:
    """Small, safe rewrites so a line reads aloud the way it reads on the
    page: links dropped, "40%" as "40 percent", dashes as pauses."""
    for pattern, repl in _SPOKEN:
        text = pattern.sub(repl, text)
    return text.strip()


def _spoken_date(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def intro_line(art) -> str:
    """How a person would introduce the piece before reading it."""
    parts = [art.title.rstrip(".") + ("" if art.title.rstrip().endswith(("?", "!")) else ".")] if art.title else []
    if art.author:
        parts.append(f"By {art.author}.")
    when = _spoken_date(art.published)
    if when:
        parts.append(f"Published {when}.")
    return " ".join(parts)


def plan_script(art, target_words: int = narration.CHUNK_TARGET_WORDS) -> list[dict]:
    """The article as an ordered list of pieces to voice:
    ``[{"kind": "intro"|"heading"|"body", "text": ...}]``. Body text between
    headings is grouped into pieces of whole sentences near ``target_words``,
    which is the length the voice model holds steady over."""
    pieces: list[dict] = []
    intro = intro_line(art)
    if intro:
        pieces.append({"kind": "intro", "text": intro})
    run: list[str] = []

    def flush():
        if run:
            for chunk in narration.split_into_segments("\n\n".join(run), target_words):
                pieces.append({"kind": "body", "text": chunk})
            run.clear()

    for block in art.blocks:
        text = speakable(block.text)
        if not text:
            continue
        if block.kind == "heading":
            flush()
            pieces.append({"kind": "heading", "text": text.rstrip(".:") + "."})
        else:
            if not text.endswith((".", "!", "?", '"', "”", ":")):
                text += "."
            run.append(text)
    flush()
    return pieces


_LEXICON_PROMPT = (
    "You prepare text for a text-to-speech voice. From the article below, list only the terms a "
    "voice would likely mispronounce: acronyms that are spelled out letter by letter, unusual "
    "names, and symbols. For each, give how it should be SAID using plain words (for a "
    "spelled-out acronym, the letters separated by spaces, e.g. \"UBI\" -> \"U B I\"). Do not "
    "list ordinary words or acronyms normally said as a word (NASA, AI is fine as \"A I\"). "
    "At most 15 entries. Reply with a JSON object only, mapping the written term to its "
    "spoken form. If nothing needs help, reply {}."
)


def _ask_llm(user, system: str, prompt: str, max_tokens: int = 400) -> tuple[str, str]:
    """One short question to the member's first reachable chat model. Returns
    (answer, model name); ("", "") when there is no model or it fails."""
    import requests

    from . import jobs
    from .locks import device_lock, provider_device_key
    from .openai_views import (
        UPSTREAM_TIMEOUT_SECONDS,
        _find_provider_for_model,
        _retry_endpoint,
        _tailnet_proxies,
    )

    try:
        model = jobs.auto_model_for(user, "")
        pm = _find_provider_for_model(user, model, service_type=None) if model else None
        if pm is None:
            return "", ""
        body = {
            "model": pm.name or model, "max_tokens": max_tokens, "temperature": 0.1, "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "chat_template_kwargs": {"enable_thinking": False},
        }
        with device_lock(provider_device_key(pm), ttl=UPSTREAM_TIMEOUT_SECONDS + 60):
            r = requests.post(
                _retry_endpoint(pm.provider, "/chat/completions"), json=body,
                timeout=UPSTREAM_TIMEOUT_SECONDS, verify=False, proxies=_tailnet_proxies(),
            )
        if not r.ok:
            return "", ""
        return (r.json()["choices"][0]["message"].get("content") or "").strip(), model
    except Exception:  # noqa: BLE001 - planning help is optional
        logger.warning("narrate: LLM call failed", exc_info=True)
        return "", ""


def clean_lexicon(raw: str, text: str) -> dict:
    """Keep only entries that are safe to apply: the term really appears in
    the text, it is short, and its spoken form is plain words."""
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return {}
    out = {}
    for written, spoken in (data.items() if isinstance(data, dict) else []):
        if not isinstance(written, str) or not isinstance(spoken, str):
            continue
        written, spoken = written.strip(), spoken.strip()
        if (
            2 <= len(written) <= 40 and 1 <= len(spoken) <= 60
            and written.lower() != spoken.lower()
            and re.search(rf"(?<!\w){re.escape(written)}(?!\w)", text)
            and re.fullmatch(r"[A-Za-z0-9 .,'-]+", spoken)
        ):
            out[written] = spoken
        if len(out) >= 15:
            break
    return out


def suggest_lexicon(user, text: str) -> tuple[dict, str]:
    answer, model = _ask_llm(user, _LEXICON_PROMPT, text[:6000], max_tokens=400)
    return clean_lexicon(answer, text), model


# --- Voice ------------------------------------------------------------------


def default_voice_sample(user):
    """The member's own voice for narration: their default sample, else the
    newest one that has a transcript (the model needs the words to clone)."""
    from .models import VoiceSample

    samples = VoiceSample.objects.filter(user=user).exclude(transcript="")
    return samples.filter(is_default=True).order_by("-id").first() or samples.order_by("-id").first()


# --- Feedback ---------------------------------------------------------------

_FEEDBACK_PROMPT = (
    "A narrator is recording one line and a listener has left a note about it. Decide what to "
    "change. Reply with a JSON object only: {\"text\": the line to record (reworded only if the "
    "note asks for different words; otherwise exactly the original), \"lexicon\": {written term: "
    "how to say it} for any pronunciation the note corrects (plain words, letters separated by "
    "spaces for spelled-out acronyms; {} if none), \"summary\": one short sentence saying what "
    "you changed}. Never add commentary to the line itself."
)


def apply_feedback(segment, note: str) -> dict:
    """Turn a listener's note about one piece into changes: new wording for
    the line and/or pronunciation entries for the episode. Returns what was
    understood. With no chat model reachable the note just triggers a retake."""
    ep = segment.episode
    answer, _ = _ask_llm(ep.user, _FEEDBACK_PROMPT, f"Line:\n{segment.text}\n\nNote:\n{note}", max_tokens=500)
    plan = {"text_changed": False, "lexicon": {}, "summary": "Voicing it again."}
    m = re.search(r"\{.*\}", answer or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        data = {}
    text = data.get("text") if isinstance(data, dict) else None
    if isinstance(text, str) and text.strip() and text.strip() != segment.text.strip() \
            and 0.3 <= len(text) / max(1, len(segment.text)) <= 3:
        if not segment.original_text:
            segment.original_text = segment.text
        segment.text = text.strip()
        segment.save(update_fields=["text", "original_text", "modified_on"])
        plan["text_changed"] = True
    lex = clean_lexicon(json.dumps(data.get("lexicon") or {}), segment.text) if isinstance(data, dict) else {}
    if lex:
        ep.settings = {**(ep.settings or {}), "lexicon": {**((ep.settings or {}).get("lexicon") or {}), **lex}}
        ep.save(update_fields=["settings", "modified_on"])
        plan["lexicon"] = lex
    if isinstance(data, dict) and isinstance(data.get("summary"), str) and (plan["text_changed"] or lex):
        plan["summary"] = data["summary"].strip()[:200]
    return plan


# --- Mix --------------------------------------------------------------------


def _mix_signature(takes) -> str:
    return hashlib.sha1(",".join(str(v.id) for _, v in takes).encode()).hexdigest()[:16]


def selected_takes(ep):
    """(segment, chosen take) for every segment that has audio, in order."""
    out = []
    for seg in ep.segments.select_related("selected_variant", "selected_variant__cleaned_audio",
                                          "selected_variant__audio").order_by("position", "id"):
        v = seg.selected_variant
        if v is not None and (v.cleaned_audio_id or v.audio_id):
            out.append((seg, v))
    return out


def mix_is_current(ep) -> bool:
    mix = (ep.production or {}).get("mix") or {}
    return bool(ep.audio_id) and mix.get("signature") == _mix_signature(selected_takes(ep))


def mix(ep):
    """Join the chosen takes into one MP3 with a short breath between pieces,
    store it on the episode, and record where each segment starts so a player
    can follow along. Returns the asset, or None when nothing is voiced yet."""
    from django.core.files.base import ContentFile

    from .models import MediaAsset

    takes = selected_takes(ep)
    if not takes:
        return None
    kinds = (ep.production or {}).get("kinds") or {}
    with tempfile.TemporaryDirectory() as td:
        parts, offsets, cursor = [], [], 0.0
        for n, (seg, v) in enumerate(takes):
            src = narration._download_asset(v.cleaned_audio or v.audio, td)
            kind = kinds.get(str(seg.id), "body")
            gap = 0.0 if n == len(takes) - 1 else (
                GAP_AFTER_INTRO if kind == "intro" else GAP_AFTER_HEADING if kind == "heading" else GAP_SECONDS)
            part = os.path.join(td, f"part-{n:04d}.wav")
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", src,
                 "-af", f"apad=pad_dur={gap}", "-ar", "44100", "-ac", "1", part],
                check=True, capture_output=True, timeout=120,
            )
            length = narration._probe_duration(part)
            offsets.append({"segment_id": seg.id, "start": round(cursor, 3), "end": round(cursor + length - gap, 3)})
            cursor += length
            parts.append(part)
        listing = os.path.join(td, "parts.txt")
        with open(listing, "w") as fh:
            fh.writelines(f"file '{p}'\n" for p in parts)
        out = os.path.join(td, "narration.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listing,
             "-c:a", "libmp3lame", "-b:a", "128k", out],
            check=True, capture_output=True, timeout=600,
        )
        seconds = narration._probe_duration(out)
        with open(out, "rb") as fh:
            data = fh.read()
    asset = MediaAsset(
        user=ep.user, kind=MediaAsset.OUTPUT_AUDIO, content_type="audio/mpeg",
        size_bytes=len(data), duration_seconds=seconds,
        metadata={"episode_id": ep.id, "narration": True, "title": ep.title},
    )
    asset.file.save("narration.mp3", ContentFile(data), save=False)
    asset.save()
    asset.record_derivation([v.cleaned_audio or v.audio for _, v in takes])
    ep.audio = asset
    ep.save(update_fields=["audio", "modified_on"])
    _save(ep, mix={"signature": _mix_signature(takes), "seconds": round(seconds, 2),
                   "offsets": offsets, "at": timezone.now().isoformat()})
    return asset


def transcript(ep) -> dict:
    """Every word of the joined recording with its time in that recording.
    Word times come from speech recognition of each take, corrected for
    recognition lag and carried through every cut, then shifted to where the
    piece sits in the joined file."""
    offsets = {o["segment_id"]: o for o in ((ep.production or {}).get("mix") or {}).get("offsets") or []}
    segments, words = [], []
    for seg, v in selected_takes(ep):
        o = offsets.get(seg.id)
        if o is None:
            continue
        segments.append({"segment_id": seg.id, "start": o["start"], "end": o["end"], "text": seg.text})
        for w in v.words or []:
            words.append({"word": w["word"], "segment_id": seg.id,
                          "start": round(o["start"] + w["start"], 3),
                          "end": round(min(o["end"], o["start"] + w["end"]), 3)})
    return {"seconds": ((ep.production or {}).get("mix") or {}).get("seconds"),
            "current": mix_is_current(ep), "segments": segments, "words": words}


# --- Cover ------------------------------------------------------------------


def enqueue_cover(ep, art=None):
    """Queue a title image for the narration. Best effort."""
    from .jobs import async_enabled, auto_model_for, enqueue_job, kick_dispatch

    if ep.cover_request_id or not async_enabled():
        return None
    model = auto_model_for(ep.user, "image")
    if not model:
        return None
    lead = ""
    if art is not None:
        lead = " ".join(b.text for b in art.blocks if b.kind != "heading")[:900]
    # Putting the title in the prompt makes image models paint it as lettering,
    # so ask for a picture of the idea instead.
    concept, _ = _ask_llm(
        ep.user,
        "You are an art director. In one sentence of at most 40 words, describe a single striking "
        "image that captures the idea of this essay: concrete objects and a scene, no people's "
        "faces, no words, no signs, no screens with text. Reply with the sentence only.",
        f"Title: {ep.title}\n\n{lead}", max_tokens=120,
    )
    concept = re.sub(r"\s+", " ", concept).strip().strip('"') or "A single symbolic still life that suggests the essay's theme"
    prompt = (
        f"{concept} Editorial illustration, bold shapes, rich colour, magazine cover quality. "
        "No text, no letters, no numbers, no logos."
    )
    job = enqueue_job(
        ep.user, "IMAGE", {"model": model, "prompt": prompt, "n": 1, "size": "1344x768"},
        model_name=model, visibility="SECRET", idempotency_key=f"narration-cover:{ep.id}", max_attempts=2,
    )
    kick_dispatch()
    ep.cover_request = job
    ep.save(update_fields=["cover_request", "modified_on"])
    return job


# --- The run ----------------------------------------------------------------


def _title_from_text(text: str) -> str:
    """A working title for pasted text: its first line, kept short."""
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    first = re.split(r"(?<=[.!?])\s", first)[0].rstrip(".")
    return first if len(first) <= 70 else first[:68].rstrip() + "…"


def start(user, *, url: str = "", text: str = "", title: str = "", voice_sample=None):
    """Create the episode for a narration and queue the work. Returns the
    episode immediately (stage "reading"); read it again to follow progress."""
    from .models import Episode

    url, text = (url or "").strip(), (text or "").strip()
    if not url and not text:
        raise article_mod.ArticleError("Give a link or some text to narrate.")
    # A lone link pasted into the text box is a link.
    if not url and re.fullmatch(r"(https?://)?[\w.-]+\.[a-z]{2,}(/\S*)?", text, re.I):
        url, text = text, ""
    sample = voice_sample or default_voice_sample(user)
    ep = Episode.objects.create(
        user=user, title=(title or url or _title_from_text(text))[:200] or "Narration",
        voice_sample=sample,
        # A take the judge calls "minor issues, acceptable" (8 of 10) is good
        # enough to keep; the Studio's stricter default suits hand-polishing.
        settings={"accept_score": 8.0},
        source={"source_url": url} if url else {"via": "text"},
        production={"stage": "reading", "started": timezone.now().isoformat(), "events": [],
                    "request": {"url": url, "text": text, "title": title}},
    )
    _log(ep, "Reading the link" if url else "Reading the text")
    from .studio_views import _async_ok
    from .tasks import narrate_episode

    if _async_ok():
        narrate_episode.delay(ep.id)
    else:
        run(ep)
    return ep


def run(ep):
    """Do the whole narration for ``ep``. Never raises: a failure is recorded
    on the episode as stage "error" with a message a person can read."""
    try:
        _run(ep)
    except article_mod.ArticleError as e:
        _log(ep, str(e), stage="error", error=str(e), finished=timezone.now().isoformat())
    except Exception as e:  # noqa: BLE001
        logger.exception("narrate: episode %s failed", ep.id)
        _log(ep, "Something went wrong while narrating.", stage="error",
             error=f"{type(e).__name__}: {str(e)[:200]}", finished=timezone.now().isoformat())


def _run(ep):
    from .jobs import auto_model_for
    from .models import Segment
    from .openai_views import _find_voice_provider

    user = ep.user
    req = (ep.production or {}).get("request") or {}
    models = {}

    # read
    if req.get("url"):
        art = article_mod.read_article(req["url"], scrape=lambda u: _club_scrape(user, u))
    else:
        art = article_mod.article_from_text(req.get("text") or "", title=req.get("title") or "")
    if art.words > MAX_WORDS:
        raise article_mod.ArticleError(
            f"That is {art.words:,} words; narration takes up to {MAX_WORDS:,} at a time.")
    if req.get("title"):
        art.title = req["title"]
    ep.title = (art.title or ep.title or "Narration")[:200]
    ep.source = {k: v for k, v in art.as_dict().items() if k != "blocks"}
    ep.save(update_fields=["title", "source", "modified_on"])
    if art.via == "scrape":
        models["read"] = auto_model_for(user, "scrape")
    who = f" by {art.author}" if art.author else ""
    _log(ep, f"Found “{ep.title}”{who}: {art.words:,} words", stage="planning", models=models)
    enqueue_cover(ep, art)
    if ep.cover_request_id:
        models["cover"] = ep.cover_request.model_name
    if _cancelled(ep):
        return _stop(ep)

    # plan
    pieces = plan_script(art)
    body_text = " ".join(p["text"] for p in pieces)
    lexicon, judge = suggest_lexicon(user, body_text)
    if lexicon:
        ep.settings = {**(ep.settings or {}), "lexicon": {**lexicon, **((ep.settings or {}).get("lexicon") or {})}}
        ep.save(update_fields=["settings", "modified_on"])
    segments = Segment.objects.bulk_create([
        Segment(episode=ep, position=i, text=p["text"], status=Segment.STATUS_QUEUED)
        for i, p in enumerate(pieces)
    ])
    segments = list(ep.segments.order_by("position", "id"))
    voice = _find_voice_provider(user, ep.voice_model or None)
    models.update({
        "voice": (voice.name if voice else "") or "",
        "clean": auto_model_for(user, "audio-enhance"),
        "check": auto_model_for(user, "stt"),
        "judge": judge or auto_model_for(user, ""),
    })
    said = f", with {len(lexicon)} pronunciation note{'s' if len(lexicon) != 1 else ''}" if lexicon else ""
    _log(ep, f"Planned {len(segments)} pieces{said}", stage="voicing", models=models,
         kinds={str(s.id): p["kind"] for s, p in zip(segments, pieces)},
         voice={"sample": ep.voice_sample.speaker_name if ep.voice_sample_id else None})
    if voice is None:
        raise article_mod.ArticleError("No voice model is online right now, so nothing could be voiced.")

    # voice
    for n, seg in enumerate(segments, 1):
        if _cancelled(ep):
            return _stop(ep)
        try:
            result = narration.produce_segment(seg)
        except Exception as e:  # noqa: BLE001 - one bad piece must not stop the rest
            logger.exception("narrate: segment %s failed", seg.id)
            seg.status = Segment.STATUS_ERROR
            seg.save(update_fields=["status", "modified_on"])
            result = {"ok": False, "error": str(e)[:160]}
        if not result.get("ok"):
            _log(ep, f"Piece {n} of {len(segments)} could not be voiced")
        elif result.get("accepted"):
            takes = result.get("attempts", 1)
            _log(ep, f"Piece {n} of {len(segments)} voiced" + (f" on take {takes}" if takes > 1 else ""))
        else:
            _log(ep, f"Piece {n} of {len(segments)} kept its best take but needs a listen")
        # With no voice to clone, the first good take becomes the voice for
        # the rest, so the narrator does not change from piece to piece.
        if not ep.voice_sample_id and result.get("accepted"):
            seg.refresh_from_db()
            try:
                narration.save_variant_as_voice_sample(
                    seg.selected_variant, speaker_name="Narrator", label=ep.title[:60], use_for_episode=True)
                ep.refresh_from_db()
                _log(ep, "Kept this voice for the rest of the narration")
            except Exception:  # noqa: BLE001
                logger.warning("narrate: could not lock the voice", exc_info=True)

    # mix
    _log(ep, "Joining the pieces", stage="mixing")
    asset = mix(ep)
    if asset is None:
        raise article_mod.ArticleError("None of the pieces could be voiced.")
    counts = _counts(ep)
    _log(ep, f"Done: {_clock(asset.duration_seconds)} of audio"
         + (f", {counts['flagged'] + counts['error']} piece(s) to review" if counts["flagged"] + counts["error"] else ""),
         stage="done", finished=timezone.now().isoformat())


def _stop(ep):
    _log(ep, "Stopped", stage="stopped", finished=timezone.now().isoformat())
    from .models import Segment
    ep.segments.filter(status=Segment.STATUS_QUEUED).update(status=Segment.STATUS_PENDING)


def _counts(ep) -> dict:
    from .models import Segment

    rows = list(ep.segments.values_list("status", flat=True))
    return {
        "total": len(rows),
        "ready": rows.count(Segment.STATUS_READY),
        "flagged": rows.count(Segment.STATUS_FLAGGED),
        "error": rows.count(Segment.STATUS_ERROR),
        "working": rows.count(Segment.STATUS_GENERATING),
        "waiting": rows.count(Segment.STATUS_QUEUED) + rows.count(Segment.STATUS_PENDING),
    }


def _clock(seconds) -> str:
    seconds = int(round(seconds or 0))
    return f"{seconds // 60}:{seconds % 60:02d}"


def summary(ep) -> dict:
    """The run in the shape clients show: stage, counts and a fraction done."""
    prod = ep.production or {}
    counts = _counts(ep)
    stage = prod.get("stage") or ""
    done = counts["ready"] + counts["flagged"] + counts["error"]
    fraction = {"reading": 0.02, "planning": 0.06}.get(stage)
    if fraction is None:
        voiced = done / counts["total"] if counts["total"] else 0
        fraction = 1.0 if stage == "done" else 0.08 + 0.88 * voiced if stage in ("voicing", "mixing") else voiced
    return {
        "stage": stage, "active": stage in ACTIVE, "error": prod.get("error") or "",
        "fraction": round(min(1.0, fraction), 3), "counts": counts,
        "models": prod.get("models") or {}, "voice": prod.get("voice") or {},
        "events": (prod.get("events") or [])[-12:],
        "started": prod.get("started"), "finished": prod.get("finished"),
        "mix": {k: v for k, v in (prod.get("mix") or {}).items() if k != "signature"},
        "mix_current": mix_is_current(ep) if ep.audio_id else False,
        "kinds": prod.get("kinds") or {},
    }
