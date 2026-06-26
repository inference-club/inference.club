"""Central upload validation + storage for user-uploaded media (PRD 17 §5).

One place that decides what a `MediaAsset` kind a file is, whether it's within
the per-kind size/type guardrails, and how to persist it — replacing the
size/type checks that were copy-pasted across the STT / image-edit / mesh /
enhance views. The guardrail *numbers* still live in settings; this module just
maps a kind to the right one and enforces it.
"""
from __future__ import annotations

from rest_framework import status

from django.conf import settings
from django.core.files.base import ContentFile

from .models import MediaAsset


class UploadError(Exception):
    """A user-facing upload rejection carrying the HTTP status + error type to
    surface in an OpenAI-style ``{"error": {...}}`` body."""

    def __init__(self, message: str, *, http_status: int, error_type: str):
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.error_type = error_type


# Map a MediaAsset input kind to its (max-bytes, allowed-content-types) guardrail.
# ``None`` for the type set means "any type within the size cap".
def _limits_for(kind: str) -> tuple[int, set[str] | None]:
    if kind == MediaAsset.INPUT_IMAGE:
        return settings.IMAGE_MAX_UPLOAD_BYTES, settings.IMAGE_ALLOWED_CONTENT_TYPES
    if kind == MediaAsset.INPUT_AUDIO:
        return settings.STT_MAX_UPLOAD_BYTES, settings.STT_ALLOWED_CONTENT_TYPES
    # INPUT_VIDEO, INPUT_DOC, and anything else: the generic cap, any type.
    return settings.MEDIA_MAX_UPLOAD_BYTES, None


def _norm_ct(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def detect_kind(content_type: str | None, filename: str | None) -> str:
    """Best-effort MediaAsset input kind from the MIME type, falling back to the
    filename extension when the type is missing/ambiguous (octet-stream)."""
    ct = _norm_ct(content_type)
    if ct.startswith("image/"):
        return MediaAsset.INPUT_IMAGE
    if ct.startswith("audio/"):
        return MediaAsset.INPUT_AUDIO
    if ct.startswith("video/"):
        return MediaAsset.INPUT_VIDEO
    if ct in ("text/plain", "text/markdown", "application/pdf", "application/json"):
        return MediaAsset.INPUT_DOC
    # Ambiguous type — lean on the extension.
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if filename and "." in filename else ""
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
        return MediaAsset.INPUT_IMAGE
    if ext in (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"):
        return MediaAsset.INPUT_AUDIO
    if ext in (".mp4", ".webm", ".mov", ".mkv"):
        return MediaAsset.INPUT_VIDEO
    return MediaAsset.INPUT_DOC


def validate_upload(upload, kind: str | None = None) -> tuple[str, str, int]:
    """Resolve + validate one uploaded file. Returns ``(kind, content_type,
    size_bytes)`` or raises ``UploadError`` (413 too large / 415 wrong type).

    ``kind`` may be forced by the caller; otherwise it's detected. A forced kind
    that isn't an accepted input kind is rejected."""
    ct = _norm_ct(getattr(upload, "content_type", ""))
    name = getattr(upload, "name", "") or ""
    resolved = kind or detect_kind(ct, name)
    if resolved not in (
        MediaAsset.INPUT_IMAGE, MediaAsset.INPUT_AUDIO,
        MediaAsset.INPUT_VIDEO, MediaAsset.INPUT_DOC,
    ):
        raise UploadError(
            f"Unsupported upload kind: {resolved!r}.",
            http_status=status.HTTP_400_BAD_REQUEST,
            error_type="invalid_kind",
        )

    size = int(getattr(upload, "size", 0) or 0)
    max_bytes, allowed = _limits_for(resolved)
    if size and size > max_bytes:
        raise UploadError(
            f"File too large: {size} bytes (max {max_bytes}).",
            http_status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            error_type="file_too_large",
        )
    if allowed is not None and ct and ct not in allowed:
        raise UploadError(
            f"Unsupported content type: {ct!r}.",
            http_status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            error_type="unsupported_media_type",
        )
    return resolved, ct, size


def store_upload(user, upload, *, kind: str | None = None,
                 inference_request=None, visibility=None) -> MediaAsset:
    """Validate + persist an uploaded file as a MediaAsset owned by ``user``.

    Standalone uploads default to owner-only (the model default); pass
    ``visibility`` only to override. Raises ``UploadError`` on a bad file.
    """
    resolved, ct, size = validate_upload(upload, kind)
    asset = MediaAsset(
        user=user,
        inference_request=inference_request,
        kind=resolved,
        content_type=ct,
        size_bytes=size or None,
    )
    if visibility is not None:
        asset.visibility = visibility
    asset.file.save(name=upload.name or "upload", content=upload, save=False)
    asset.save()
    return asset
