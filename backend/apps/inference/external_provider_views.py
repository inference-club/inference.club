"""Browse + pin external-provider models (PRD 19 §5).

``GET  /api/inference/providers/<slug>/models`` — the provider's catalog
(fetched with the user's key, cached) annotated with which the user has pinned.
``GET/POST/DELETE /api/inference/providers/<slug>/pins`` — list / pin / unpin.
"""
import requests
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .external_keys import get_service, is_llm_provider
from .external_providers import fetch_provider_catalog, normalize_catalog_entry
from .models import PinnedModel


def _pin_dict(p: PinnedModel) -> dict:
    return {
        "id": p.public_id,
        "provider": p.provider,
        "model_id": p.model_id,
        "display_name": p.display_name,
        "context_length": p.context_length,
        "input_modalities": p.input_modalities,
    }


class ProviderModelsView(APIView):
    """The provider's model catalog + the caller's pinned flags."""

    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        if not is_llm_provider(slug):
            return Response({"detail": "Unknown provider."}, status=status.HTTP_404_NOT_FOUND)
        try:
            raw = fetch_provider_catalog(
                request.user, slug, force=request.query_params.get("refresh") == "1"
            )
        except PermissionError as e:
            return Response(
                {"detail": str(e), "type": "missing_api_key"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError:
            return Response({"detail": "Unknown provider."}, status=status.HTTP_404_NOT_FOUND)
        except requests.RequestException as e:
            return Response(
                {"detail": f"Could not reach {slug}: {e}", "type": "upstream_error"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        pinned = set(
            PinnedModel.objects.filter(user=request.user, provider=slug).values_list(
                "model_id", flat=True
            )
        )
        q = (request.query_params.get("q") or "").strip().lower()
        out = []
        for r in raw:
            if not isinstance(r, dict):
                continue
            e = normalize_catalog_entry(r)
            mid = e["model_id"]
            if not mid:
                continue
            if q and q not in mid.lower() and q not in (e["display_name"] or "").lower():
                continue
            e["pinned"] = mid in pinned
            out.append(e)
        out.sort(key=lambda e: e["model_id"].lower())
        svc = get_service(slug)
        return Response({"provider": slug, "label": svc.name if svc else slug, "data": out})


class ProviderPinsView(APIView):
    """List / pin / unpin the caller's models for one provider. Body: ``model_id``
    (plus optional display_name/context_length/input_modalities snapshotted from
    the catalog row)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        pins = PinnedModel.objects.filter(user=request.user, provider=slug)
        return Response({"data": [_pin_dict(p) for p in pins]})

    def post(self, request, slug):
        if not is_llm_provider(slug):
            return Response({"detail": "Unknown provider."}, status=status.HTTP_404_NOT_FOUND)
        model_id = (request.data.get("model_id") or "").strip()
        if not model_id:
            return Response({"detail": "model_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        ctx = request.data.get("context_length")
        in_mods = request.data.get("input_modalities")
        display = (request.data.get("display_name") or "").strip()
        pin, _created = PinnedModel.objects.get_or_create(
            user=request.user,
            provider=slug,
            model_id=model_id,
            defaults={
                "display_name": display or model_id,
                "context_length": ctx if isinstance(ctx, int) else None,
                "input_modalities": in_mods if isinstance(in_mods, list) else ["text"],
            },
        )
        return Response(_pin_dict(pin), status=status.HTTP_201_CREATED)

    def delete(self, request, slug):
        model_id = (
            request.data.get("model_id")
            or request.query_params.get("model_id")
            or ""
        ).strip()
        if not model_id:
            return Response({"detail": "model_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        PinnedModel.objects.filter(
            user=request.user, provider=slug, model_id=model_id
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
