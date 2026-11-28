"""HTTP API for the Narration Studio (PRD 12 §5.4).

Episode + Segment CRUD, segment reorder, and selecting a Segment's active take.
All owner-scoped to a full member. Generation-bearing actions (retake, trim,
StudioVoice clean, dynamic image series) build on this and land in later
increments — this is the data spine the Studio UI reads and writes.
"""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsFullMember

from .models import Episode, Segment, Variant, VoiceSample
from .studio_serializers import (
    EpisodeListSerializer,
    EpisodeSerializer,
    SegmentSerializer,
)


def _episodes_for(user):
    return Episode.objects.filter(user=user)


class EpisodeListCreateView(APIView):
    """GET /v1/episodes — your episodes. POST — create one (``title`` required)."""

    permission_classes = [IsFullMember]

    def get(self, request):
        qs = _episodes_for(request.user).prefetch_related("segments")
        return Response({"data": EpisodeListSerializer(qs, many=True, context={"request": request}).data})

    def post(self, request):
        title = (request.data.get("title") or "").strip()
        if not title:
            return Response({"detail": "`title` is required."}, status=400)
        ep = Episode.objects.create(
            user=request.user,
            title=title[:200],
            description=(request.data.get("description") or "").strip(),
        )
        return Response(
            EpisodeSerializer(ep, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class EpisodeFromTextView(APIView):
    """POST /v1/episodes/from-text — paste a block of text and split it into an
    Episode of narration-sized Segments. Body: ``{text, [title], [target_words]}``
    (target_words groups whole sentences toward that size; default 32)."""

    permission_classes = [IsFullMember]

    def post(self, request):
        from . import narration

        body = request.data if isinstance(request.data, dict) else {}
        text = (body.get("text") or "").strip()
        if not text:
            return Response({"detail": "`text` is required."}, status=400)
        try:
            target = int(body.get("target_words") or narration.CHUNK_TARGET_WORDS)
        except (TypeError, ValueError):
            return Response({"detail": "`target_words` must be a number."}, status=400)

        chunks = narration.split_into_segments(text, target_words=target)
        if not chunks:
            return Response({"detail": "No sentences found in `text`."}, status=400)

        title = (body.get("title") or chunks[0])[:200].strip() or "Narration"
        ep = Episode.objects.create(
            user=request.user, title=title,
            description=(body.get("description") or "").strip(),
        )
        Segment.objects.bulk_create([
            Segment(episode=ep, position=i, text=c) for i, c in enumerate(chunks)
        ])
        return Response(
            EpisodeSerializer(ep, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class EpisodeDetailView(APIView):
    """GET/PATCH/DELETE /v1/episodes/<id> — the full workspace payload."""

    permission_classes = [IsFullMember]

    def _get(self, request, id):
        return get_object_or_404(_episodes_for(request.user), id=id)

    def get(self, request, id):
        ep = self._get(request, id)
        return Response(EpisodeSerializer(ep, context={"request": request}).data)

    def patch(self, request, id):
        ep = self._get(request, id)
        fields = ["modified_on"]
        if "title" in request.data:
            title = (request.data.get("title") or "").strip()
            if not title:
                return Response({"detail": "`title` can't be blank."}, status=400)
            ep.title = title[:200]
            fields.append("title")
        if "description" in request.data:
            ep.description = (request.data.get("description") or "").strip()
            fields.append("description")
        if "voice_model" in request.data:
            ep.voice_model = (request.data.get("voice_model") or "").strip()[:200]
            fields.append("voice_model")
        if "settings" in request.data:
            from . import narration

            clean, err = narration.validate_settings(request.data.get("settings"))
            if err:
                return Response({"detail": err}, status=400)
            merged = dict(ep.settings or {})
            for k, v in clean.items():
                if v is None:
                    merged.pop(k, None)
                else:
                    merged[k] = v
            ep.settings = merged
            fields.append("settings")
        if "voice_sample_id" in request.data:
            vsid = request.data.get("voice_sample_id")
            if vsid in (None, ""):
                ep.voice_sample = None
            elif VoiceSample.objects.filter(id=vsid, user=request.user).exists():
                ep.voice_sample_id = vsid
            else:
                return Response({"detail": "Unknown voice sample."}, status=400)
            fields.append("voice_sample")
        ep.save(update_fields=fields)
        return Response(EpisodeSerializer(ep, context={"request": request}).data)

    def delete(self, request, id):
        self._get(request, id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SegmentListCreateView(APIView):
    """POST /v1/episodes/<id>/segments — append a segment (``text`` required)."""

    permission_classes = [IsFullMember]

    def post(self, request, id):
        ep = get_object_or_404(_episodes_for(request.user), id=id)
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"detail": "`text` is required."}, status=400)
        last = ep.segments.order_by("-position").first()
        seg = Segment.objects.create(
            episode=ep,
            text=text,
            position=(last.position + 1) if last else 0,
        )
        # Optional per-segment voice override.
        vsid = request.data.get("voice_sample_id")
        if vsid and VoiceSample.objects.filter(id=vsid, user=request.user).exists():
            seg.voice_sample_id = vsid
            seg.save(update_fields=["voice_sample", "modified_on"])
        return Response(
            SegmentSerializer(seg, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class SegmentDetailView(APIView):
    """PATCH/DELETE /v1/segments/<id> — edit text/voice or remove the segment.
    Editing the text stashes the prior text in ``original_text`` once, so the
    Studio can offer an undo."""

    permission_classes = [IsFullMember]

    def _get(self, request, id):
        return get_object_or_404(
            Segment.objects.filter(episode__user=request.user), id=id
        )

    def patch(self, request, id):
        seg = self._get(request, id)
        fields = []
        if "text" in request.data:
            new_text = (request.data.get("text") or "").strip()
            if not new_text:
                return Response({"detail": "`text` can't be blank."}, status=400)
            if new_text != seg.text:
                if not seg.original_text:
                    seg.original_text = seg.text
                    fields.append("original_text")
                seg.text = new_text
                fields.append("text")
                # The current take no longer says this line: back to pending so
                # autopilot (produce) re-voices it without needing force.
                if seg.status in (Segment.STATUS_READY, Segment.STATUS_FLAGGED):
                    seg.status = Segment.STATUS_PENDING
                    fields.append("status")
        if "voice_sample_id" in request.data:
            vsid = request.data.get("voice_sample_id")
            if vsid in (None, ""):
                seg.voice_sample = None
            elif VoiceSample.objects.filter(id=vsid, user=request.user).exists():
                seg.voice_sample_id = vsid
            else:
                return Response({"detail": "Unknown voice sample."}, status=400)
            fields.append("voice_sample")
        if fields:
            seg.save(update_fields=fields + ["modified_on"])
        return Response(SegmentSerializer(seg, context={"request": request}).data)

    def delete(self, request, id):
        self._get(request, id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SegmentReorderView(APIView):
    """POST /v1/episodes/<id>/segments/reorder — body ``{order: [seg_id, …]}``
    sets each listed segment's ``position`` to its index. Ids not owned by the
    episode are ignored."""

    permission_classes = [IsFullMember]

    def post(self, request, id):
        ep = get_object_or_404(_episodes_for(request.user), id=id)
        order = request.data.get("order")
        if not isinstance(order, list):
            return Response({"detail": "`order` must be a list of segment ids."}, status=400)
        owned = {s.id: s for s in ep.segments.all()}
        with transaction.atomic():
            for idx, sid in enumerate(order):
                seg = owned.get(sid)
                if seg is not None and seg.position != idx:
                    seg.position = idx
                    seg.save(update_fields=["position", "modified_on"])
        ep.refresh_from_db()
        return Response(EpisodeSerializer(ep, context={"request": request}).data)


class VariantSelectView(APIView):
    """POST /v1/segments/<id>/variants/<vid>/select — make a take the active one
    (what plays/exports). The variant must belong to the segment."""

    permission_classes = [IsFullMember]

    def post(self, request, id, vid):
        seg = get_object_or_404(
            Segment.objects.filter(episode__user=request.user), id=id
        )
        variant = get_object_or_404(Variant, id=vid, segment=seg)
        seg.selected_variant = variant
        seg.status = Segment.STATUS_READY
        seg.save(update_fields=["selected_variant", "status", "modified_on"])
        return Response(SegmentSerializer(seg, context={"request": request}).data)


class SegmentProcessView(APIView):
    """POST /v1/segments/<id>/process — run the narration pipeline (clean → ASR →
    trim → grade) on the segment's selected take. Runs off the request path when
    a Celery worker is available; otherwise inline. Returns the segment (202)."""

    permission_classes = [IsFullMember]

    def post(self, request, id):
        from django.conf import settings

        from . import jobs, narration
        from .tasks import process_segment as process_segment_task

        seg = get_object_or_404(
            Segment.objects.filter(episode__user=request.user)
            .select_related("episode", "selected_variant"),
            id=id,
        )
        if seg.selected_variant_id is None or seg.selected_variant.audio_id is None:
            return Response(
                {"detail": "Segment has no audio take to process. Generate one first."},
                status=status.HTTP_409_CONFLICT,
            )
        if jobs.async_enabled() and not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            # Queued until the worker actually acquires the (single) clean device;
            # narration flips it to 'generating' the moment work starts.
            seg.status = Segment.STATUS_QUEUED
            seg.save(update_fields=["status", "modified_on"])
            process_segment_task.delay(seg.id)
        else:
            narration.process_segment(seg)
            seg.refresh_from_db()
        return Response(
            SegmentSerializer(seg, context={"request": request}).data,
            status=status.HTTP_202_ACCEPTED,
        )


class SegmentRegenerateView(APIView):
    """POST /v1/segments/<id>/regenerate — generate a fresh take (Dia, honoring
    the segment's voice sample) and run the full pipeline on it. Optional body:
    ``{text, seed}`` (text overrides the spoken line; seed pins the voice).
    Returns the segment (202)."""

    permission_classes = [IsFullMember]

    def post(self, request, id):
        from django.conf import settings

        from . import jobs, narration
        from .tasks import regenerate_segment as regenerate_task

        seg = get_object_or_404(
            Segment.objects.filter(episode__user=request.user).select_related("episode"),
            id=id,
        )
        body = request.data if isinstance(request.data, dict) else {}
        text_override = body.get("text")
        seed = body.get("seed")
        try:
            seed = int(seed) if seed not in (None, "") else None
        except (TypeError, ValueError):
            return Response({"detail": "`seed` must be an integer."}, status=400)

        if jobs.async_enabled() and not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            # Queued until the worker acquires the (single) voice device; narration
            # flips it to 'generating' the moment the Dia call starts.
            seg.status = Segment.STATUS_QUEUED
            seg.save(update_fields=["status", "modified_on"])
            regenerate_task.delay(seg.id, text_override=text_override, seed=seed)
        else:
            narration.regenerate_segment(seg, text_override=text_override, seed=seed)
            seg.refresh_from_db()
        return Response(
            SegmentSerializer(seg, context={"request": request}).data,
            status=status.HTTP_202_ACCEPTED,
        )


class SegmentRetrimView(APIView):
    """POST /v1/segments/<id>/retrim — re-cut the segment's selected take from
    manual *remove* ranges. Body: ``{remove: [[start, end], …]}`` (seconds, on
    the enhanced/untrimmed timeline). Rebuilds the trimmed audio + words and
    returns the segment. Runs inline — it's a fast central FFmpeg cut."""

    permission_classes = [IsFullMember]

    def post(self, request, id):
        from . import narration

        seg = get_object_or_404(
            Segment.objects.filter(episode__user=request.user)
            .select_related("episode", "selected_variant"),
            id=id,
        )
        variant = seg.selected_variant
        if variant is None:
            return Response({"detail": "Segment has no take to trim."}, status=409)

        body = request.data if isinstance(request.data, dict) else {}
        remove = body.get("remove") or []
        if not isinstance(remove, list):
            return Response({"detail": "`remove` must be a list of [start, end] ranges."}, status=400)

        result = narration.retrim_variant(variant, remove)
        if not result.get("ok"):
            return Response({"detail": result.get("error") or "Re-trim failed."}, status=400)
        seg.refresh_from_db()
        return Response(SegmentSerializer(seg, context={"request": request}).data)


class StudioVoicesView(APIView):
    """GET /v1/studio/voices — the voices the editor can pick from:

    - ``voices``: reachable TTS / voice models (``voice_cloning`` flags the ones,
      like Dia, that can clone a reference sample). Empty when no voice service
      is online — the UI then explains generation is unavailable.
    - ``samples``: the user's Dia voice samples that have a transcript (required
      to clone), so they can pick which voice to speak in.
    """

    permission_classes = [IsFullMember]

    def get(self, request):
        from .openai_views import _has_feature, _online_providers

        seen, voices = set(), []
        for provider in _online_providers(request.user):
            for pm in (
                provider.models.filter(is_active=True)
                .filter(service__service_type="tts")
                .select_related("provider", "service", "catalog_model")
            ):
                name = pm.name or ""
                if not name or name in seen:
                    continue
                seen.add(name)
                voices.append({
                    "model": name,
                    "label": (getattr(pm.catalog_model, "display_name", "") or name),
                    "provider": provider.name or provider.tailnet_hostname,
                    "voice_cloning": bool(_has_feature(pm, "voice-cloning")),
                })
        voices.sort(key=lambda v: (not v["voice_cloning"], v["label"].lower()))

        samples = [
            {
                "id": vs.id,
                "name": (f"{vs.speaker_name} · {vs.label}"
                         if vs.label else vs.speaker_name),
                "has_transcript": bool((vs.transcript or "").strip()),
            }
            for vs in VoiceSample.objects.filter(user=request.user)
            .select_related("audio").order_by("speaker_name", "label")
        ]
        return Response({"voices": voices, "samples": samples})


def _async_ok():
    from django.conf import settings

    from . import jobs
    return jobs.async_enabled() and not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)


def _int_or_none(v, name, lo, hi):
    if v in (None, ""):
        return None, None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None, f"`{name}` must be an integer."
    if not lo <= n <= hi:
        return None, f"`{name}` must be between {lo} and {hi}."
    return n, None


class EpisodeProduceView(APIView):
    """POST /v1/episodes/<id>/produce — narration autopilot. For each segment
    that isn't ``ready`` (all of them with ``force``): generate a take, clean it
    (StudioVoice), transcribe it (word timestamps), trim dead air, level it, grade
    the transcript against the line, and retake while the grade is poor — up to
    ``attempts`` takes, keeping the best. Body (all optional): ``{force,
    attempts, accept}``; defaults come from the episode's settings."""

    permission_classes = [IsFullMember]

    def post(self, request, id):
        from . import narration
        from .tasks import produce_episode as produce_task

        ep = get_object_or_404(_episodes_for(request.user), id=id)
        body = request.data if isinstance(request.data, dict) else {}
        attempts, err = _int_or_none(body.get("attempts"), "attempts", 1, 8)
        if err:
            return Response({"detail": err}, status=400)
        accept = body.get("accept")
        try:
            accept = float(accept) if accept not in (None, "") else None
        except (TypeError, ValueError):
            return Response({"detail": "`accept` must be a number."}, status=400)
        force = bool(body.get("force"))
        todo = [s.id for s in ep.segments.all() if force or s.status != Segment.STATUS_READY]
        Segment.objects.filter(id__in=todo).update(status=Segment.STATUS_QUEUED)
        if _async_ok():
            produce_task.delay(ep.id, force=force, attempts=attempts, accept=accept)
        else:
            narration.produce_episode(ep, force=force, attempts=attempts, accept=accept)
        ep.refresh_from_db()
        return Response(EpisodeSerializer(ep, context={"request": request}).data,
                        status=status.HTTP_202_ACCEPTED)


class SegmentTakesView(APIView):
    """POST /v1/segments/<id>/takes — audition several takes of one line. Body:
    ``{count}`` (1-8, random seeds) or ``{seeds: [..]}``. Every take is fully
    processed and scored; the best becomes the selected take. Use it to design a
    voice: audition seeds, then save the best take as a voice sample."""

    permission_classes = [IsFullMember]

    def post(self, request, id):
        from . import narration
        from .tasks import produce_segment as produce_task

        seg = get_object_or_404(
            Segment.objects.filter(episode__user=request.user).select_related("episode"), id=id)
        body = request.data if isinstance(request.data, dict) else {}
        seeds = body.get("seeds")
        if seeds is not None and (
                not isinstance(seeds, list) or not 1 <= len(seeds) <= 8
                or not all(isinstance(x, int) and not isinstance(x, bool) for x in seeds)):
            return Response({"detail": "`seeds` must be a list of 1-8 integers."}, status=400)
        count, err = _int_or_none(body.get("count"), "count", 1, 8)
        if err:
            return Response({"detail": err}, status=400)
        count = count or 4
        seg.status = Segment.STATUS_QUEUED
        seg.save(update_fields=["status", "modified_on"])
        if _async_ok():
            produce_task.delay(seg.id, attempts=count, explore=True, seeds=seeds)
        else:
            narration.produce_segment(seg, attempts=count, explore=True, seeds=seeds)
            seg.refresh_from_db()
        return Response(SegmentSerializer(seg, context={"request": request}).data,
                        status=status.HTTP_202_ACCEPTED)


class VariantSaveVoiceView(APIView):
    """POST /v1/segments/<id>/variants/<vid>/save-voice — save this take (its
    cleaned, trimmed audio) to your voice library. Body: ``{speaker_name,
    [label], [is_default], [use_for_episode]}``. With ``use_for_episode`` the
    episode clones this voice for every later take."""

    permission_classes = [IsFullMember]

    def post(self, request, id, vid):
        from . import narration

        seg = get_object_or_404(
            Segment.objects.filter(episode__user=request.user).select_related("episode"), id=id)
        variant = get_object_or_404(Variant.objects.filter(segment=seg), id=vid)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            sample = narration.save_variant_as_voice_sample(
                variant, speaker_name=body.get("speaker_name") or "Narrator",
                label=body.get("label") or "", make_default=bool(body.get("is_default")),
                use_for_episode=bool(body.get("use_for_episode")))
        except ValueError as e:
            return Response({"detail": str(e)}, status=409)
        return Response({"id": sample.id, "speaker_name": sample.speaker_name,
                         "label": sample.label, "is_default": sample.is_default,
                         "transcript": sample.transcript,
                         "duration_seconds": sample.duration_seconds},
                        status=status.HTTP_201_CREATED)


class EpisodeExportView(APIView):
    """GET /v1/episodes/<id>/export — a zip of the selected takes in order
    (``01.wav`` ...) plus ``manifest.json`` (text, spoken form, duration, word
    timestamps, grade, seed per segment)."""

    permission_classes = [IsFullMember]

    def get(self, request, id):
        from django.http import HttpResponse
        from django.utils.text import slugify

        from . import narration

        ep = get_object_or_404(_episodes_for(request.user), id=id)
        data = narration.export_episode_zip(ep)
        resp = HttpResponse(data, content_type="application/zip")
        name = slugify(ep.title)[:60] or f"episode-{ep.id}"
        resp["Content-Disposition"] = f'attachment; filename="{name}.zip"'
        return resp


# --- "Narrate this": a link or text in, a finished narration out -------------


class NarrationCreateView(APIView):
    """POST /v1/narrations — narrate an article or some text.

    Body: ``url`` (any page, or a Hacker News discussion link) or ``text``;
    optional ``title`` and ``voice_sample_id`` (default: your default voice).
    Answers 202 with the episode straight away. Read ``GET /v1/episodes/<id>``
    to follow it: ``narration.stage`` moves through reading, planning, voicing
    and mixing to ``done``, and ``audio_url`` is the finished file."""

    permission_classes = [IsFullMember]

    def post(self, request):
        from . import narrate
        from .article import ArticleError

        body = request.data if isinstance(request.data, dict) else {}
        sample = None
        if body.get("voice_sample_id"):
            sample = VoiceSample.objects.filter(user=request.user, id=body["voice_sample_id"]).first()
            if sample is None:
                return Response({"detail": "No such voice sample."}, status=400)
        try:
            ep = narrate.start(
                request.user, url=str(body.get("url") or ""), text=str(body.get("text") or ""),
                title=str(body.get("title") or ""), voice_sample=sample,
            )
        except ArticleError as e:
            return Response({"detail": str(e)}, status=400)
        ep.refresh_from_db()
        return Response(EpisodeSerializer(ep, context={"request": request}).data,
                        status=status.HTTP_202_ACCEPTED)


class EpisodeMixView(APIView):
    """POST /v1/episodes/<id>/mix — join the chosen takes into one file again
    (after an edit, a retake or picking a different take)."""

    permission_classes = [IsFullMember]

    def post(self, request, id):
        from . import narrate

        ep = get_object_or_404(_episodes_for(request.user), id=id)
        if narrate.mix(ep) is None:
            return Response({"detail": "Nothing is voiced yet."}, status=409)
        ep.refresh_from_db()
        return Response(EpisodeSerializer(ep, context={"request": request}).data)


class EpisodeTranscriptView(APIView):
    """GET /v1/episodes/<id>/transcript — every word of the joined recording
    with its start and end time in that recording, plus where each piece
    starts. For captions, follow-along text, or cutting video to the voice."""

    permission_classes = [IsFullMember]

    def get(self, request, id):
        from . import narrate

        ep = get_object_or_404(_episodes_for(request.user), id=id)
        return Response(narrate.transcript(ep))


class EpisodeCancelView(APIView):
    """POST /v1/episodes/<id>/cancel — stop a narration after the piece it is
    on. What is already voiced is kept."""

    permission_classes = [IsFullMember]

    def post(self, request, id):
        from . import narrate

        ep = get_object_or_404(_episodes_for(request.user), id=id)
        if narrate.is_active(ep):
            narrate._save(ep, cancel=True)
        return Response(EpisodeSerializer(ep, context={"request": request}).data)


class SegmentProduceView(APIView):
    """POST /v1/segments/<id>/produce — voice one piece again with the full
    loop (take, clean, trim, check, retake while the check is poor), keeping
    the best take."""

    permission_classes = [IsFullMember]

    def post(self, request, id):
        from . import narration
        from .tasks import produce_segment as produce_task

        seg = get_object_or_404(Segment.objects.select_related("episode"), id=id, episode__user=request.user)
        seg.status = Segment.STATUS_QUEUED
        seg.save(update_fields=["status", "modified_on"])
        if _async_ok():
            produce_task.delay(seg.id)
        else:
            narration.produce_segment(seg)
        seg.refresh_from_db()
        return Response(SegmentSerializer(seg, context={"request": request}).data,
                        status=status.HTTP_202_ACCEPTED)


class SegmentFeedbackView(APIView):
    """POST /v1/segments/<id>/feedback — say what is wrong with a piece in
    your own words (``note``; a transcribed voice note works) and have it
    fixed: the line is reworded or a pronunciation is added as the note asks,
    and the piece is voiced again."""

    permission_classes = [IsFullMember]

    def post(self, request, id):
        from . import narrate, narration
        from .tasks import produce_segment as produce_task

        seg = get_object_or_404(Segment.objects.select_related("episode"), id=id, episode__user=request.user)
        note = str((request.data or {}).get("note") or "").strip()
        if not note:
            return Response({"detail": "Say what should change."}, status=400)
        plan = narrate.apply_feedback(seg, note)
        seg.status = Segment.STATUS_QUEUED
        seg.save(update_fields=["status", "modified_on"])
        if _async_ok():
            produce_task.delay(seg.id)
        else:
            narration.produce_segment(seg)
        seg.refresh_from_db()
        return Response({"understood": plan, "segment": SegmentSerializer(seg, context={"request": request}).data},
                        status=status.HTTP_202_ACCEPTED)
