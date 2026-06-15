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
        return Response({"data": EpisodeListSerializer(qs, many=True).data})

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
        if "title" in request.data:
            title = (request.data.get("title") or "").strip()
            if not title:
                return Response({"detail": "`title` can't be blank."}, status=400)
            ep.title = title[:200]
        if "description" in request.data:
            ep.description = (request.data.get("description") or "").strip()
        ep.save(update_fields=["title", "description", "modified_on"])
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
