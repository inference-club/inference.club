"""The ``/v1/files`` Media Library API (PRD 17 §5).

One upload entry point for all user media: ``POST /v1/files`` stores the upload
as an owner-only ``MediaAsset`` and returns a stable, opaque reference; ``GET
/v1/files`` lists the caller's own media (the Library's backing); and the
per-file routes manage visibility / metadata / deletion. Byte serving is the
audience-gated ``FileContentView`` (a thin alias over the shared asset serve).
"""
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import VISIBILITY_VALUES, MediaAsset
from .serializers import MediaAssetDetailSerializer
from .uploads import UploadError, store_upload


def _asset_qs():
    return MediaAsset.objects.select_related("inference_request").prefetch_related(
        "derived_from", "derivatives"
    )


def _resolve(ref):
    """An asset by opaque public_id or legacy int PK (or None)."""
    qs = _asset_qs()
    if isinstance(ref, str) and ref.isdigit():
        return qs.filter(pk=int(ref)).first()
    return qs.filter(public_id=ref).first()


class FilesView(APIView):
    """``POST /v1/files`` (multipart upload) and ``GET /v1/files`` (list mine)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"error": {"message": "`file` is required.", "type": "missing_file"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            asset = store_upload(request.user, upload, kind=request.data.get("kind") or None)
        except UploadError as e:
            return Response(
                {"error": {"message": e.message, "type": e.error_type}},
                status=e.http_status,
            )
        data = MediaAssetDetailSerializer(
            _asset_qs().get(pk=asset.pk), context={"request": request}
        ).data
        return Response(data, status=status.HTTP_201_CREATED)

    def get(self, request):
        qs = _asset_qs().filter(user=request.user)
        kind = request.query_params.get("kind")
        if kind:
            qs = qs.filter(kind=kind)
        bound = request.query_params.get("bound")
        if bound == "true":
            qs = qs.exclude(inference_request__isnull=True)
        elif bound == "false":
            qs = qs.filter(inference_request__isnull=True)
        q = request.query_params.get("q")
        if q:
            qs = qs.filter(file__icontains=q)

        try:
            limit = min(max(int(request.query_params.get("limit", 60)), 1), 200)
        except (TypeError, ValueError):
            limit = 60
        try:
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except (TypeError, ValueError):
            offset = 0

        total = qs.count()
        rows = list(qs[offset : offset + limit])
        data = MediaAssetDetailSerializer(
            rows, many=True, context={"request": request}
        ).data
        return Response(
            {
                "object": "list",
                "total": total,
                "limit": limit,
                "offset": offset,
                "data": data,
            }
        )


class FileDetailView(APIView):
    """``GET/PATCH/DELETE /v1/files/<ref>`` — GET is audience-gated (so a shared
    or published asset's metadata is readable, even anonymously), while
    PATCH/DELETE are owner-only (a non-owner — including anonymous — fails the
    ownership check below)."""

    permission_classes = [AllowAny]

    def get(self, request, ref):
        asset = _resolve(ref)
        if asset is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not asset.is_visible_to(request.user):
            return Response({"detail": "Not your asset."}, status=status.HTTP_403_FORBIDDEN)
        return Response(
            MediaAssetDetailSerializer(asset, context={"request": request}).data
        )

    def patch(self, request, ref):
        asset = _resolve(ref)
        if asset is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if asset.user_id != request.user.id:
            return Response({"detail": "Not your asset."}, status=status.HTTP_403_FORBIDDEN)

        if "visibility" in request.data:
            v = request.data["visibility"]
            if v not in VISIBILITY_VALUES:
                return Response(
                    {"detail": f"Invalid visibility: {v!r}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Anonymous accounts can never make content PUBLIC (mirrors the
            # InferenceRequest sharing rule — PRD 08).
            if v == "PUBLIC" and getattr(request.user, "is_anonymous_account", False):
                v = "UNLISTED"
            asset.visibility = v
        if isinstance(request.data.get("metadata"), dict):
            asset.metadata = request.data["metadata"]
        asset.save()
        return Response(
            MediaAssetDetailSerializer(asset, context={"request": request}).data
        )

    def delete(self, request, ref):
        asset = _resolve(ref)
        if asset is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if asset.user_id != request.user.id:
            return Response({"detail": "Not your asset."}, status=status.HTTP_403_FORBIDDEN)
        try:
            asset.file.delete(save=False)  # remove the stored object too
        except Exception:
            pass
        asset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FileContentView(APIView):
    """``GET /v1/files/<ref>/content`` — the bytes, audience-gated. OpenAI-shaped
    alias for ``/api/inference/assets/<ref>/``."""

    permission_classes = [AllowAny]

    def get(self, request, ref):
        from .views import _lookup_media_asset, serve_media_asset

        return serve_media_asset(request, _lookup_media_asset(ref))
