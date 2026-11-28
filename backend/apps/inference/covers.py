"""Automatic album art and titles for songs.

When a MUSIC request finishes without a cover, queue one square image for it
through the normal async image pipeline and link the result as the song's
``cover_request``. Nothing here blocks or can fail the song: every step is
best-effort and a song with no cover simply keeps its placeholder.

Two ``post_save`` receivers do the work:

- a finished song with no cover enqueues an IMAGE job tagged
  ``payload["cover_for"] = <song id>`` (idempotent per song);
- a finished IMAGE job carrying that tag is linked to the song, unless the
  owner has set a cover in the meantime.

A finished song also gets a title: the one the client sent, or a short one
written by an LLM (``name_song``, run as a Celery task so the generation
request never waits on it).

``enqueue_missing_covers`` backfills songs that predate this.
"""
import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

COVER_SIZE = "1024x1024"
# Below normal generations: a cover never delays work someone asked for.
COVER_PRIORITY = -10

_LOOKS = (
    "bold graphic illustration",
    "dreamy analog film photograph",
    "textured oil painting",
    "minimal geometric poster design",
    "surreal collage",
    "soft watercolor wash",
    "neon-lit cinematic still",
    "risograph print with grain",
)


def cover_prompt(song) -> str:
    """An image prompt for a song's cover, from what the song was asked to be.

    The look is picked from the song id so a batch of similar prompts ("edm",
    "edm", "edm") still gets visibly different covers, and the same song always
    gets the same look if its cover is regenerated.
    """
    p = song.payload or {}
    style = " ".join(str(p.get("prompt") or "").split())[:300]
    lyrics = " ".join(str(p.get("lyrics") or "").split())
    # Structure tags like [verse] carry no imagery.
    words = [w for w in lyrics.split() if not (w.startswith("[") and w.endswith("]"))]
    lyric_hint = " ".join(words)[:160]
    look = _LOOKS[song.id % len(_LOOKS)]
    parts = [
        "Square album cover art",
        f"for a song described as: {style}" if style else "for an instrumental track",
    ]
    if lyric_hint:
        parts.append(f"with lyrics that begin: {lyric_hint}")
    return (
        ", ".join(parts)
        + f". Style: {look}. One strong central image that captures the mood: "
        "a place, an object, weather, light or an abstract form. No portrait and "
        "no faces unless the description names a person. Cohesive colour "
        "palette, rich detail. No text, no letters, no logos, no watermark."
    )


_TITLE_SYSTEM = (
    "You name songs. Given a description of a song's style and its lyrics, "
    "reply with ONLY a title: 1 to 4 words, in Title Case, evocative and "
    "specific, with no quotes, no trailing punctuation and no emoji. Do not "
    "use genre names as the title."
)


def name_song(song_id) -> str:
    """Give a finished, untitled song a title. Returns the title set, or ''."""
    import requests

    from .chat_threads import _clean_title
    from .jobs import auto_model_for
    from .models import InferenceRequest
    from .openai_views import _find_provider_for_model, _retry_endpoint
    from .views import _tailnet_proxies

    song = InferenceRequest.objects.filter(id=song_id).select_related("user").first()
    if song is None or song.inference_type != "MUSIC" or song.title or song.user is None:
        return ""
    p = song.payload or {}
    title = " ".join(str(p.get("title") or "").split())[:160]
    if not title:
        model = auto_model_for(song.user, "llm")
        pm = _find_provider_for_model(song.user, model) if model else None
        if pm is None:
            return ""
        described = f"Style: {str(p.get('prompt') or '')[:600]}"
        if p.get("lyrics"):
            described += f"\n\nLyrics:\n{str(p['lyrics'])[:1200]}"
        try:
            resp = requests.post(
                _retry_endpoint(pm.provider, "/chat/completions"),
                json={
                    "model": pm.name or model,
                    "messages": [
                        {"role": "system", "content": _TITLE_SYSTEM},
                        {"role": "user", "content": described + "\n\nTitle:"},
                    ],
                    "stream": False,
                    "max_tokens": 24,
                    # Warm: forty songs prompted "edm" should not share a name.
                    "temperature": 1.0,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=60, verify=False, proxies=_tailnet_proxies(),
            )
            resp.raise_for_status()
            raw = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
        except Exception:
            logger.warning("song title generation failed for %s", song_id, exc_info=True)
            return ""
        title = _clean_title(raw)[:160]
    if not title:
        return ""
    # Only fill a blank: a rename by the owner in the meantime wins.
    InferenceRequest.objects.filter(id=song_id, title="").update(title=title)
    return title


def _queue_title(song_id):
    from .jobs import async_enabled

    if not async_enabled():
        return
    try:
        from .tasks import name_song as name_song_task

        name_song_task.delay(song_id)
    except Exception:
        logger.warning("could not queue song title for %s", song_id, exc_info=True)


def enqueue_cover(song):
    """Queue cover art for one finished song. Returns the job, or None when
    there is nothing to do or nothing to do it with."""
    from .jobs import async_enabled, auto_model_for, enqueue_job, kick_dispatch

    if not getattr(settings, "AUTO_COVER_ART", True) or not async_enabled():
        return None
    if (
        song.inference_type != "MUSIC"
        or song.status != "PROCESSED"
        or song.cover_request_id is not None
        or song.user_id is None
    ):
        return None
    from .models import InferenceRequest

    # Saves of a finished song are frequent (stars, visibility); the common
    # case of "already has a cover job" must cost one indexed lookup. This also
    # means a cover job that failed for good is not retried on every save.
    key = f"cover:{song.id}"
    if InferenceRequest.objects.filter(user_id=song.user_id, idempotency_key=key).exists():
        return None
    model = auto_model_for(song.user, "image")
    if not model:
        return None
    job = enqueue_job(
        song.user,
        "IMAGE",
        {
            "model": model,
            "prompt": cover_prompt(song),
            "n": 1,
            "size": COVER_SIZE,
            "cover_for": song.id,
        },
        model_name=model,
        # The cover is shown wherever the song is, so it shares its audience.
        visibility=song.visibility or "",
        idempotency_key=key,
        priority=COVER_PRIORITY,
        max_attempts=2,
    )
    kick_dispatch()
    return job


def link_cover(image_job) -> bool:
    """Attach a finished cover image to the song it was made for."""
    from .models import InferenceRequest, MediaAsset

    song_id = (image_job.payload or {}).get("cover_for")
    if not song_id or image_job.status != "PROCESSED":
        return False
    if not image_job.assets.filter(kind=MediaAsset.OUTPUT_IMAGE).exists():
        return False
    # Only fill an empty slot: a cover the owner picked by hand wins.
    updated = InferenceRequest.objects.filter(
        id=song_id, user_id=image_job.user_id, cover_request__isnull=True
    ).update(cover_request=image_job)
    return bool(updated)


def enqueue_missing_covers(user, limit=25) -> int:
    """Queue covers for ``user``'s finished songs that have none. Returns how
    many were queued (songs whose cover job already exists are skipped)."""
    from .models import InferenceRequest

    songs = (
        InferenceRequest.objects.filter(
            user=user, inference_type="MUSIC", status="PROCESSED",
            cover_request__isnull=True,
        )
        .exclude(
            id__in=_songs_with_cover_jobs(user)
        )
        .order_by("-id")[:limit]
    )
    queued = 0
    for song in songs:
        if enqueue_cover(song) is not None:
            queued += 1
    # Name the untitled ones while we are here.
    untitled = InferenceRequest.objects.filter(
        user=user, inference_type="MUSIC", status="PROCESSED", title=""
    ).order_by("-id").values_list("id", flat=True)[:limit]
    for song_id in untitled:
        _queue_title(song_id)
    return queued


def _songs_with_cover_jobs(user):
    from .models import InferenceRequest

    keys = InferenceRequest.objects.filter(
        user=user, idempotency_key__startswith="cover:"
    ).values_list("idempotency_key", flat=True)
    ids = []
    for key in keys:
        try:
            ids.append(int(key.split(":", 1)[1]))
        except ValueError:
            continue
    return ids


def missing_cover_count(user) -> int:
    from .models import InferenceRequest

    return (
        InferenceRequest.objects.filter(
            user=user, inference_type="MUSIC", status="PROCESSED",
            cover_request__isnull=True,
        )
        .exclude(id__in=_songs_with_cover_jobs(user))
        .count()
    )


@receiver(post_save, dispatch_uid="inference_auto_cover_art")
def _on_request_saved(sender, instance, **kwargs):
    from .models import InferenceRequest

    if sender is not InferenceRequest or instance.status != "PROCESSED":
        return
    created = kwargs.get("created")
    update_fields = kwargs.get("update_fields")
    # Name the song once, on the save that marks it finished.
    if (
        instance.inference_type == "MUSIC"
        and not instance.title
        and (created or update_fields is None or "status" in update_fields)
    ):
        untitled_id = instance.id
        transaction.on_commit(lambda: _queue_title(untitled_id))
    if instance.inference_type == "MUSIC" and instance.cover_request_id is None:
        song_id = instance.id

        def _enqueue():
            try:
                song = InferenceRequest.objects.filter(id=song_id).first()
                if song is not None:
                    enqueue_cover(song)
            except Exception:
                logger.warning("auto cover enqueue failed for %s", song_id, exc_info=True)

        transaction.on_commit(_enqueue)
    elif instance.inference_type == "IMAGE" and (instance.payload or {}).get("cover_for"):
        job_id = instance.id

        def _link():
            try:
                job = InferenceRequest.objects.filter(id=job_id).first()
                if job is not None:
                    link_cover(job)
            except Exception:
                logger.warning("auto cover link failed for %s", job_id, exc_info=True)

        transaction.on_commit(_link)
