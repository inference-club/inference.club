import logging
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from .manifest_validator import validate as validate_manifest
from .models import (
    InferenceRequest,
    Provider,
    ProviderModel,
    ProviderService,
    ServiceManifest,
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
    ).prefetch_related("user__social_auth")


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
                    mid = m.get("id")
                    if isinstance(mid, str) and mid.strip():
                        names.add(mid.strip())
    return names


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
            model_ids = set()
            for m in svc.get("models") or []:
                if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"].strip():
                    model_ids.add(m["id"].strip())
            out.append(
                {
                    "name": name.strip(),
                    "host_id": host_id or "",
                    "engine": svc.get("engine") if isinstance(svc.get("engine"), str) else "",
                    "model_ids": model_ids,
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
    for sd in services_data:
        for mid in sd["model_ids"]:
            declared_models.add(mid)
            model_to_service.setdefault(mid, service_by_name[sd["name"]])

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
        if fields:
            pm.save(update_fields=fields + ["modified_on"])
    for name in declared_models:
        if name not in existing:
            ProviderModel.objects.create(
                provider=provider,
                name=name,
                is_active=True,
                service=model_to_service.get(name),
            )
    return len(declared_models)


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

    for name, pm in existing.items():
        if name not in incoming and name not in declared and pm.is_active:
            pm.is_active = False
            pm.save(update_fields=["is_active", "modified_on"])
    for name in incoming:
        ProviderModel.objects.update_or_create(
            provider=provider, name=name, defaults={"is_active": True}
        )

    # A successful round-trip is the strongest possible "online" signal —
    # bump last_seen_at so the provider isn't shown offline to /v1/models
    # callers between actual inference requests.
    Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())
    return len(incoming)


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


class PublicUserProfileView(APIView):
    """GET /api/users/<github_login>/ — unauthenticated public profile.

    Looks up a user by their GitHub login (since signup is GitHub-only,
    every user has one) via the ``social_auth`` reverse manager.

    Returns display info plus active providers with their (parsed-only)
    manifests. The raw YAML is never exposed here.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, github_login):
        # Case-insensitive match on the JSON-stored ``login`` key, done in
        # Python so it works regardless of whether ``extra_data`` is stored
        # as a JSONField or a legacy TextField.
        from social_django.models import UserSocialAuth

        target = github_login.lower()
        social = (
            UserSocialAuth.objects.filter(provider="github")
            .select_related("user")
            .prefetch_related(
                "user__social_auth",
                "user__providers__models",
                "user__providers__manifest",
            )
        )
        match = None
        for sa in social:
            login_value = (sa.extra_data or {}).get("login") or ""
            if login_value.lower() == target:
                match = sa
                break

        if match is None:
            return Response(
                {"detail": f"no user with github login {github_login!r}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        user = match.user
        github_data = match.extra_data or {}

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
                "providers": PublicProviderSerializer(
                    providers_qs, many=True, context={"request": request}
                ).data,
            }
        )
