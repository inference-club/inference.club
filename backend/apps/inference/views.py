import logging
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Prefetch, Q, Sum
from django.db.models.functions import TruncDate
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from .manifest_validator import SERVICE_TYPES
from .manifest_validator import validate as validate_manifest
from .models import (
    Bookmark,
    CatalogModel,
    Collection,
    CollectionItem,
    ContentReport,
    InferenceRequest,
    MediaAsset,
    Provider,
    ProviderModel,
    ProviderService,
    ServiceManifest,
    Star,
    VISIBILITY_PUBLIC,
    link_catalog_model,
    slugify_model_id,
    visible_list_q,
)
from .pagination import StandardResultsSetPagination
from .serializers import (
    AgentRegisterSerializer,
    CollectionSerializer,
    CollectionWriteSerializer,
    ContentReportCreateSerializer,
    InferenceRequestDetailSerializer,
    InferenceRequestListSerializer,
    InferenceRequestSerializer,
    InferenceRequestVisibilitySerializer,
    ProviderSerializer,
    ProviderServiceSerializer,
    ProviderUpdateSerializer,
    PublicProviderSerializer,
    ServiceManifestSerializer,
    _user_github_login,
    _user_owner,
)
from .tailscale import mint_authkey_for_provider

logger = logging.getLogger("django")


# Owner-attribution querysets need the user + their GitHub social_auth row.
def _requests_with_owner():
    return InferenceRequest.objects.select_related(
        "provider", "user"
    ).prefetch_related("user__social_auth", "assets")


def _annotate_viewer_flags(qs, user):
    """Annotate ``user_has_starred`` / ``user_has_bookmarked`` so the card and
    detail serializers can show per-viewer star/bookmark state without an N+1.
    No-op for anonymous callers (the flags default to False in the serializer)."""
    if user is not None and getattr(user, "is_authenticated", False):
        qs = qs.annotate(
            user_has_starred=Exists(
                Star.objects.filter(request=OuterRef("pk"), user=user)
            ),
            user_has_bookmarked=Exists(
                Bookmark.objects.filter(request=OuterRef("pk"), user=user)
            ),
        )
    return qs


# Valid inference_type values, used to validate the ?type= query param.
_INFERENCE_TYPES = {t[0] for t in InferenceRequest.INFERENCE_TYPES}


def _apply_request_filters(qs, params):
    """Shared list-filtering for the request endpoints.

    ``?type=IMAGE`` narrows to a single modality (powers the image gallery and
    the profile "recent images" strip). ``?model=<name>`` narrows to one exact
    model (powers each playground's "recent for this model" strip). ``?search=``
    matches the stored prompt (image/TTS payloads carry it directly) and the
    model name, case-insensitive. ``?sort=popular`` orders by star count
    (most-starred first). All optional and composable.
    """
    itype = (params.get("type") or "").upper().strip()
    if itype in _INFERENCE_TYPES:
        qs = qs.filter(inference_type=itype)

    model = (params.get("model") or "").strip()
    if model:
        qs = qs.filter(model_name=model)

    search = (params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(payload__prompt__icontains=search)
            | Q(model_name__icontains=search)
        )

    if (params.get("sort") or "").lower() in ("popular", "stars"):
        qs = qs.order_by("-star_count", "-created_on")
    return qs


class InferenceRequestView(generics.ListCreateAPIView):
    """GET lists the requesting user's own requests (powers "Your Inference
    Requests"); POST creates a request."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        # Slim cards on list; the write serializer accepts payload on create.
        if self.request.method == "POST":
            return InferenceRequestSerializer
        return InferenceRequestListSerializer

    def get_queryset(self):
        qs = _requests_with_owner().filter(user=self.request.user)
        qs = _annotate_viewer_flags(qs, self.request.user)
        return _apply_request_filters(qs, self.request.query_params)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AllInferenceRequestView(generics.ListAPIView):
    """Every *listable* inference request on the network (powers "All Inference
    Requests"). Visible to any authenticated user, with owner attribution.
    Honors per-request visibility: a member sees PUBLIC + PRIVATE (members-only)
    requests plus their own; UNLISTED and SECRET are excluded from the feed."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    serializer_class = InferenceRequestListSerializer

    def get_queryset(self):
        qs = _requests_with_owner().filter(visible_list_q(self.request.user))
        qs = _annotate_viewer_flags(qs, self.request.user)
        return _apply_request_filters(qs, self.request.query_params)


class RetrieveInferenceRequestView(generics.RetrieveUpdateDestroyAPIView):
    """GET returns a request fully-expanded (subject to its visibility); PATCH
    changes its visibility (owner only); DELETE removes it (owner only)."""

    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return InferenceRequestVisibilitySerializer
        return InferenceRequestDetailSerializer

    def get_queryset(self):
        return _annotate_viewer_flags(_requests_with_owner(), self.request.user)

    def get_object(self):
        obj = super().get_object()
        # Writes are owner-only; reads enforce the request's visibility.
        if self.request.method in ("PATCH", "PUT", "DELETE"):
            if obj.user_id != self.request.user.id:
                raise PermissionDenied("You can only modify your own inference requests.")
        elif not obj.is_visible_to(self.request.user):
            raise Http404("no such inference request")
        return obj

    def perform_destroy(self, instance):
        if instance.user_id != self.request.user.id:
            raise PermissionDenied("You can only delete your own inference requests.")
        instance.delete()


class SharedRequestView(generics.RetrieveAPIView):
    """GET /api/inference/shared/<share_token>/ — resolve a request by its
    unguessable share token, for link-based sharing. Unauthenticated-friendly:
    PUBLIC/UNLISTED render to anyone, PRIVATE to any signed-in member, SECRET
    only to the owner. Anything not visible 404s (never 403) so the token's
    existence isn't confirmed."""

    permission_classes = [AllowAny]
    serializer_class = InferenceRequestDetailSerializer
    lookup_field = "share_token"

    def get_queryset(self):
        user = self.request.user if self.request.user.is_authenticated else None
        return _annotate_viewer_flags(_requests_with_owner(), user)

    def get_object(self):
        obj = super().get_object()
        if not obj.is_visible_to(self.request.user):
            raise Http404("no such inference request")
        return obj


def _get_owned_or_visible_request(request, request_id):
    """Fetch a request the caller may act on (star/bookmark): must be visible
    to them. 404 otherwise."""
    obj = get_object_or_404(InferenceRequest, id=request_id)
    if not obj.is_visible_to(request.user):
        raise Http404("no such inference request")
    return obj


class RequestStarView(APIView):
    """POST/DELETE /api/inference/requests/<id>/star/ — toggle the caller's star
    on a request. Returns the fresh star_count + is_starred."""

    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        obj = _get_owned_or_visible_request(request, id)
        Star.objects.get_or_create(user=request.user, request=obj)
        return Response({"is_starred": True, "star_count": obj.recount_stars()})

    def delete(self, request, id):
        obj = _get_owned_or_visible_request(request, id)
        Star.objects.filter(user=request.user, request=obj).delete()
        return Response({"is_starred": False, "star_count": obj.recount_stars()})


class RequestBookmarkView(APIView):
    """POST/DELETE /api/inference/requests/<id>/bookmark/ — toggle the caller's
    bookmark (the "show on my profile" curation choice)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        obj = _get_owned_or_visible_request(request, id)
        Bookmark.objects.get_or_create(user=request.user, request=obj)
        return Response({"is_bookmarked": True})

    def delete(self, request, id):
        obj = _get_owned_or_visible_request(request, id)
        Bookmark.objects.filter(user=request.user, request=obj).delete()
        return Response({"is_bookmarked": False})


class RequestReportView(APIView):
    """POST /api/inference/requests/<id>/report/ — flag a request for
    inappropriate content. Any signed-in member may report any request they can
    see; staff triage the queue from the admin surface.

    Idempotent per (reporter, request): re-reporting the same request just
    returns the existing report instead of creating a duplicate (the unique
    constraint guarantees one report per member per request)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        obj = _get_owned_or_visible_request(request, id)
        ser = ContentReportCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        report, created = ContentReport.objects.get_or_create(
            reporter=request.user,
            request=obj,
            defaults=ser.validated_data,
        )
        return Response(
            {"reported": True, "already_reported": not created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class StarredRequestsView(generics.ListAPIView):
    """GET /api/inference/requests/starred/ — the caller's starred requests
    (most-recently-starred first), filtered to what's still visible to them."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    serializer_class = InferenceRequestListSerializer

    def get_queryset(self):
        user = self.request.user
        starred_ids = Star.objects.filter(user=user).values_list("request_id", flat=True)
        qs = (
            _requests_with_owner()
            .filter(id__in=list(starred_ids))
            .filter(Q(user=user) | Q(visibility__in=[VISIBILITY_PUBLIC, "UNLISTED", "PRIVATE"]))
        )
        qs = _annotate_viewer_flags(qs, user)
        return _apply_request_filters(qs, self.request.query_params)


class BookmarkedRequestsView(generics.ListAPIView):
    """GET /api/inference/requests/bookmarked/ — the caller's bookmarked
    requests, for managing what shows on their profile."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    serializer_class = InferenceRequestListSerializer

    def get_queryset(self):
        user = self.request.user
        bookmarked_ids = Bookmark.objects.filter(user=user).values_list(
            "request_id", flat=True
        )
        qs = (
            _requests_with_owner()
            .filter(id__in=list(bookmarked_ids))
            .filter(Q(user=user) | Q(visibility__in=[VISIBILITY_PUBLIC, "UNLISTED", "PRIVATE"]))
        )
        qs = _annotate_viewer_flags(qs, user)
        return _apply_request_filters(qs, self.request.query_params)


class AgentRegisterView(APIView):
    """Agent calls this on first run; returns a Tailscale auth key the agent
    uses to join the inference.club tailnet.

    Idempotent on (user, name): re-registering an existing provider rebumps
    last_seen_at and re-mints an auth key. Safe to call repeatedly.
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        ser = AgentRegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        provider, _ = Provider.objects.update_or_create(
            user=request.user,
            name=data.get("name") or "club-host",
            defaults={
                "tailnet_hostname": data.get("tailnet_hostname", ""),
                "agent_port": data.get("agent_port", 443),
                "is_active": True,
                "registered_at": timezone.now(),
                "last_seen_at": timezone.now(),
            },
        )

        if settings.INFERENCE_DIRECT_AGENTS:
            # Local-dev, no-Tailscale: the agent runs with AGENT_DIRECT and
            # serves plain HTTP on a directly-reachable host:port (e.g.
            # host.docker.internal:8090). Trust the address it reported (stored
            # above) — no hostname rewrite, no auth key. The backend reaches it
            # directly because TAILNET_PROXY_URL is unset in dev.
            authkey = ""
            login_server = ""
        else:
            # Force a deterministic per-provider hostname so two agents from the
            # same user can't collide in the tailnet.
            canonical = f"club-host-{provider.id}"
            if provider.tailnet_hostname != canonical:
                provider.tailnet_hostname = canonical
                provider.save(update_fields=["tailnet_hostname", "modified_on"])
            minted = mint_authkey_for_provider(provider)
            authkey = minted.authkey
            login_server = minted.login_server

        return Response(
            {
                "provider_id": provider.id,
                "tailscale_authkey": authkey,
                "tailscale_login_server": login_server,
                "tailnet_hostname": provider.tailnet_hostname,
            },
            status=status.HTTP_200_OK,
        )


class ProviderListView(generics.ListAPIView):
    """List the authenticated user's providers (powers /providers/my-nodes UI)."""

    permission_classes = [IsAuthenticated]
    serializer_class = ProviderSerializer

    def get_queryset(self):
        return (
            Provider.objects.filter(user=self.request.user)
            .prefetch_related("models")
        )


class AllProvidersListView(generics.ListAPIView):
    """List every active provider on the network (powers /providers/all-nodes UI).

    Exposes per-node detail to any logged-in user, including the owner
    (email local-part), so the network is legible. Inactive providers
    are hidden.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PublicProviderSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return (
            Provider.objects.filter(is_active=True)
            .select_related("user")
            .prefetch_related("models", "user__social_auth")
            .order_by("-created_on")
        )


class ProviderServiceListView(generics.ListAPIView):
    """List the requesting user's services so they can manage access policies
    (powers the Settings → Access page)."""

    permission_classes = [IsAuthenticated]
    serializer_class = ProviderServiceSerializer

    def get_queryset(self):
        return (
            ProviderService.objects.filter(provider__user=self.request.user)
            .select_related("provider")
            .prefetch_related("models")
            .order_by("provider__name", "name")
        )


class ProviderServiceUpdateView(generics.RetrieveUpdateAPIView):
    """GET / PATCH one of the requesting user's services to set its access
    policy. Scoped to the owner — others' services 404 here."""

    permission_classes = [IsAuthenticated]
    serializer_class = ProviderServiceSerializer
    lookup_field = "id"

    def get_queryset(self):
        return (
            ProviderService.objects.filter(provider__user=self.request.user)
            .select_related("provider")
            .prefetch_related("models")
        )


class ProviderUpdateView(generics.RetrieveUpdateAPIView):
    """PATCH a provider's owner-editable settings (the accepting_requests
    pause/kill switch). Scoped to the owner."""

    permission_classes = [IsAuthenticated]
    serializer_class = ProviderUpdateSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Provider.objects.filter(user=self.request.user)


class LeaderboardView(APIView):
    """Top token consumers over a time window. Visible to any authenticated
    member — it's a deliberately public, social view of network usage."""

    permission_classes = [IsAuthenticated]

    RANGES = {
        "hour": timedelta(hours=1),
        "day": timedelta(days=1),
        "week": timedelta(days=7),
        "month": timedelta(days=30),
        "year": timedelta(days=365),
        "all": None,
    }

    def get(self, request):
        rng = request.query_params.get("range", "day")
        if rng not in self.RANGES:
            rng = "day"
        delta = self.RANGES[rng]

        qs = InferenceRequest.objects.all()
        if delta is not None:
            qs = qs.filter(created_on__gte=timezone.now() - delta)

        rows = (
            qs.values("user")
            .annotate(
                total_tokens=Sum("total_tokens"),
                prompt_tokens=Sum("prompt_tokens"),
                completion_tokens=Sum("completion_tokens"),
                requests=Count("id"),
            )
            .filter(total_tokens__gt=0)
            .order_by("-total_tokens")[:50]
        )

        User = get_user_model()
        users = {
            u.id: u
            for u in User.objects.filter(
                id__in=[r["user"] for r in rows]
            ).prefetch_related("social_auth")
        }

        results = []
        for i, r in enumerate(rows, start=1):
            u = users.get(r["user"])
            results.append(
                {
                    "rank": i,
                    "owner": _user_owner(u) if u else "unknown",
                    "github_login": _user_github_login(u) if u else None,
                    "total_tokens": r["total_tokens"] or 0,
                    "prompt_tokens": r["prompt_tokens"] or 0,
                    "completion_tokens": r["completion_tokens"] or 0,
                    "requests": r["requests"],
                }
            )
        return Response({"range": rng, "results": results})


# The throttle scopes used by the OpenAI-compatible proxy (see
# openai_views ModelsView / _ChatOrCompletionsProxy). Surfaced read-only so
# users can see their current rate-limit headroom.
INFERENCE_THROTTLE_SCOPES = ["inference", "models"]


def _parse_throttle_rate(rate):
    """('60/min') -> (60, 60). Mirrors DRF's SimpleRateThrottle.parse_rate."""
    if not rate:
        return None, None
    num, _, period = rate.partition("/")
    try:
        num_requests = int(num)
    except ValueError:
        return None, None
    duration = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(period[:1])
    if duration is None:
        return None, None
    return num_requests, duration


def scope_usage(scope, ident):
    """Current usage for a throttle scope + identity, read straight from the
    throttle cache (no quota consumed). Returns None if the scope has no rate.

    Mirrors DRF's SimpleRateThrottle cache key/format so it reflects exactly
    what the throttle enforces.
    """
    rate = api_settings.DEFAULT_THROTTLE_RATES.get(scope)
    num_requests, duration = _parse_throttle_rate(rate)
    if num_requests is None:
        return None
    key = "throttle_%s_%s" % (scope, ident)
    history = cache.get(key, []) or []
    now = time.time()
    recent = [t for t in history if t > now - duration]
    used = len(recent)
    # DRF stores newest-first, so min(recent) is the oldest in-window request;
    # a slot frees when it ages past `duration`.
    reset_in = int(max(0, duration - (now - min(recent)))) if recent else 0
    return {
        "scope": scope,
        "limit": num_requests,
        "used": used,
        "remaining": max(0, num_requests - used),
        "duration_seconds": duration,
        "reset_in_seconds": reset_in,
    }


class RateLimitUsageView(APIView):
    """The requesting user's current rate-limit consumption per scope.

    Read-only view of the throttle cache so the dashboard can show a live
    usage meter without itself counting against any limit.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        ident = request.user.pk
        scopes = [
            u
            for u in (scope_usage(s, ident) for s in INFERENCE_THROTTLE_SCOPES)
            if u is not None
        ]
        return Response({"scopes": scopes})


# --- OpenRouter-style model catalog --------------------------------------
# See docs/plans/openrouter-provider-compatibility.md. Per-model capabilities
# come from the linked CatalogModel (declared by the operator in the agent
# manifest); per-deployment overrides on ProviderModel.metadata win when set.

_DEFAULT_SAMPLING_PARAMS = [
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "frequency_penalty",
    "presence_penalty",
    "repetition_penalty",
    "stop",
    "seed",
    "max_tokens",
]


def openrouter_model_schema(pm) -> dict:
    """Build the OpenRouter provider `data[]` entry for a ProviderModel.

    Capabilities are sourced from the linked CatalogModel (declared in the
    operator's manifest); per-deployment overrides on ``ProviderModel.metadata``
    take precedence. No id-based guessing.
    """
    meta = pm.metadata if isinstance(pm.metadata, dict) else {}
    cat = pm.catalog_model if pm.catalog_model_id else None
    model_id = pm.name
    created_dt = pm.created_on or pm.provider.created_on

    cat_input = (cat.input_modalities or ["text"]) if cat else ["text"]
    cat_output = (cat.output_modalities or ["text"]) if cat else ["text"]
    cat_features = (cat.supported_features or []) if cat else []
    # Live-probed served window first, then the declared catalog ceiling.
    context = (
        pm.served_context_len
        or (cat.native_context_length if cat else None)
        or pm.context_window
    )

    out = {
        "id": model_id,
        "name": meta.get("name") or (cat.display_name if cat else None) or model_id,
        "created": int(created_dt.timestamp()) if created_dt else 0,
        "input_modalities": meta.get("input_modalities") or cat_input,
        "output_modalities": meta.get("output_modalities") or cat_output,
        "context_length": (
            meta.get("context_length")
            if meta.get("context_length") is not None
            else context
        ),
        "max_output_length": meta.get("max_output_length"),
        # No economic model yet — pricing is present (OpenRouter requires it)
        # but zeroed. See §2 of the compatibility doc.
        "pricing": meta.get("pricing")
        or {"prompt": "0", "completion": "0", "request": "0", "image": "0"},
        "supported_sampling_parameters": meta.get("supported_sampling_parameters")
        or _DEFAULT_SAMPLING_PARAMS,
        "supported_features": meta.get("supported_features") or cat_features,
        "is_ready": meta.get("is_ready", True),
    }
    quant = meta.get("quantization")
    if quant:
        out["quantization"] = quant
    if meta.get("description"):
        out["description"] = meta["description"]
    hf_id = meta.get("hugging_face_id") or (cat.hf_repo_id if cat else None)
    if hf_id:
        out["hugging_face_id"] = hf_id
    return out


class ProviderModelsCatalogView(APIView):
    """OpenRouter-style provider models catalog for the whole network.

    Emits the `{data: [...]}` schema OpenRouter expects from a provider's list-
    models endpoint, deduped across the network's active models. See
    docs/plans/openrouter-provider-compatibility.md.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        seen: dict[str, dict] = {}
        qs = (
            ProviderModel.objects.filter(is_active=True, provider__is_active=True)
            .select_related("provider")
            .order_by("name", "-created_on")
        )
        for pm in qs:
            if pm.name in seen:
                continue
            seen[pm.name] = openrouter_model_schema(pm)
        return Response({"data": list(seen.values())})


def serialize_catalog_entry(catalog, deployments) -> dict:
    """Build the public catalog dict for one CatalogModel given an iterable of
    its active deployments. Shared by ModelCatalogView (network-wide) and the
    public profile (scoped to one user's deployments)."""
    providers = {}
    served = []
    for d in deployments:
        p = d.provider
        providers[p.id] = {"name": p.name, "online": p.is_online}
        if d.served_context_len:
            served.append(d.served_context_len)
    # The real, usable context (largest served across online nodes) takes
    # precedence over the declared ceiling.
    context_length = (max(served) if served else None) or catalog.native_context_length
    return {
        "slug": catalog.slug,
        "display_name": catalog.display_name or catalog.slug,
        "hf_repo_id": catalog.hf_repo_id,
        "hf_url": catalog.hf_url,
        "is_custom": catalog.is_custom,
        "context_length": context_length,
        "input_modalities": catalog.input_modalities or [],
        "output_modalities": catalog.output_modalities or [],
        "supported_features": catalog.supported_features or [],
        "provider_count": len(providers),
        "online_provider_count": sum(1 for v in providers.values() if v["online"]),
        "providers": sorted(providers.values(), key=lambda v: v["name"]),
    }


class ModelCatalogView(APIView):
    """GET /api/inference/models/ — the human-facing network model catalog.

    One entry per CatalogModel that has at least one active deployment, with
    operator-declared capabilities (modalities, context, features) and which
    nodes serve it.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        active_deploys = ProviderModel.objects.filter(
            is_active=True, provider__is_active=True
        ).select_related("provider")
        catalogs = list(
            CatalogModel.objects.filter(
                deployments__is_active=True, deployments__provider__is_active=True
            )
            .distinct()
            .prefetch_related(
                Prefetch("deployments", queryset=active_deploys, to_attr="active_deployments")
            )
            .order_by("slug")
        )

        data = [
            serialize_catalog_entry(c, getattr(c, "active_deployments", []))
            for c in catalogs
        ]
        return Response({"models": data})


class NetworkStatusView(APIView):
    """GET /api/inference/network/ — PUBLIC, unauthenticated snapshot of the
    live network for the status page.

    Aggregates only: no request content and no user data beyond public GitHub
    handles (the same handles already exposed on public profiles).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        now = timezone.now()
        cutoff_24h = now - timedelta(hours=24)

        providers = list(
            Provider.objects.filter(is_active=True)
            .exclude(tailnet_hostname="")
            .select_related("user")
        )
        online = [p for p in providers if p.is_online]
        online_ids = {p.id for p in online}

        # Models available *right now* = active deployments on online nodes.
        deploys = ProviderModel.objects.filter(
            is_active=True, provider_id__in=online_ids
        ).select_related("catalog_model")
        model_providers: dict[str, set[int]] = {}
        model_meta: dict[str, object] = {}
        node_models: dict[int, set[str]] = {}
        for d in deploys:
            slug = d.catalog_model.slug if d.catalog_model_id else slugify_model_id(d.name)
            model_providers.setdefault(slug, set()).add(d.provider_id)
            node_models.setdefault(d.provider_id, set()).add(slug)
            if d.catalog_model_id and slug not in model_meta:
                model_meta[slug] = d.catalog_model

        models = []
        for slug in sorted(model_providers):
            cat = model_meta.get(slug)
            models.append(
                {
                    "slug": slug,
                    "display_name": (getattr(cat, "display_name", "") or slug),
                    "input_modalities": (getattr(cat, "input_modalities", None) or ["text"]),
                    "supported_features": (getattr(cat, "supported_features", None) or []),
                    "online_provider_count": len(model_providers[slug]),
                }
            )

        all_ir = InferenceRequest.objects.all()
        recent = all_ir.filter(created_on__gte=cutoff_24h)
        tokens_total = all_ir.aggregate(t=Sum("total_tokens"))["t"] or 0
        tokens_24h = recent.aggregate(t=Sum("total_tokens"))["t"] or 0

        # Daily tokens for the last 30 days (contiguous, zero-filled).
        start = (now - timedelta(days=29)).date()
        rows = (
            all_ir.filter(created_on__date__gte=start)
            .annotate(day=TruncDate("created_on"))
            .values("day")
            .annotate(t=Sum("total_tokens"))
        )
        by_day = {r["day"]: (r["t"] or 0) for r in rows}
        daily = [
            {"date": (start + timedelta(days=i)).isoformat(), "tokens": by_day.get(start + timedelta(days=i), 0)}
            for i in range(30)
        ]

        from .serializers import _user_github_login

        nodes = [
            {
                "name": p.name,
                "github_login": _user_github_login(p.user),
                "model_count": len(node_models.get(p.id, set())),
            }
            for p in online
        ]

        return Response(
            {
                "generated_at": now.isoformat(),
                "providers": {"online": len(online), "total": len(providers)},
                "models_available": len(model_providers),
                "tokens": {"total": tokens_total, "last_24h": tokens_24h},
                "requests": {"total": all_ir.count(), "last_24h": recent.count()},
                "daily_tokens": daily,
                "models": models,
                "nodes": nodes,
            }
        )


def _tailnet_proxies():
    """Per-call proxy dict for outbound tailnet requests.

    Returning None when no proxy is configured keeps local dev simple: the
    backend just talks to the agent directly (e.g. on localhost). In prod the
    Tailscale sidecar provides a SOCKS5 endpoint that resolves *.ts.net names.
    """
    from django.conf import settings as _settings

    url = getattr(_settings, "TAILNET_PROXY_URL", "") or ""
    if not url:
        return None
    return {"http": url, "https": url}


class RefreshError(Exception):
    """Internal — surfaces upstream failure detail to the caller of refresh_provider_models."""


def _manifest_model_names(parsed) -> set[str]:
    """Pull the set of model ids declared in a parsed manifest.

    Walks ``parsed.hosts[].services[].models[].id`` defensively — anything
    not shaped like the validator expects is just skipped, since the
    validator already ran.
    """
    names: set[str] = set()
    if not isinstance(parsed, dict):
        return names
    for host in parsed.get("hosts") or []:
        if not isinstance(host, dict):
            continue
        for svc in host.get("services") or []:
            if not isinstance(svc, dict):
                continue
            for m in svc.get("models") or []:
                if isinstance(m, dict):
                    served = _model_served_id(m)
                    if served:
                        names.add(served)
    return names


def _model_served_id(m: dict) -> str:
    """The served id for a manifest model entry: the explicit ``id`` if given,
    else the ``hf`` repo id (vLLM serves under the HF id by default). Empty if
    neither is usable."""
    mid = m.get("id")
    mid = mid.strip() if isinstance(mid, str) else ""
    if mid:
        return mid
    hf = m.get("hf")
    return hf.strip() if isinstance(hf, str) else ""


def _model_hf_id(m: dict) -> str:
    hf = m.get("hf")
    return hf.strip() if isinstance(hf, str) else ""


def _str_list(value) -> list[str]:
    """Normalize a manifest list field to a clean list of non-empty strings."""
    return [v.strip() for v in (value or []) if isinstance(v, str) and v.strip()]


def _model_capabilities(m: dict) -> dict:
    """Operator-declared capabilities for one manifest model entry. All
    optional; the validator already enforced shape. Modalities default later
    from the service type when omitted (empty list here)."""
    name = m.get("name")
    ctx = m.get("context_length")
    quant = m.get("quantization")
    return {
        "name": name.strip() if isinstance(name, str) and name.strip() else "",
        "input_modalities": _str_list(m.get("input_modalities")),
        "output_modalities": _str_list(m.get("output_modalities")),
        "features": _str_list(m.get("features")),
        "context_length": ctx if isinstance(ctx, int) and ctx > 0 else None,
        "quantization": quant.strip() if isinstance(quant, str) and quant.strip() else "",
    }


def _manifest_services(parsed) -> list[dict]:
    """Walk ``parsed.hosts[].services[]`` into a flat list of
    ``{name, host_id, engine, model_ids}`` dicts. Defensive — the validator
    already ran, so anything malformed is just skipped."""
    out: list[dict] = []
    if not isinstance(parsed, dict):
        return out
    for host in parsed.get("hosts") or []:
        if not isinstance(host, dict):
            continue
        host_id = host.get("id") if isinstance(host.get("id"), str) else ""
        for svc in host.get("services") or []:
            if not isinstance(svc, dict):
                continue
            name = svc.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            models_list: list[dict] = []
            seen_served: set[str] = set()
            for m in svc.get("models") or []:
                if not isinstance(m, dict):
                    continue
                served = _model_served_id(m)
                if not served or served in seen_served:
                    continue
                seen_served.add(served)
                models_list.append(
                    {
                        "served": served,
                        "hf": _model_hf_id(m),
                        "capabilities": _model_capabilities(m),
                    }
                )
            svc_type = svc.get("type")
            # Defaults to "llm" for an omitted/unknown type. Uses the validator's
            # SERVICE_TYPES (the single source of truth) so a newly-added modality
            # can't be silently coerced back to llm by a stale literal list here.
            if not isinstance(svc_type, str) or svc_type not in SERVICE_TYPES:
                svc_type = "llm"
            features = [
                f.strip()
                for f in (svc.get("features") or [])
                if isinstance(f, str) and f.strip()
            ]
            out.append(
                {
                    "name": name.strip(),
                    "host_id": host_id or "",
                    "engine": svc.get("engine") if isinstance(svc.get("engine"), str) else "",
                    "service_type": svc_type,
                    "features": features,
                    "models": models_list,
                }
            )
    return out


def sync_provider_models_from_manifest(provider, parsed) -> int:
    """Mirror the manifest into ProviderService + ProviderModel rows.

    The manifest is the operator's declared source of truth for what the agent
    serves. We upsert one ProviderService per declared service (keyed by name)
    and link each ProviderModel to its service. Crucially, upserting a service
    **preserves its access_policy / allowed_github_users** so re-uploading a
    manifest never resets who the operator has granted access to.

    Returns the count of active models after the sync.
    """
    services_data = _manifest_services(parsed)
    declared_service_names = {s["name"] for s in services_data}
    existing_services = {s.name: s for s in provider.services.all()}

    service_by_name: dict[str, ProviderService] = {}
    for sd in services_data:
        svc = existing_services.get(sd["name"])
        if svc is None:
            svc = ProviderService.objects.create(
                provider=provider,
                name=sd["name"],
                host_id=sd["host_id"],
                engine=sd["engine"],
                service_type=sd["service_type"],
                declared_features=sd["features"],
                is_active=True,
            )
        else:
            fields = []
            if svc.host_id != sd["host_id"]:
                svc.host_id = sd["host_id"]
                fields.append("host_id")
            if svc.engine != sd["engine"]:
                svc.engine = sd["engine"]
                fields.append("engine")
            if svc.service_type != sd["service_type"]:
                svc.service_type = sd["service_type"]
                fields.append("service_type")
            if list(svc.declared_features or []) != sd["features"]:
                svc.declared_features = sd["features"]
                fields.append("declared_features")
            if not svc.is_active:
                svc.is_active = True
                fields.append("is_active")
            if fields:
                svc.save(update_fields=fields + ["modified_on"])
        service_by_name[sd["name"]] = svc

    # Deactivate services no longer in the manifest, but keep their policy in
    # case the operator brings the service back later.
    for name, svc in existing_services.items():
        if name not in declared_service_names and svc.is_active:
            svc.is_active = False
            svc.save(update_fields=["is_active", "modified_on"])

    declared_models: set[str] = set()
    model_to_service: dict[str, ProviderService] = {}
    model_hf: dict[str, str] = {}
    model_caps: dict[str, dict] = {}
    for sd in services_data:
        for m in sd["models"]:
            served = m["served"]
            declared_models.add(served)
            model_to_service.setdefault(served, service_by_name[sd["name"]])
            if m["hf"]:
                model_hf.setdefault(served, m["hf"])
            model_caps.setdefault(served, m.get("capabilities") or {})

    existing = {pm.name: pm for pm in provider.models.all()}
    for name, pm in existing.items():
        fields = []
        active = name in declared_models
        if pm.is_active != active:
            pm.is_active = active
            fields.append("is_active")
        svc = model_to_service.get(name)
        if svc is not None and pm.service_id != svc.id:
            pm.service = svc
            fields.append("service")
        hf = model_hf.get(name, "")
        if hf and pm.hf_repo_id != hf:
            pm.hf_repo_id = hf
            fields.append("hf_repo_id")
        # (Re)link the catalog model when the deployment is active and either
        # unlinked or its declared identity just changed.
        if active and (pm.catalog_model_id is None or "hf_repo_id" in fields):
            link_catalog_model(pm)
            fields.append("catalog_model")
        # Apply the operator's declared capabilities to the catalog on every
        # sync (manifest is the source of truth), and stash per-deployment
        # quantization on the ProviderModel.
        if active and pm.catalog_model_id and svc is not None:
            _apply_declared_capabilities(pm.catalog_model, svc, model_caps.get(name))
            if _apply_deployment_caps(pm, model_caps.get(name)) and "metadata" not in fields:
                fields.append("metadata")
        if fields:
            pm.save(update_fields=fields + ["modified_on"])
    for name in declared_models:
        if name not in existing:
            svc = model_to_service.get(name)
            pm = ProviderModel(
                provider=provider,
                name=name,
                hf_repo_id=model_hf.get(name, ""),
                is_active=True,
                service=svc,
            )
            catalog = link_catalog_model(pm)
            _apply_declared_capabilities(catalog, svc, model_caps.get(name))
            _apply_deployment_caps(pm, model_caps.get(name))
            pm.save()
    return len(declared_models)


# Default (input, output) modalities by service type, used when a model doesn't
# declare its own. LLM is text→text; the others mirror their endpoint shape.
_SERVICE_TYPE_MODALITIES = {
    "stt": (["audio"], ["text"]),
    "tts": (["text"], ["audio"]),
    "image": (["text", "image"], ["image"]),
    "mesh": (["image"], ["model"]),
    "music": (["text"], ["audio"]),
    "video": (["text", "image"], ["video"]),
    "llm": (["text"], ["text"]),
}


def _apply_declared_capabilities(catalog, service, caps) -> None:
    """Apply operator-declared model capabilities to its CatalogModel.

    Modalities use the declared lists when present, else default from the
    service type. Features, context-length ceiling, and display name are taken
    from the declaration when given. Manifest is the source of truth, so this
    runs on every sync (idempotent — only writes changed fields).
    """
    caps = caps or {}
    stype = getattr(service, "service_type", "llm") if service is not None else "llm"
    default_in, default_out = _SERVICE_TYPE_MODALITIES.get(stype, (["text"], ["text"]))

    inp = caps.get("input_modalities") or default_in
    out = caps.get("output_modalities") or default_out
    feats = caps.get("features") or []
    ctx = caps.get("context_length")
    name = caps.get("name")

    fields = []
    if catalog.input_modalities != inp:
        catalog.input_modalities = inp
        fields.append("input_modalities")
    if catalog.output_modalities != out:
        catalog.output_modalities = out
        fields.append("output_modalities")
    if catalog.supported_features != feats:
        catalog.supported_features = feats
        fields.append("supported_features")
    if ctx is not None and catalog.native_context_length != ctx:
        catalog.native_context_length = ctx
        fields.append("native_context_length")
    if name and catalog.display_name != name:
        catalog.display_name = name
        fields.append("display_name")
    if fields:
        catalog.save(update_fields=fields + ["modified_on"])


def _apply_deployment_caps(pm, caps) -> bool:
    """Stash per-deployment capability overrides (currently just quantization)
    on ``pm.metadata``. Mutates pm in place; returns True if metadata changed
    (so the caller can include it in update_fields)."""
    caps = caps or {}
    quant = caps.get("quantization") or ""
    meta = dict(pm.metadata or {})
    if quant:
        if meta.get("quantization") != quant:
            meta["quantization"] = quant
            pm.metadata = meta
            return True
    elif "quantization" in meta:
        meta.pop("quantization")
        pm.metadata = meta
        return True
    return False


def refresh_provider_models(provider) -> int:
    """Hit the agent's /v1/models over the tailnet and sync ProviderModel rows.

    Returns the count of models the agent currently advertises. Raises
    RefreshError with diagnostic detail on transport failure so the calling
    view can surface it (only in non-prod / for the MVP debugging period).

    When the provider has uploaded a manifest, this function never
    deactivates a model declared in that manifest — the manifest is the
    operator's declared source of truth, and the agent's live ``/v1/models``
    may legitimately be a subset (e.g. only the model currently loaded into
    vLLM). Without this guard, a manual "Refresh models" click would
    silently undo a manifest-driven sync.
    """
    if not provider.tailnet_base_url:
        raise RefreshError("provider has no tailnet_hostname yet")
    url = provider.tailnet_base_url.rstrip("/") + "/models"
    proxies = _tailnet_proxies()
    try:
        resp = requests.get(
            url,
            timeout=10,
            verify=False,
            proxies=proxies,
        )
    except requests.RequestException as e:
        logger.warning("refresh_provider_models failed for %s: %s", provider, e)
        raise RefreshError(f"GET {url} via proxies={proxies}: {type(e).__name__}: {e}") from e
    if not resp.ok:
        body = resp.text[:500]
        srv = resp.headers.get("Server", "?")
        raise RefreshError(
            f"GET {url} via proxies={proxies}: HTTP {resp.status_code} "
            f"from Server={srv!r}, body={body!r}"
        )
    payload = resp.json()
    rows = payload.get("data") or payload.get("models") or []

    incoming = {row["id"]: row for row in rows if row.get("id")}
    existing = {pm.name: pm for pm in provider.models.all()}

    manifest = getattr(provider, "manifest", None)
    declared = (
        _manifest_model_names(manifest.parsed) if manifest and manifest.is_valid else set()
    )

    if declared:
        # Manifest is the source of truth: the active set is EXACTLY the
        # declared models. The agent's live /v1/models is only a liveness
        # signal here — it may report ids that differ from the operator's
        # declared ids (e.g. a server's own short/normalized id), and we must
        # not surface those or leave stale ones active.
        for name, pm in existing.items():
            want = name in declared
            if pm.is_active != want:
                pm.is_active = want
                pm.save(update_fields=["is_active", "modified_on"])
        for name in declared:
            if name not in existing:
                ProviderModel.objects.create(
                    provider=provider, name=name, is_active=True
                )
        refreshed = len(declared)
    else:
        # No manifest: reflect exactly what the agent reports live.
        for name, pm in existing.items():
            if name not in incoming and pm.is_active:
                pm.is_active = False
                pm.save(update_fields=["is_active", "modified_on"])
        for name in incoming:
            ProviderModel.objects.update_or_create(
                provider=provider, name=name, defaults={"is_active": True}
            )
        refreshed = len(incoming)

    # Ensure every active deployment is pooled under a CatalogModel. Manifest
    # sync sets HF-derived links; this backfills live-discovered models (slug
    # derived from the served name) and anything missed.
    _link_missing_catalog(provider)

    # Store probed context windows (max_model_len) reported by the agent.
    _apply_context_lengths(provider, incoming)

    # A successful round-trip is the strongest possible "online" signal —
    # bump last_seen_at so the provider isn't shown offline to /v1/models
    # callers between actual inference requests.
    Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())
    return refreshed


def _link_missing_catalog(provider) -> None:
    """Link any active ProviderModel that has no CatalogModel yet (idempotent)."""
    for pm in provider.models.filter(is_active=True, catalog_model__isnull=True):
        link_catalog_model(pm)
        pm.save(update_fields=["catalog_model", "modified_on"])


def _apply_context_lengths(provider, incoming: dict) -> None:
    """Store each model's probed ``max_model_len`` (from the agent's live
    /v1/models rows) on its ProviderModel. Best-effort: rows without the field
    are left unchanged, so the surface falls back to the catalog/HF value."""
    for pm in provider.models.filter(is_active=True):
        row = incoming.get(pm.name)
        if not isinstance(row, dict):
            continue
        ml = row.get("max_model_len")
        if isinstance(ml, int) and ml > 0 and pm.served_context_len != ml:
            pm.served_context_len = ml
            pm.save(update_fields=["served_context_len", "modified_on"])


class RefreshProviderModelsView(APIView):
    """POST /api/inference/providers/<id>/refresh-models/ — UI-triggered model sync."""

    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        provider = get_object_or_404(Provider, id=id, user=request.user)
        try:
            count = refresh_provider_models(provider)
            error = None
        except RefreshError as e:
            count = 0
            error = str(e)
        # Always re-mirror the manifest into ProviderModel rows after a
        # refresh attempt, so the operator-declared model list survives
        # even when the agent's live /v1/models is a subset (or the agent
        # is currently offline). Source of truth is the manifest.
        manifest = getattr(provider, "manifest", None)
        if manifest is not None and manifest.is_valid:
            sync_provider_models_from_manifest(provider, manifest.parsed)
        return Response(
            {
                "refreshed": count,
                "error": error,
                "provider": ProviderSerializer(provider).data,
            }
        )


class AgentManifestView(APIView):
    """PUT /api/inference/agent/manifest/ — agent uploads its service manifest.

    Resolves the target Provider by ``(request.user, name=agent.name)`` —
    same key the register endpoint uses, so a user with multiple agents
    gets one manifest per agent.

    Always persists, even on validation failure: stores ``is_valid=False``
    plus the error list, and returns 400. The dashboard can then show
    "your manifest is broken, here's why" instead of "no manifest yet."
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def put(self, request):
        raw_yaml = request.data.get("raw_yaml") or ""
        parsed = request.data.get("parsed")
        if parsed is None:
            return Response(
                {"errors": ["body must include `parsed` (the structured manifest)"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        errors = validate_manifest(parsed, raw_yaml=raw_yaml)

        # Even if validation fails we need a Provider to attach the
        # manifest to; pull the agent name from the (possibly invalid)
        # parsed body if we can.
        agent_name = ""
        if isinstance(parsed, dict):
            agent_block = parsed.get("agent") or {}
            if isinstance(agent_block, dict):
                agent_name = (agent_block.get("name") or "").strip()

        if not agent_name:
            return Response(
                {
                    "errors": (errors or [])
                    + ["agent.name is required to bind the manifest to a provider"]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            provider = Provider.objects.get(user=request.user, name=agent_name)
        except Provider.DoesNotExist:
            return Response(
                {
                    "errors": [
                        f"no provider named {agent_name!r} for this user — "
                        "the agent must register before uploading a manifest"
                    ]
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        schema_version = (
            parsed.get("schema_version") if isinstance(parsed, dict) else None
        )
        if not isinstance(schema_version, int):
            schema_version = 1

        manifest, _ = ServiceManifest.objects.update_or_create(
            provider=provider,
            defaults={
                "schema_version": schema_version,
                "raw_yaml": raw_yaml,
                "parsed": parsed if isinstance(parsed, dict) else {},
                "is_valid": not errors,
                "validation_errors": errors,
            },
        )

        # Mirror the manifest's declared models into ProviderModel rows so
        # the dashboard and /v1/models proxy reflect every model the
        # operator has advertised — not just whatever the agent's live
        # /v1/models happens to return. Skip on validation failure so a
        # broken manifest can't wipe out a previously-good model list.
        if not errors:
            sync_provider_models_from_manifest(provider, manifest.parsed)

        body = {
            "manifest": ServiceManifestSerializer(manifest).data,
            "errors": errors,
        }
        if errors:
            return Response(body, status=status.HTTP_400_BAD_REQUEST)
        return Response(body, status=status.HTTP_200_OK)


class ProviderManifestView(APIView):
    """GET /api/inference/providers/<id>/manifest/ — owner only.

    Returns the full manifest (raw YAML + parsed + validation status) so
    the dashboard can display it and surface validation errors.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        provider = get_object_or_404(Provider, id=id, user=request.user)
        manifest = getattr(provider, "manifest", None)
        if manifest is None:
            return Response(
                {"detail": "no manifest uploaded yet"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(ServiceManifestSerializer(manifest).data)


def _daily_series(qs, days: int = 365) -> list[dict]:
    """Per-day request counts + tokens over the trailing window, for a
    GitHub-style activity heatmap. Sparse — only days with activity."""
    cutoff = timezone.now() - timedelta(days=days)
    rows = (
        qs.filter(created_on__gte=cutoff)
        .annotate(day=TruncDate("created_on"))
        .values("day")
        .annotate(count=Count("id"), tokens=Sum("total_tokens"))
        .order_by("day")
    )
    return [
        {"date": r["day"].isoformat(), "count": r["count"], "tokens": r["tokens"] or 0}
        for r in rows
        if r["day"] is not None
    ]


def _profile_stats(user) -> dict:
    """Public activity stats for a profile: what this user's computers have
    served (provider) vs what this user has consumed, as lifetime totals + a
    daily series for the heatmaps. Aggregates only — no prompt/response content.
    """
    consumed = InferenceRequest.objects.filter(user=user)
    served = InferenceRequest.objects.filter(provider__user=user)

    c = consumed.aggregate(
        requests=Count("id"),
        prompt=Sum("prompt_tokens"),
        completion=Sum("completion_tokens"),
        total=Sum("total_tokens"),
    )
    s = served.aggregate(requests=Count("id"), total=Sum("total_tokens"))

    return {
        "consumer": {
            "lifetime": {
                "requests": c["requests"] or 0,
                "prompt_tokens": c["prompt"] or 0,
                "completion_tokens": c["completion"] or 0,
                "total_tokens": c["total"] or 0,
            },
            "daily": _daily_series(consumed),
        },
        "provider": {
            "lifetime": {
                "requests": s["requests"] or 0,
                "total_tokens": s["total"] or 0,
            },
            "daily": _daily_series(served),
        },
    }


def _user_by_github_login(github_login):
    """Return ``(user, github_data)`` for a GitHub login (case-insensitive), or
    ``(None, None)`` if no such user. Signup is GitHub-only, so every user has a
    ``github`` social_auth row.

    The match is done in Python on the JSON-stored ``login`` key so it works
    regardless of whether ``extra_data`` is a JSONField or a legacy TextField.
    Prefetches the data the public profile needs; the requests endpoint reuses
    the same lookup (the extra prefetch there is negligible).
    """
    from social_django.models import UserSocialAuth

    target = (github_login or "").lower()
    social = (
        UserSocialAuth.objects.filter(provider="github")
        .select_related("user")
        .prefetch_related(
            "user__social_auth",
            "user__providers__models",
            "user__providers__manifest",
        )
    )
    for sa in social:
        login_value = (sa.extra_data or {}).get("login") or ""
        if login_value.lower() == target:
            return sa.user, (sa.extra_data or {})
    return None, None


def _user_served_models(user) -> list:
    """The catalog models this user serves (across their active providers),
    each with capabilities + which of *their* nodes serve it. Reuses
    ``serialize_catalog_entry`` so the shape matches the network catalog."""
    deploys = (
        ProviderModel.objects.filter(
            is_active=True, provider__user=user, provider__is_active=True
        )
        .select_related("provider", "catalog_model")
    )
    by_catalog: dict = {}
    for d in deploys:
        c = d.catalog_model
        if c is None:
            continue
        by_catalog.setdefault(c.id, (c, []))[1].append(d)

    entries = [serialize_catalog_entry(c, ds) for c, ds in by_catalog.values()]
    entries.sort(key=lambda e: e["display_name"].lower())
    return entries


class PublicUserProfileView(APIView):
    """GET /api/users/<github_login>/ — unauthenticated public profile.

    Returns display info, the models this user serves (with capabilities), and
    active providers with their (parsed-only) manifests. The raw YAML is never
    exposed here.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, github_login):
        user, github_data = _user_by_github_login(github_login)
        if user is None or not user.public_profile_enabled:
            return Response(
                {"detail": f"no public profile for {github_login!r}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        providers_qs = user.providers.filter(is_active=True)
        return Response(
            {
                "github_login": github_data.get("login") or github_login,
                "name": github_data.get("name") or github_data.get("login") or "",
                "avatar_url": github_data.get("avatar_url") or "",
                "github_url": (
                    f"https://github.com/{github_data.get('login')}"
                    if github_data.get("login")
                    else ""
                ),
                "joined": user.date_joined,
                "models": _user_served_models(user),
                "providers": PublicProviderSerializer(
                    providers_qs, many=True, context={"request": request}
                ).data,
                "stats": _profile_stats(user),
            }
        )


class PublicUserRequestsView(generics.ListAPIView):
    """GET /api/users/<github_login>/requests/ — unauthenticated, paginated
    list of a user's inference requests for their public profile.

    ``?scope=consumed`` (default) = requests this user made; ``?scope=served``
    = requests this user's nodes served to others; ``?scope=bookmarked`` =
    requests this user has bookmarked onto their profile. Only PUBLIC requests
    are listed (UNLISTED/PRIVATE/SECRET never surface publicly). ``is_owner`` is
    always False here (anonymous), so no delete affordance is exposed.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    pagination_class = StandardResultsSetPagination
    serializer_class = InferenceRequestListSerializer

    def get_queryset(self):
        user, _ = _user_by_github_login(self.kwargs["github_login"])
        if user is None or not user.public_profile_enabled:
            raise Http404("no such profile")
        scope = self.request.query_params.get("scope")
        qs = _requests_with_owner()
        if scope == "served":
            qs = qs.filter(provider__user=user)
        elif scope == "bookmarked":
            bookmarked_ids = Bookmark.objects.filter(user=user).values_list(
                "request_id", flat=True
            )
            qs = qs.filter(id__in=list(bookmarked_ids))
        else:
            qs = qs.filter(user=user)
        # Public profile shows PUBLIC content only, whoever owns it.
        qs = qs.filter(visibility=VISIBILITY_PUBLIC)
        return _apply_request_filters(qs, self.request.query_params)


# --- Collections ---------------------------------------------------------


def _unique_collection_slug(user, name, instance=None) -> str:
    """A slug unique within ``user``'s collections, derived from ``name``."""
    base = slugify(name) or "collection"
    slug = base
    n = 2
    qs = Collection.objects.filter(user=user)
    if instance is not None:
        qs = qs.exclude(pk=instance.pk)
    while qs.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _collection_with_items(col, request) -> dict:
    """Serialize a collection plus the items the caller may see (each item still
    enforces its own visibility)."""
    items_qs = (
        _requests_with_owner()
        .filter(collection_items__collection=col)
        .order_by("collection_items__position", "-created_on")
    )
    viewer = request.user if request.user.is_authenticated else None
    items_qs = _annotate_viewer_flags(items_qs, viewer)
    items = [ir for ir in items_qs if ir.is_visible_to(request.user)]
    data = CollectionSerializer(col, context={"request": request}).data
    data["items"] = InferenceRequestListSerializer(
        items, many=True, context={"request": request}
    ).data
    return data


class CollectionListCreateView(generics.ListCreateAPIView):
    """GET lists the caller's collections; POST creates one (slug derived from
    the name)."""

    permission_classes = [IsAuthenticated]
    serializer_class = CollectionSerializer

    def get_queryset(self):
        return (
            Collection.objects.filter(user=self.request.user)
            .annotate(item_count=Count("items"))
            .select_related("cover_request")
        )

    def create(self, request, *args, **kwargs):
        ser = CollectionWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        slug = _unique_collection_slug(request.user, ser.validated_data["name"])
        col = Collection.objects.create(user=request.user, slug=slug, **ser.validated_data)
        return Response(
            CollectionSerializer(col, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class CollectionDetailView(APIView):
    """GET (collection + items) / PATCH / DELETE one of the caller's
    collections, keyed by slug. The slug stays stable across renames so shared
    links don't break."""

    permission_classes = [IsAuthenticated]

    def _get(self, request, slug):
        return get_object_or_404(Collection, user=request.user, slug=slug)

    def get(self, request, slug):
        return Response(_collection_with_items(self._get(request, slug), request))

    def patch(self, request, slug):
        col = self._get(request, slug)
        ser = CollectionWriteSerializer(col, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(CollectionSerializer(col, context={"request": request}).data)

    def delete(self, request, slug):
        self._get(request, slug).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CollectionItemView(APIView):
    """POST/DELETE /api/inference/collections/<slug>/items/<request_id>/ — add
    or remove a request from one of the caller's collections."""

    permission_classes = [IsAuthenticated]

    def post(self, request, slug, request_id):
        col = get_object_or_404(Collection, user=request.user, slug=slug)
        ir = _get_owned_or_visible_request(request, request_id)
        CollectionItem.objects.get_or_create(collection=col, request=ir)
        return Response({"in_collection": True})

    def delete(self, request, slug, request_id):
        col = get_object_or_404(Collection, user=request.user, slug=slug)
        CollectionItem.objects.filter(collection=col, request_id=request_id).delete()
        return Response({"in_collection": False})


class PublicUserCollectionsView(APIView):
    """GET /api/users/<github_login>/collections/ — the user's PUBLIC
    collections, for their profile. 404 when the profile is disabled."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, github_login):
        user, _ = _user_by_github_login(github_login)
        if user is None or not user.public_profile_enabled:
            raise Http404("no such profile")
        cols = (
            Collection.objects.filter(user=user, visibility=VISIBILITY_PUBLIC)
            .annotate(item_count=Count("items"))
            .select_related("cover_request")
        )
        return Response(
            CollectionSerializer(cols, many=True, context={"request": request}).data
        )


class PublicCollectionDetailView(APIView):
    """GET /api/users/<github_login>/collections/<slug>/ — a PUBLIC collection +
    its publicly-visible items."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, github_login, slug):
        user, _ = _user_by_github_login(github_login)
        if user is None or not user.public_profile_enabled:
            raise Http404("no such profile")
        col = get_object_or_404(
            Collection, user=user, slug=slug, visibility=VISIBILITY_PUBLIC
        )
        return Response(_collection_with_items(col, request))


import os as _os

_OPENAPI_PATH = _os.path.join(_os.path.dirname(__file__), "openapi.yaml")
_openapi_cache: dict = {}


def _openapi_yaml_text() -> str:
    if "yaml" not in _openapi_cache:
        with open(_OPENAPI_PATH, encoding="utf-8") as f:
            _openapi_cache["yaml"] = f.read()
    return _openapi_cache["yaml"]


def _openapi_spec() -> dict:
    if "spec" not in _openapi_cache:
        import yaml

        _openapi_cache["spec"] = yaml.safe_load(_openapi_yaml_text())
    return _openapi_cache["spec"]


class OpenAPISchemaView(APIView):
    """``GET /openapi.json`` / ``/openapi.yaml`` — the public OpenAPI 3.1 spec
    for the OpenAI-compatible inference endpoints. Unauthenticated so the docs
    page (and any external tool) can load it; CORS headers are added by the
    corsheaders middleware for allowed origins. Set ``as_yaml=True`` in the URL
    conf to serve raw YAML."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    as_yaml = False

    def get(self, request):
        from django.http import HttpResponse, JsonResponse

        if self.as_yaml:
            return HttpResponse(_openapi_yaml_text(), content_type="application/yaml")
        return JsonResponse(_openapi_spec())


class MediaAssetView(APIView):
    """``GET /api/inference/assets/<id>/`` — stream a stored media asset
    (STT input audio, generated/edited images) from MinIO/disk.

    Streaming through the app keeps one path that works whether the asset
    lives on local disk (dev) or S3/MinIO (prod), without exposing a public
    bucket. Image kinds are served publicly by URL (so generated images embed
    in <img> tags and can show on profiles); private kinds (uploaded audio)
    stay owner-gated.
    """

    permission_classes = [AllowAny]

    def get(self, request, id):
        from django.http import FileResponse

        asset = get_object_or_404(MediaAsset, id=id)
        if asset.kind not in MediaAsset.PUBLIC_KINDS:
            if not request.user.is_authenticated or asset.user_id != request.user.id:
                raise PermissionDenied("Not your asset.")
        try:
            fh = asset.file.open("rb")
        except (FileNotFoundError, ValueError):
            raise Http404("asset file missing")
        resp = FileResponse(
            fh, content_type=asset.content_type or "application/octet-stream"
        )
        resp["Content-Disposition"] = (
            f'inline; filename="{(asset.file.name or "asset").rsplit("/", 1)[-1]}"'
        )
        # Public images are cacheable; private assets must not be cached by
        # shared proxies.
        if asset.kind in MediaAsset.PUBLIC_KINDS:
            resp["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            resp["Cache-Control"] = "private, no-store"
        return resp
