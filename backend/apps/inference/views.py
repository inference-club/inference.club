import logging
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Prefetch, Sum
from django.db.models.functions import TruncDate
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from .manifest_validator import validate as validate_manifest
from .hf_enrich import enrich_catalog_model
from .models import (
    CatalogModel,
    InferenceRequest,
    MediaAsset,
    Provider,
    ProviderModel,
    ProviderService,
    ServiceManifest,
    link_catalog_model,
    slugify_model_id,
)
from .pagination import StandardResultsSetPagination
from .serializers import (
    AgentRegisterSerializer,
    InferenceRequestDetailSerializer,
    InferenceRequestListSerializer,
    InferenceRequestSerializer,
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
        return _requests_with_owner().filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AllInferenceRequestView(generics.ListAPIView):
    """Every inference request on the network (powers "All Inference
    Requests"). Visible to any authenticated user, with owner attribution."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    serializer_class = InferenceRequestListSerializer

    def get_queryset(self):
        return _requests_with_owner()


class RetrieveInferenceRequestView(generics.RetrieveDestroyAPIView):
    """GET returns any request fully-expanded (the All view links here);
    DELETE is restricted to the request's owner."""

    permission_classes = [IsAuthenticated]
    serializer_class = InferenceRequestDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        return _requests_with_owner()

    def perform_destroy(self, instance):
        if instance.user_id != self.request.user.id:
            raise PermissionDenied("You can only delete your own inference requests.")
        instance.delete()


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
# See docs/plans/openrouter-provider-compatibility.md. We build rich per-model
# metadata from light id heuristics + operator overrides (ProviderModel.metadata)
# + sensible defaults, so the catalog is credible without agent changes.

_QUANT_HEURISTICS = [
    ("fp4", ("nvfp4", "mxfp4", "fp4")),
    ("fp6", ("fp6",)),
    ("fp8", ("fp8",)),
    ("bf16", ("bf16",)),
    ("fp16", ("fp16", "half")),
    ("fp32", ("fp32",)),
    ("int4", ("int4", "awq", "gptq", "q4", "4bit", "w4a16")),
    ("int8", ("int8", "q8", "8bit", "w8a8")),
]

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


def _guess_quantization(model_id: str):
    s = model_id.lower()
    for canonical, needles in _QUANT_HEURISTICS:
        if any(n in s for n in needles):
            return canonical
    return None


def _guess_features(model_id: str) -> list[str]:
    s = model_id.lower()
    feats = []
    if any(k in s for k in ("reason", "thinking", "-r1", "qwq")):
        feats.append("reasoning")
    return feats


def _guess_modalities(model_id: str):
    s = model_id.lower()
    inp = ["text"]
    if any(k in s for k in ("vl", "vision", "omni", "image", "multimodal")):
        inp.append("image")
    return inp, ["text"]


def openrouter_model_schema(pm) -> dict:
    """Build the OpenRouter provider `data[]` entry for a ProviderModel."""
    meta = pm.metadata if isinstance(pm.metadata, dict) else {}
    model_id = pm.name
    inp_default, out_default = _guess_modalities(model_id)
    created_dt = pm.created_on or pm.provider.created_on

    out = {
        "id": model_id,
        "name": meta.get("name") or model_id,
        "created": int(created_dt.timestamp()) if created_dt else 0,
        "input_modalities": meta.get("input_modalities") or inp_default,
        "output_modalities": meta.get("output_modalities") or out_default,
        "context_length": (
            meta.get("context_length")
            if meta.get("context_length") is not None
            else pm.context_window
        ),
        "max_output_length": meta.get("max_output_length"),
        # No economic model yet — pricing is present (OpenRouter requires it)
        # but zeroed. See §2 of the compatibility doc.
        "pricing": meta.get("pricing")
        or {"prompt": "0", "completion": "0", "request": "0", "image": "0"},
        "supported_sampling_parameters": meta.get("supported_sampling_parameters")
        or _DEFAULT_SAMPLING_PARAMS,
        "supported_features": meta.get("supported_features") or _guess_features(model_id),
        "is_ready": meta.get("is_ready", True),
    }
    quant = meta.get("quantization") or _guess_quantization(model_id)
    if quant:
        out["quantization"] = quant
    if meta.get("description"):
        out["description"] = meta["description"]
    if meta.get("hugging_face_id"):
        out["hugging_face_id"] = meta["hugging_face_id"]
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


# Lazy-enrich at most this many un-synced models per catalog page view, so the
# first visit "just works" without a slow unbounded burst of HF calls.
_LAZY_ENRICH_CAP = 15


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
    # precedence over the HF-derived ceiling.
    context_length = (max(served) if served else None) or catalog.native_context_length
    md = catalog.metadata or {}
    return {
        "slug": catalog.slug,
        "display_name": catalog.display_name or catalog.slug,
        "hf_repo_id": catalog.hf_repo_id,
        "hf_url": catalog.hf_url,
        "is_custom": catalog.is_custom,
        "architecture": catalog.architecture,
        "context_length": context_length,
        "input_modalities": catalog.input_modalities or [],
        "output_modalities": catalog.output_modalities or [],
        "supported_features": catalog.supported_features or [],
        "pipeline_tag": md.get("pipeline_tag"),
        "downloads": md.get("downloads"),
        "likes": md.get("likes"),
        "provider_count": len(providers),
        "online_provider_count": sum(1 for v in providers.values() if v["online"]),
        "providers": sorted(providers.values(), key=lambda v: v["name"]),
    }


def _lazy_enrich(catalogs) -> None:
    """Best-effort, bounded HF enrichment for never-synced catalogs. Never lets
    enrichment break the calling view."""
    for c in [c for c in catalogs if c.hf_repo_id and c.hf_synced_at is None][:_LAZY_ENRICH_CAP]:
        try:
            enrich_catalog_model(c)
        except Exception:  # never let enrichment break the listing
            logger.exception("lazy enrich failed for %s", c.slug)


class ModelCatalogView(APIView):
    """GET /api/inference/models/ — the human-facing network model catalog.

    One entry per CatalogModel that has at least one active deployment, with
    HuggingFace-enriched metadata (modalities, context, features) and which
    nodes serve it. Un-synced models are enriched lazily (bounded) on view;
    `manage.py enrich_catalog` does the authoritative/bulk sync.
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

        # Lazy, bounded, best-effort enrichment for anything never synced.
        _lazy_enrich(catalogs)

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
                models_list.append({"served": served, "hf": _model_hf_id(m)})
            svc_type = svc.get("type")
            if not isinstance(svc_type, str) or svc_type not in ("llm", "stt", "tts", "image"):
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
    for sd in services_data:
        for m in sd["models"]:
            served = m["served"]
            declared_models.add(served)
            model_to_service.setdefault(served, service_by_name[sd["name"]])
            if m["hf"]:
                model_hf.setdefault(served, m["hf"])

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
            catalog = link_catalog_model(pm)
            _apply_service_type_modalities(catalog, svc)
            fields.append("catalog_model")
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
            _apply_service_type_modalities(catalog, svc)
            pm.save()
    return len(declared_models)


def _apply_service_type_modalities(catalog, service) -> None:
    """Seed sensible input/output modalities on a freshly-pooled catalog model
    from its service type, so non-text models render correctly *before* the
    lazy HuggingFace enrichment runs (and for models with no HF id at all).

    Only fills when the catalog hasn't been HF-enriched yet — never clobbers
    richer enriched data.
    """
    if service is None or catalog.hf_synced_at is not None:
        return
    stype = getattr(service, "service_type", "llm")
    if stype == "stt":
        inp, out = ["audio"], ["text"]
    elif stype == "tts":
        inp, out = ["text"], ["audio"]
    elif stype == "image":
        # Text prompt always; image input for the edits endpoint.
        inp, out = ["text", "image"], ["image"]
    else:
        return
    fields = []
    if catalog.input_modalities != inp:
        catalog.input_modalities = inp
        fields.append("input_modalities")
    if catalog.output_modalities != out:
        catalog.output_modalities = out
        fields.append("output_modalities")
    if fields:
        catalog.save(update_fields=fields + ["modified_on"])


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

    _lazy_enrich([c for c, _ in by_catalog.values()])
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
        if user is None:
            return Response(
                {"detail": f"no user with github login {github_login!r}"},
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
    = requests this user's nodes served to others. Reuses the same slim card
    serializer as the dashboard; ``is_owner`` is always False here (anonymous),
    so no delete affordance is exposed.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    pagination_class = StandardResultsSetPagination
    serializer_class = InferenceRequestListSerializer

    def get_queryset(self):
        user, _ = _user_by_github_login(self.kwargs["github_login"])
        if user is None:
            raise Http404("no such user")
        qs = _requests_with_owner()
        if self.request.query_params.get("scope") == "served":
            return qs.filter(provider__user=user)
        return qs.filter(user=user)


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
