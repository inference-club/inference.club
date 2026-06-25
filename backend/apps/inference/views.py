import ipaddress
import logging
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Exists, Max, OuterRef, Prefetch, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
)
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from apps.core.permissions import IsFullMember

from .manifest_validator import SERVICE_TYPES
from .manifest_validator import validate as validate_manifest
from .sharing import unique_collection_slug
from .models import (
    Bookmark,
    CatalogModel,
    ChatThread,
    Collection,
    CollectionItem,
    ContentReport,
    InferenceRequest,
    ManifestRevision,
    MediaAsset,
    Provider,
    ProviderModel,
    ProviderService,
    ServiceManifest,
    Star,
    VISIBILITY_PUBLIC,
    VoiceSample,
    link_catalog_model,
    slugify_model_id,
    visible_list_q,
)
from .pagination import StandardResultsSetPagination
from .serializers import (
    AgentRegisterSerializer,
    ChatThreadListSerializer,
    ChatThreadSerializer,
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
    VoiceSampleSerializer,
    VoiceSampleWriteSerializer,
    _cover_image_url,
    _user_github_login,
    _user_owner,
)
from .tailscale import mint_authkey_for_provider

logger = logging.getLogger("django")


# Owner-attribution querysets need the user + their GitHub social_auth row.
def _requests_with_owner():
    return InferenceRequest.objects.select_related(
        "provider", "provider__manifest", "user", "cover_request", "host", "gpu"
    ).prefetch_related(
        "user__social_auth", "assets", "cover_request__assets", "host__gpus"
    )


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
    requests plus their own; UNLISTED and SECRET are excluded from the feed.
    Open to anonymous visitors too — ``visible_list_q`` narrows them to PUBLIC
    only, so the logged-out dashboard can showcase what the club is making."""

    permission_classes = [AllowAny]
    pagination_class = StandardResultsSetPagination
    serializer_class = InferenceRequestListSerializer

    def get_queryset(self):
        qs = _requests_with_owner().filter(visible_list_q(self.request.user))
        qs = _annotate_viewer_flags(qs, self.request.user)
        return _apply_request_filters(qs, self.request.query_params)


class RetrieveInferenceRequestView(generics.RetrieveUpdateDestroyAPIView):
    """GET returns a request fully-expanded (subject to its visibility); PATCH
    changes its visibility (owner only); DELETE removes it (owner only).

    Reads are open to anyone (``get_object`` enforces ``is_visible_to``, so a
    logged-out visitor can open a PUBLIC/UNLISTED request by its opaque
    ``public_id``); writes require auth and are owner-only."""

    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = "id"

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return InferenceRequestVisibilitySerializer
        return InferenceRequestDetailSerializer

    def get_queryset(self):
        return _annotate_viewer_flags(_requests_with_owner(), self.request.user)

    def get_object(self):
        # Resolve by opaque public_id first; fall back to the numeric PK so old
        # /requests/<int>/ links keep working.
        raw = str(self.kwargs.get(self.lookup_field, ""))
        qs = self.filter_queryset(self.get_queryset())
        obj = qs.filter(public_id=raw).first()
        if obj is None and raw.isdigit():
            obj = qs.filter(pk=int(raw)).first()
        if obj is None:
            raise Http404("no such inference request")
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


def _maybe_generate_title(thread):
    """Enqueue async AI title generation if this thread still needs one and has
    something to summarize. The task is a no-op once a title lands, so a couple
    of redundant enqueues across create/update are harmless."""
    if thread.title_generated or thread.title:
        return
    msgs = thread.messages or []
    if not any(isinstance(m, dict) and m.get("role") == "user" for m in msgs):
        return
    from .tasks import generate_chat_title

    try:
        generate_chat_title.delay(thread.id)
    except Exception:
        logger.exception("could not enqueue chat title for thread %s", thread.id)


class ChatThreadView(generics.ListCreateAPIView):
    """GET lists the user's saved chat threads (newest first); POST creates one
    from the playground after the first exchange."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ChatThreadSerializer
        return ChatThreadListSerializer

    def get_queryset(self):
        qs = ChatThread.objects.filter(user=self.request.user)
        if self.request.method != "POST":
            # Optional ?source=chat|agent|voice filter for the badged history.
            source = self.request.query_params.get("source")
            if source in dict(ChatThread.Source.choices):
                qs = qs.filter(source=source)
            # The list never needs the (potentially large) messages blob.
            qs = qs.defer("messages")
        return qs

    def perform_create(self, serializer):
        thread = serializer.save(user=self.request.user)
        _maybe_generate_title(thread)


class ChatThreadDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET returns a thread fully expanded (messages included); PATCH appends the
    latest turn(s); DELETE removes it. Owner-only throughout."""

    permission_classes = [IsAuthenticated]
    serializer_class = ChatThreadSerializer
    lookup_field = "id"

    def get_queryset(self):
        return ChatThread.objects.filter(user=self.request.user)

    def get_object(self):
        # Resolve by opaque public_id first; fall back to the numeric PK.
        raw = str(self.kwargs.get(self.lookup_field, ""))
        qs = self.filter_queryset(self.get_queryset())
        obj = qs.filter(public_id=raw).first()
        if obj is None and raw.isdigit():
            obj = qs.filter(pk=int(raw)).first()
        if obj is None:
            raise Http404("no such chat thread")
        return obj

    def perform_update(self, serializer):
        thread = serializer.save()
        _maybe_generate_title(thread)


class ApiKeyListView(APIView):
    """``GET /api/inference/api-keys/`` — the known external services merged with
    this user's set status. Never returns the actual keys, only a masked hint."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.accounts.models import UserApiKey

        from .external_keys import EXTERNAL_SERVICES

        rows = {r.service: r for r in UserApiKey.objects.filter(user=request.user)}
        legacy_brave = getattr(request.user, "brave_api_key", "") or ""
        data = []
        for svc in EXTERNAL_SERVICES:
            row = rows.get(svc.slug)
            is_set = bool(row and row.value)
            hint = row.hint if row else ""
            # Surface a legacy Brave key (pre-UserApiKey) as set.
            if not is_set and svc.slug == "brave" and legacy_brave:
                is_set = True
                hint = f"…{legacy_brave[-4:]}" if len(legacy_brave) >= 8 else "set"
            data.append({
                "service": svc.slug,
                "name": svc.name,
                "description": svc.description,
                "docs_url": svc.docs_url,
                "is_set": is_set,
                "hint": hint,
                "updated": row.modified_on if row else None,
            })
        return Response({"data": data})


class ApiKeyDetailView(APIView):
    """``PUT``/``DELETE /api/inference/api-keys/<service>/`` — set or clear the
    user's key for a known service. PUT body: ``{"value": "<key>"}``."""

    permission_classes = [IsAuthenticated]

    def put(self, request, service):
        from .external_keys import get_service, set_user_api_key

        if not get_service(service):
            return Response({"error": "Unknown service"}, status=status.HTTP_400_BAD_REQUEST)
        value = (request.data.get("value") or "").strip()
        if not value:
            return Response({"error": "value is required"}, status=status.HTTP_400_BAD_REQUEST)
        set_user_api_key(request.user, service, value)
        # Keep the legacy single Brave field in sync for any un-migrated readers.
        if service == "brave":
            request.user.brave_api_key = value[:128]
            request.user.save(update_fields=["brave_api_key"])
        return Response({"service": service, "is_set": True})

    def delete(self, request, service):
        from .external_keys import clear_user_api_key, get_service

        if not get_service(service):
            return Response({"error": "Unknown service"}, status=status.HTTP_400_BAD_REQUEST)
        clear_user_api_key(request.user, service)
        if service == "brave" and getattr(request.user, "brave_api_key", ""):
            request.user.brave_api_key = ""
            request.user.save(update_fields=["brave_api_key"])
        return Response({"service": service, "is_set": False})


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


class RequestFeatureView(APIView):
    """POST/DELETE /api/inference/requests/<id>/feature/ — staff-only toggle
    marking a request as featured on the public home page. Only PUBLIC
    requests qualify (the showcase is world-readable, so nothing
    unlisted/private may be pinned to it)."""

    permission_classes = [IsAuthenticated]

    def _check(self, request, id):
        if not request.user.is_staff:
            raise PermissionDenied("Only staff can feature requests.")
        return get_object_or_404(InferenceRequest, id=id)

    def post(self, request, id):
        obj = self._check(request, id)
        if obj.visibility != VISIBILITY_PUBLIC:
            return Response(
                {"detail": "Only PUBLIC requests can be featured."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.featured_at = timezone.now()
        obj.save(update_fields=["featured_at", "modified_on"])
        return Response({"is_featured": True})

    def delete(self, request, id):
        obj = self._check(request, id)
        obj.featured_at = None
        obj.save(update_fields=["featured_at", "modified_on"])
        return Response({"is_featured": False})


def _provider_gpus(provider) -> list[str]:
    """GPU model names from the provider's manifest (all hosts, deduped,
    order preserved), e.g. ["RTX 4090"]. Empty when no valid manifest."""
    if provider is None:
        return []
    manifest = getattr(provider, "manifest", None)
    if manifest is None or not isinstance(manifest.parsed, dict):
        return []
    out: list[str] = []
    for host in manifest.parsed.get("hosts") or []:
        if not isinstance(host, dict):
            continue
        # Manifests use a singular ``gpu`` (dict or string) per host or a
        # ``gpus`` list of dicts — support both.
        candidates = list(host.get("gpus") or [])
        if host.get("gpu"):
            candidates.append(host["gpu"])
        for gpu in candidates:
            model = gpu.get("model") if isinstance(gpu, dict) else gpu
            if model and str(model) not in out:
                out.append(str(model))
    return out


class FeaturedContentView(APIView):
    """GET /api/inference/featured/ — the most recently featured PUBLIC
    request per inference_type, for the home-page showcase. World-readable.
    Types with nothing featured are simply absent."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        qs = (
            _requests_with_owner()
            .select_related("provider__manifest")
            .filter(featured_at__isnull=False, visibility=VISIBILITY_PUBLIC)
            .order_by("-featured_at")
        )
        picks: dict[str, InferenceRequest] = {}
        for ir in qs:
            if ir.inference_type not in picks:
                picks[ir.inference_type] = ir
        items = []
        for ir in picks.values():
            data = InferenceRequestListSerializer(
                ir, context={"request": request}
            ).data
            # The card links to /s/<token>; the serializer hides the token
            # from non-owners, but PUBLIC content is already open to anyone.
            data["share_token"] = ir.share_token
            data["gpus"] = _provider_gpus(ir.provider)
            data["featured_at"] = ir.featured_at
            items.append(data)
        items.sort(key=lambda d: d["featured_at"], reverse=True)
        return Response(items)


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

    Full members only — guest/passcode accounts are playground-only and must
    never join the tailnet or register compute.
    """

    permission_classes = [IsFullMember]

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


# Tailscale hands out node addresses from the 100.64.0.0/10 CGNAT range.
_TAILNET_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _valid_tailnet_addr(value) -> str:
    """Return a trusted tailnet IPv4 string, or '' if not a usable address.

    Guards the SOCKS dial target: we only accept an IPv4 inside Tailscale's
    100.64.0.0/10 range so an agent can't steer the proxy at a LAN host.
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return ""
    if ip.version != 4 or ip not in _TAILNET_CGNAT:
        return ""
    return str(ip)


class AgentHeartbeatView(APIView):
    """POST /api/inference/agent/heartbeat/ — lightweight liveness beacon.

    The push half of liveness (PRD: agent beacon, phase 1). The agent calls
    this on a fixed interval over its existing outbound connection, so a
    healthy provider stays "online" without the backend having to reach back
    into it over the tailnet. That decouples "is the agent alive" from "can the
    backend probe it right now" — the latter was the only signal before, which
    painted healthy-but-unreachable clusters (and every local-dev provider) as
    offline.

    Resolves the provider by ``(user, name)`` like register, stamps
    ``last_seen_at`` with **server receipt time** (never an agent-supplied
    clock), and returns 200. The inbound ``/healthz`` probe and the
    inference-request bumps stay as fallbacks for agents that don't beacon yet.

    Full members only — guests never register compute.
    """

    permission_classes = [IsFullMember]

    def post(self, request):
        name = (request.data.get("name") or "").strip() or "club-host"
        try:
            provider = Provider.objects.get(user=request.user, name=name)
        except Provider.DoesNotExist:
            return Response(
                {
                    "detail": (
                        f"no provider named {name!r} for this user — "
                        "the agent must register before sending heartbeats"
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        now = timezone.now()
        updates = {"last_seen_at": now}
        # The agent reports its actual tailnet IP once it has joined, so the
        # backend dials the live node directly instead of a MagicDNS hostname
        # that Tailscale may have renamed on rejoin (club-host-1 → club-host-1-1).
        # Only accept addresses in Tailscale's 100.64.0.0/10 (CGNAT) range so a
        # misbehaving agent can't point the SOCKS proxy at arbitrary hosts.
        addr = _valid_tailnet_addr(request.data.get("tailnet_addr"))
        if addr and addr != provider.tailnet_addr:
            updates["tailnet_addr"] = addr
        Provider.objects.filter(id=provider.id).update(**updates)
        return Response(
            {"provider_id": provider.id, "online": True, "last_seen_at": now},
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

    Exposes per-node detail to anyone, including the owner (public GitHub
    handle), so the network is legible — same public surface as the network
    status view. Inactive providers are hidden.
    """

    permission_classes = [AllowAny]
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

    permission_classes = [IsFullMember]
    serializer_class = ProviderServiceSerializer
    lookup_field = "id"

    def get_queryset(self):
        return (
            ProviderService.objects.filter(provider__user=self.request.user)
            .select_related("provider")
            .prefetch_related("models")
        )


SERVICE_LOGO_MAX_BYTES = 2 * 1024 * 1024  # 2 MB — logos are small brand marks
SERVICE_LOGO_TYPES = {
    "image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml",
}


class ServiceLogoView(APIView):
    """Upload (POST, multipart ``logo``) or clear (DELETE) a service's custom
    logo. Owner-only — a member may only touch their own services. The file
    lands in the public media bucket; its URL is surfaced through the manifest's
    enriched ``parsed`` services as ``logo_url`` (see serializers)."""

    permission_classes = [IsFullMember]
    parser_classes = [MultiPartParser, FormParser]

    def _service(self, request, pk):
        return get_object_or_404(
            ProviderService, id=pk, provider__user=request.user
        )

    def post(self, request, pk):
        from django.core.files.base import ContentFile

        svc = self._service(request, pk)
        upload = request.FILES.get("logo")
        if upload is None:
            return Response(
                {"detail": "`logo` file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ctype = (
            (getattr(upload, "content_type", "") or "").split(";", 1)[0].strip().lower()
        )
        if ctype not in SERVICE_LOGO_TYPES:
            return Response(
                {"detail": f"Unsupported image type '{ctype or 'unknown'}'."},
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )
        data = upload.read()
        if len(data) > SERVICE_LOGO_MAX_BYTES:
            return Response(
                {"detail": "Logo too large (max 2 MB)."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        # Replace any previous logo so old files don't orphan in the bucket.
        if svc.logo:
            svc.logo.delete(save=False)
        svc.logo.save(
            getattr(upload, "name", "logo") or "logo", ContentFile(data), save=False
        )
        svc.save(update_fields=["logo", "modified_on"])
        return Response({"logo_url": svc.logo.url})

    def delete(self, request, pk):
        svc = self._service(request, pk)
        if svc.logo:
            svc.logo.delete(save=False)
            svc.logo = None
            svc.save(update_fields=["logo", "modified_on"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProviderUpdateView(generics.RetrieveUpdateAPIView):
    """PATCH a provider's owner-editable settings (the accepting_requests
    pause/kill switch). Scoped to the owner."""

    permission_classes = [IsFullMember]
    serializer_class = ProviderUpdateSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Provider.objects.filter(user=self.request.user)


class LeaderboardView(APIView):
    """Top token consumers over a time window. A deliberately public, social
    view of network usage — open to logged-out visitors too."""

    permission_classes = [AllowAny]

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


def scope_usage(scope, ident, rate=None):
    """Current usage for a throttle scope + identity, read straight from the
    throttle cache (no quota consumed). Returns None if the scope has no rate.

    Mirrors DRF's SimpleRateThrottle cache key/format so it reflects exactly
    what the throttle enforces. ``rate`` overrides the settings lookup for
    scopes whose rate lives elsewhere (the AccessPolicy anon scopes).
    """
    rate = rate or api_settings.DEFAULT_THROTTLE_RATES.get(scope)
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
        from .throttling import anon_scope_rate, is_anon_account

        ident = request.user.pk
        if is_anon_account(request.user):
            usages = (
                scope_usage(f"{s}_anon", ident, rate=anon_scope_rate(s))
                for s in INFERENCE_THROTTLE_SCOPES
            )
        else:
            usages = (scope_usage(s, ident) for s in INFERENCE_THROTTLE_SCOPES)
        scopes = [u for u in usages if u is not None]
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


def serialize_catalog_entry(catalog, deployments, include_offline=True):
    """Build the public catalog dict for one CatalogModel given an iterable of
    its active deployments. Shared by ModelCatalogView (network-wide) and the
    public profile (scoped to one user's deployments).

    When ``include_offline`` is False, deployments on offline nodes are dropped
    and a model with no online deployment returns ``None`` — so the catalog
    reflects what's actually runnable right now (no stale, retired services)."""
    providers = {}
    served = []
    for d in deployments:
        p = d.provider
        if not include_offline and not p.is_online:
            continue
        providers[p.id] = {"name": p.name, "online": p.is_online}
        if d.served_context_len:
            served.append(d.served_context_len)
    if not include_offline and not providers:
        return None
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
    nodes serve it. Open to logged-out visitors — the catalog is public network
    data (the same models are already surfaced on public profiles).
    """

    permission_classes = [AllowAny]

    def get(self, request):
        # Default to "runnable right now": models with at least one online
        # deployment. ``?include_offline=1`` returns everything (incl. retired
        # nodes) for completeness/debugging.
        include_offline = request.query_params.get("include_offline") in (
            "1", "true", "yes",
        )
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
            entry
            for c in catalogs
            if (
                entry := serialize_catalog_entry(
                    c, getattr(c, "active_deployments", []), include_offline=include_offline
                )
            )
            is not None
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
            mc = svc.get("max_concurrent")
            mc = mc if isinstance(mc, int) and mc >= 1 else 1
            rg = svc.get("resource_group")
            rg = rg.strip() if isinstance(rg, str) else ""
            out.append(
                {
                    "name": name.strip(),
                    "host_id": host_id or "",
                    "engine": svc.get("engine") if isinstance(svc.get("engine"), str) else "",
                    "service_type": svc_type,
                    "features": features,
                    "max_concurrent": mc,
                    "resource_group": rg,
                    "models": models_list,
                }
            )
    return out


def _sync_resource_groups(provider, parsed) -> None:
    """Mirror the manifest's top-level ``resource_groups`` into ResourceGroup
    rows (PRD 10 capacity pools). Groups absent from the manifest are dropped —
    they carry no operator state worth preserving, unlike services."""
    from .models import ResourceGroup

    rgs = parsed.get("resource_groups") if isinstance(parsed, dict) else None
    declared = {}
    if isinstance(rgs, dict):
        for name, val in rgs.items():
            if not isinstance(name, str) or not name.strip():
                continue
            mc = val.get("max_concurrent") if isinstance(val, dict) else None
            declared[name.strip()] = mc if isinstance(mc, int) and mc >= 1 else 1
    existing = {g.name: g for g in provider.resource_groups.all()}
    for name, mc in declared.items():
        g = existing.get(name)
        if g is None:
            ResourceGroup.objects.create(provider=provider, name=name, max_concurrent=mc)
        elif g.max_concurrent != mc:
            g.max_concurrent = mc
            g.save(update_fields=["max_concurrent", "modified_on"])
    for name, g in existing.items():
        if name not in declared:
            g.delete()


def _host_gpus(host: dict) -> list[dict]:
    """Normalize a manifest host's GPU declaration into a flat list of
    ``{index, vendor, model, vram_gb}`` — one entry per physical device.

    Supports both shapes the codebase already produces: a singular ``gpu``
    object (``{vendor, vram_gb, count, model?}``) which expands to ``count``
    identical devices, and a ``gpus[]`` list (each ``{model?, vendor?, vram_gb?,
    index?}``), as emitted by the kubernetes-discovery agent path.
    """
    out: list[dict] = []
    raw_list = host.get("gpus")
    if isinstance(raw_list, list) and raw_list:
        for i, g in enumerate(raw_list):
            if isinstance(g, dict):
                idx = g.get("index")
                out.append({
                    "index": idx if isinstance(idx, int) else i,
                    "vendor": str(g.get("vendor") or ""),
                    "model": str(g.get("model") or ""),
                    "vram_gb": g.get("vram_gb") if isinstance(g.get("vram_gb"), (int, float)) else None,
                })
            elif g:
                out.append({"index": i, "vendor": "", "model": str(g), "vram_gb": None})
        return out
    gpu = host.get("gpu")
    if isinstance(gpu, dict):
        count = gpu.get("count", 1)
        count = count if isinstance(count, int) and count >= 1 else 1
        vram = gpu.get("vram_gb") if isinstance(gpu.get("vram_gb"), (int, float)) else None
        for i in range(count):
            out.append({
                "index": i,
                "vendor": str(gpu.get("vendor") or ""),
                "model": str(gpu.get("model") or ""),
                "vram_gb": vram,
            })
    elif isinstance(gpu, str) and gpu.strip():
        out.append({"index": 0, "vendor": "", "model": gpu.strip(), "vram_gb": None})
    return out


def _sync_hosts_and_gpus(provider, parsed) -> dict:
    """Mirror the manifest's ``hosts[]`` (and their GPUs) into Host + Gpu rows.

    Returns ``{host_id: Host}`` for the services sync to link against. Hosts /
    GPUs that vanish from the manifest are soft-deactivated (``is_active=False``)
    rather than deleted, so the generations that ran on them keep a stable home.
    """
    from .models import Gpu, Host

    hosts = parsed.get("hosts") if isinstance(parsed, dict) else None
    if not isinstance(hosts, list):
        hosts = []

    existing = {h.host_id: h for h in provider.hosts.all()}
    declared_ids: set[str] = set()
    result: dict[str, Host] = {}

    for h in hosts:
        if not isinstance(h, dict):
            continue
        hid = h.get("id")
        if not isinstance(hid, str) or not hid.strip():
            continue
        hid = hid.strip()
        declared_ids.add(hid)
        hostname = str(h.get("hostname") or "")
        address = str(h.get("address") or "")
        notes = str(h.get("notes") or "")

        host = existing.get(hid)
        if host is None:
            host = Host.objects.create(
                provider=provider, host_id=hid, hostname=hostname,
                address=address, notes=notes, is_active=True,
            )
        else:
            fields = []
            for attr, val in (("hostname", hostname), ("address", address),
                              ("notes", notes), ("is_active", True)):
                if getattr(host, attr) != val:
                    setattr(host, attr, val)
                    fields.append(attr)
            if fields:
                host.save(update_fields=fields + ["modified_on"])
        result[hid] = host

        # Upsert this host's GPUs by index; deactivate any beyond the declared set.
        gpus = _host_gpus(h)
        existing_gpus = {g.index: g for g in host.gpus.all()}
        declared_idx = set()
        for gd in gpus:
            declared_idx.add(gd["index"])
            g = existing_gpus.get(gd["index"])
            if g is None:
                Gpu.objects.create(host=host, **gd, is_active=True)
            else:
                fields = []
                for attr in ("vendor", "model", "vram_gb"):
                    if getattr(g, attr) != gd[attr]:
                        setattr(g, attr, gd[attr])
                        fields.append(attr)
                if not g.is_active:
                    g.is_active = True
                    fields.append("is_active")
                if fields:
                    g.save(update_fields=fields + ["modified_on"])
        for idx, g in existing_gpus.items():
            if idx not in declared_idx and g.is_active:
                g.is_active = False
                g.save(update_fields=["is_active", "modified_on"])

    # Soft-deactivate hosts no longer in the manifest (preserve for history).
    for hid, host in existing.items():
        if hid not in declared_ids and host.is_active:
            host.is_active = False
            host.save(update_fields=["is_active", "modified_on"])

    return result


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

    # Normalize hosts + GPUs first so services can link to a real Host row.
    hosts_by_id = _sync_hosts_and_gpus(provider, parsed)

    service_by_name: dict[str, ProviderService] = {}
    for sd in services_data:
        svc = existing_services.get(sd["name"])
        if svc is None:
            svc = ProviderService.objects.create(
                provider=provider,
                name=sd["name"],
                manifest_host_id=sd["host_id"],
                host=hosts_by_id.get(sd["host_id"]),
                engine=sd["engine"],
                service_type=sd["service_type"],
                declared_features=sd["features"],
                max_concurrent=sd["max_concurrent"],
                resource_group=sd["resource_group"],
                is_active=True,
            )
        else:
            fields = []
            if svc.manifest_host_id != sd["host_id"]:
                svc.manifest_host_id = sd["host_id"]
                fields.append("manifest_host_id")
            resolved_host = hosts_by_id.get(sd["host_id"])
            if svc.host_id != (resolved_host.id if resolved_host else None):
                svc.host = resolved_host
                fields.append("host")
            if svc.engine != sd["engine"]:
                svc.engine = sd["engine"]
                fields.append("engine")
            if svc.service_type != sd["service_type"]:
                svc.service_type = sd["service_type"]
                fields.append("service_type")
            if list(svc.declared_features or []) != sd["features"]:
                svc.declared_features = sd["features"]
                fields.append("declared_features")
            if svc.max_concurrent != sd["max_concurrent"]:
                svc.max_concurrent = sd["max_concurrent"]
                fields.append("max_concurrent")
            if svc.resource_group != sd["resource_group"]:
                svc.resource_group = sd["resource_group"]
                fields.append("resource_group")
            if not svc.is_active:
                svc.is_active = True
                fields.append("is_active")
            if fields:
                svc.save(update_fields=fields + ["modified_on"])
        service_by_name[sd["name"]] = svc

    _sync_resource_groups(provider, parsed)

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

    permission_classes = [IsFullMember]

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
            # Story-mode history (PRD 07 V3): append-only, deduped against
            # the previous revision so agent restarts don't spam rows.
            ManifestRevision.record(
                provider, manifest.parsed, schema_version=schema_version
            )

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


CLUSTER_STATE_CACHE_TTL = 12  # seconds — fresh enough for the ~20s live poll
# (so the client-side VRAM/util sparkline gets distinct samples, not cache dups)
CLUSTER_ACTIVITY_CACHE_TTL = 20  # seconds
CLUSTER_ACTIVITY_WINDOW_MIN = 60
CLUSTER_ACTIVITY_BUCKET_SEC = 60
CLUSTER_HISTORY_MAX_REVISIONS = 200


def _cluster_provider_or_404(request, provider_id, require_k8s=True):
    """Resolve a provider for the cluster endpoints (PRD 07), enforcing the
    shared access rule: public whenever the owner's profile is public — the
    cluster page is the profile's storefront — and always for the owner.
    With ``require_k8s`` the latest manifest must be kubernetes-derived
    (``discovery: kubernetes``); 404 otherwise."""
    provider = get_object_or_404(
        Provider.objects.select_related("user"), id=provider_id, is_active=True
    )
    is_owner = request.user.is_authenticated and provider.user_id == request.user.id
    if not is_owner and not provider.user.public_profile_enabled:
        raise Http404
    if require_k8s:
        manifest = getattr(provider, "manifest", None)
        parsed = manifest.parsed if manifest is not None and manifest.is_valid else None
        if not isinstance(parsed, dict) or parsed.get("discovery") != "kubernetes":
            raise Http404("provider's manifest is not kubernetes-derived")
    return provider


class ProviderHostDetailView(APIView):
    """GET /api/inference/providers/<id>/hosts/<host_id>/ — one node's specs,
    GPUs, the services running on it, and the generations made on it with stats.

    Public whenever the owner's profile is public (a node page is part of the
    cluster storefront); the owner additionally sees private recent rows and the
    LAN address. Works for static manifests too (``require_k8s=False``) — live
    VRAM/util is overlaid client-side from the separate ``/cluster/`` proxy."""

    permission_classes = [AllowAny]

    def get(self, request, id, host_id):
        from django.db.models import Avg, Count, Sum

        from .models import Host
        from .serializers import (
            InferenceProviderMiniSerializer,
            InferenceRequestListSerializer,
            ProviderServiceSerializer,
        )

        provider = _cluster_provider_or_404(request, id, require_k8s=False)
        host = get_object_or_404(Host, provider=provider, host_id=host_id)
        is_owner = request.user.is_authenticated and provider.user_id == request.user.id

        gpus = [
            {"index": g.index, "vendor": g.vendor, "model": g.model,
             "vram_gb": g.vram_gb, "is_active": g.is_active}
            for g in host.gpus.all().order_by("index")
        ]
        services = ProviderServiceSerializer(
            host.services.filter(is_active=True).prefetch_related("models"),
            many=True, context={"request": request},
        ).data

        on_host = InferenceRequest.objects.filter(host=host)
        agg = on_host.aggregate(
            total=Count("id"),
            avg_latency_ms=Avg("latency_ms"),
            total_completion_tokens=Sum("completion_tokens"),
        )
        by_modality = {
            r["inference_type"]: r["n"]
            for r in on_host.values("inference_type").annotate(n=Count("id"))
        }
        # Recent list respects per-viewer visibility (owner sees private rows).
        visible = (
            _annotate_viewer_flags(
                _requests_with_owner().filter(host=host).filter(
                    visible_list_q(request.user)
                ),
                request.user,
            )
            .order_by("-created_on")[:12]
        )
        recent = InferenceRequestListSerializer(
            visible, many=True, context={"request": request}
        ).data

        return Response({
            "host_id": host.host_id,
            "hostname": host.hostname,
            "address": host.address if is_owner else "",
            "notes": host.notes,
            "is_active": host.is_active,
            "is_owner": is_owner,
            "provider": InferenceProviderMiniSerializer(
                provider, context={"request": request}
            ).data,
            "gpus": gpus,
            "services": services,
            "stats": {
                "total": agg["total"] or 0,
                "avg_latency_ms": agg["avg_latency_ms"],
                "total_completion_tokens": agg["total_completion_tokens"] or 0,
                "by_modality": by_modality,
            },
            "recent": recent,
        })


class ProviderClusterStateView(APIView):
    """GET /api/inference/providers/<id>/cluster/ — live cluster snapshot.

    Proxies the agent's ``GET /cluster/state`` (node conditions, memory
    allocatable/usage, GPU allocatable, pod phases/restarts) for providers
    whose latest manifest is kubernetes-derived (``discovery: kubernetes``).
    A short server-side cache keeps a busy viz page from hammering the agent.
    """

    permission_classes = [AllowAny]

    def get(self, request, id):
        provider = _cluster_provider_or_404(request, id)
        if not provider.tailnet_hostname:
            return Response(
                {"detail": "provider has no reachable agent"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        cache_key = f"cluster_state:{provider.id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        url = (
            f"http://{provider.tailnet_hostname}:{provider.agent_port}/cluster/state"
        )
        try:
            upstream = requests.get(url, timeout=15, proxies=_tailnet_proxies())
            upstream.raise_for_status()
            payload = upstream.json()
        except (requests.RequestException, ValueError):
            logger.warning("cluster state fetch failed for provider %s", provider.id)
            return Response(
                {"detail": "agent did not return cluster state"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        cache.set(cache_key, payload, CLUSTER_STATE_CACHE_TTL)
        return Response(payload)


class ProviderClusterActivityView(APIView):
    """GET /api/inference/providers/<id>/cluster/activity/ — per-service
    request activity for the cluster scene (PRD 07 V1): the sparkline on the
    service card and the request pulses flowing into machines.

    Buckets the provider's served requests over the trailing hour into
    per-minute counts, grouped by the manifest service that serves each
    request's model (model_name → ProviderModel → ProviderService). Counts
    only — no prompt/response content, so it shares the public gating of the
    cluster state endpoint.
    """

    permission_classes = [AllowAny]

    def get(self, request, id):
        provider = _cluster_provider_or_404(request, id)

        cache_key = f"cluster_activity:{provider.id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        now = timezone.now()
        window = timedelta(minutes=CLUSTER_ACTIVITY_WINDOW_MIN)
        buckets_per_service = CLUSTER_ACTIVITY_WINDOW_MIN * 60 // CLUSTER_ACTIVITY_BUCKET_SEC

        service_by_model = {
            pm.name: pm.service.name
            for pm in ProviderModel.objects.filter(
                provider=provider, service__isnull=False
            ).select_related("service")
        }

        rows = InferenceRequest.objects.filter(
            provider=provider, created_on__gte=now - window
        ).values_list("model_name", "created_on")

        services: dict[str, dict] = {}
        for model_name, created_on in rows:
            service = service_by_model.get(model_name)
            if service is None:
                continue
            entry = services.setdefault(
                service,
                {
                    "service": service,
                    "total": 0,
                    "last_request_at": None,
                    "buckets": [0] * buckets_per_service,
                },
            )
            entry["total"] += 1
            if entry["last_request_at"] is None or created_on > entry["last_request_at"]:
                entry["last_request_at"] = created_on
            idx = int(
                (now - created_on).total_seconds() // CLUSTER_ACTIVITY_BUCKET_SEC
            )
            # buckets[0] is the oldest minute, buckets[-1] the current one.
            idx = buckets_per_service - 1 - min(max(idx, 0), buckets_per_service - 1)
            entry["buckets"][idx] += 1

        payload = {
            "window_minutes": CLUSTER_ACTIVITY_WINDOW_MIN,
            "bucket_seconds": CLUSTER_ACTIVITY_BUCKET_SEC,
            "generated_at": now.isoformat(),
            "services": sorted(services.values(), key=lambda s: s["service"]),
        }
        cache.set(cache_key, payload, CLUSTER_ACTIVITY_CACHE_TTL)
        return Response(payload)


class ProviderClusterHistoryView(APIView):
    """GET /api/inference/providers/<id>/cluster/history/ — manifest
    revisions for story mode (PRD 07 V3): scrub through how the cluster grew
    from the first Service to the full fleet.

    Returns a chronological index (id, uploaded_at, host/service counts) of
    the most recent revisions; the parsed manifest of one revision comes from
    the detail endpoint. ``require_k8s`` matches the other cluster endpoints:
    story mode is part of the cluster page.
    """

    permission_classes = [AllowAny]

    def get(self, request, id):
        provider = _cluster_provider_or_404(request, id)
        revisions = list(
            ManifestRevision.objects.filter(provider=provider)
            .order_by("-uploaded_at")[:CLUSTER_HISTORY_MAX_REVISIONS]
        )
        revisions.reverse()

        def counts(parsed):
            hosts = parsed.get("hosts") or [] if isinstance(parsed, dict) else []
            services = sum(
                len(h.get("services") or [])
                for h in hosts
                if isinstance(h, dict)
            )
            return len(hosts), services

        out = []
        for rev in revisions:
            host_count, service_count = counts(rev.parsed)
            out.append(
                {
                    "id": rev.id,
                    "uploaded_at": rev.uploaded_at,
                    "host_count": host_count,
                    "service_count": service_count,
                }
            )
        return Response({"revisions": out})


class ProviderClusterRevisionView(APIView):
    """GET /api/inference/providers/<id>/cluster/history/<rev_id>/ — one
    revision's parsed manifest, for rendering the scene as of that moment."""

    permission_classes = [AllowAny]

    def get(self, request, id, rev_id):
        provider = _cluster_provider_or_404(request, id)
        rev = get_object_or_404(ManifestRevision, id=rev_id, provider=provider)
        return Response(
            {
                "id": rev.id,
                "uploaded_at": rev.uploaded_at,
                "schema_version": rev.schema_version,
                "parsed": rev.parsed,
            }
        )


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


def _user_by_handle(handle):
    """Return ``(user, github_data)`` for a public handle (case-insensitive),
    or ``(None, None)`` if no such user.

    ``handle`` is the canonical public identity (PRD 08): the GitHub login for
    non-aliased GitHub users, a generated slug for aliased/anonymous accounts.
    ``github_data`` is the GitHub social_auth extra_data ONLY when the profile
    may show it (GitHub account, alias mode off) — for aliased and anonymous
    accounts it's ``{}`` so nothing public can leak the GitHub identity.
    """
    User = get_user_model()
    user = (
        User.objects.filter(handle__iexact=(handle or ""))
        .prefetch_related(
            "social_auth",
            "providers__models",
            "providers__manifest",
        )
        .first()
    )
    if user is None:
        return None, None
    github_data = {}
    if user.account_type == User.AccountType.GITHUB and not user.use_anon_alias:
        for sa in user.social_auth.all():
            if sa.provider == "github":
                github_data = sa.extra_data or {}
                break
    return user, github_data


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
    """GET /api/users/<handle>/ — unauthenticated public profile.

    Returns display info, the models this user serves (with capabilities), and
    active providers with their (parsed-only) manifests. The raw YAML is never
    exposed here.

    ``account_badge`` tells the UI the provenance to show: ``github`` (a
    GitHub-verified account — icon only, never a link when aliased) or
    ``anonymous`` (guest/passcode/aliased). GitHub name/avatar/url are only
    emitted for non-aliased GitHub accounts; the GitHub avatar URL is itself
    reverse-searchable, so aliased users get none and the UI renders an
    identicon from the handle.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, handle):
        user, github_data = _user_by_handle(handle)
        if user is None or not user.public_profile_enabled:
            return Response(
                {"detail": f"no public profile for {handle!r}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_github_account = (
            user.account_type
            == get_user_model().AccountType.GITHUB
        )
        providers_qs = user.providers.filter(is_active=True)
        return Response(
            {
                "handle": user.handle,
                # Legacy key — the frontend used it as the profile slug
                # everywhere; it now always carries the canonical handle.
                "github_login": user.handle,
                "name": github_data.get("name")
                or github_data.get("login")
                or user.handle,
                "avatar_url": github_data.get("avatar_url") or "",
                "github_url": (
                    f"https://github.com/{github_data.get('login')}"
                    if github_data.get("login")
                    else ""
                ),
                "account_badge": (
                    "github"
                    if is_github_account
                    else "anonymous"
                ),
                "is_anonymous_account": user.is_anonymous_account,
                "joined": user.date_joined,
                "models": _user_served_models(user),
                "providers": PublicProviderSerializer(
                    providers_qs, many=True, context={"request": request}
                ).data,
                "stats": _profile_stats(user),
            }
        )


class PublicUserRequestsView(generics.ListAPIView):
    """GET /api/users/<handle>/requests/ — unauthenticated, paginated
    list of a user's inference requests for their public profile.

    ``?scope=consumed`` (default) = requests this user made; ``?scope=served``
    = requests this user's nodes served to others; ``?scope=bookmarked`` =
    requests this user has bookmarked onto their profile. Only PUBLIC requests
    are listed (UNLISTED/PRIVATE/SECRET never surface publicly), with one
    deliberate exception: an *anonymous account's* own consumed items include
    UNLISTED — those accounts can't publish publicly, their random handle is
    itself the unguessable share token, and nothing links to the page, so the
    profile acts as their "unlisted public profile" (PRD 08). ``is_owner`` is
    always False here (anonymous), so no delete affordance is exposed.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    pagination_class = StandardResultsSetPagination
    serializer_class = InferenceRequestListSerializer

    def get_queryset(self):
        user, _ = _user_by_handle(self.kwargs["handle"])
        if user is None or not user.public_profile_enabled:
            raise Http404("no such profile")
        scope = self.request.query_params.get("scope")
        qs = _requests_with_owner()
        allowed = [VISIBILITY_PUBLIC]
        if scope == "served":
            qs = qs.filter(provider__user=user)
        elif scope == "bookmarked":
            bookmarked_ids = Bookmark.objects.filter(user=user).values_list(
                "request_id", flat=True
            )
            qs = qs.filter(id__in=list(bookmarked_ids))
        else:
            qs = qs.filter(user=user)
            if user.is_anonymous_account:
                from .models import VISIBILITY_UNLISTED

                allowed.append(VISIBILITY_UNLISTED)
        qs = qs.filter(visibility__in=allowed)
        return _apply_request_filters(qs, self.request.query_params)


# --- Collections ---------------------------------------------------------


def _existing_collection_by_name(user, name, exclude=None):
    """The user's collection with this name, case-insensitively (names are the
    API's unique per-user handle). Oldest wins under legacy duplicates."""
    qs = Collection.objects.filter(user=user, name__iexact=name)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.order_by("created_on").first()


def _collections_annotated(qs):
    """Collection list queryset with the counts the UI needs to pick playback
    affordances (Play as music playlist / video playlist) without fetching
    items: total items, per-modality counts, and total music runtime."""
    return (
        qs.annotate(
            item_count=Count("items"),
            audio_count=Count(
                "items", filter=Q(items__request__inference_type="MUSIC")
            ),
            video_count=Count(
                "items", filter=Q(items__request__inference_type="VIDEO")
            ),
            total_audio_seconds=Sum(
                "items__request__audio_seconds",
                filter=Q(items__request__inference_type="MUSIC"),
            ),
            # Popularity proxy for "albums": summed star_count of member songs.
            star_total=Coalesce(Sum("items__request__star_count"), 0),
        )
        .select_related("cover_request")
        .prefetch_related("cover_request__assets")
    )


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


def _resolve_cover_request(request, raw_id):
    """Validate a ``cover_request_id`` value: ``None`` clears the cover;
    otherwise it must be the caller's own IMAGE request with a generated
    OUTPUT_IMAGE. Returns ``(cover_or_None, error_response_or_None)``."""
    if raw_id is None:
        return None, None
    if not isinstance(raw_id, int):
        return None, Response(
            {"detail": "cover_request_id must be an integer or null."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    cover = InferenceRequest.objects.filter(id=raw_id, user=request.user).first()
    if cover is None:
        raise Http404("no such inference request")
    if cover.inference_type != "IMAGE" or not any(
        a.kind == MediaAsset.OUTPUT_IMAGE for a in cover.assets.all()
    ):
        return None, Response(
            {"detail": "Cover must be an IMAGE request with a generated image."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return cover, None


class RequestCoverView(APIView):
    """PATCH /api/inference/requests/<id>/cover/ — set or clear a request's
    cover art (owner only). Body: ``{"cover_request_id": <id> | null}``."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, id):
        obj = get_object_or_404(InferenceRequest, id=id, user=request.user)
        if "cover_request_id" not in request.data:
            return Response(
                {"detail": "cover_request_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cover, error = _resolve_cover_request(request, request.data["cover_request_id"])
        if error is not None:
            return error
        if cover is not None and cover.id == obj.id:
            return Response(
                {"detail": "A request cannot be its own cover."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.cover_request = cover
        obj.save(update_fields=["cover_request"])
        return Response({"cover_image_url": _cover_image_url(obj, request)})


class CollectionListCreateView(generics.ListCreateAPIView):
    """GET lists the caller's collections; POST get-or-creates one by name
    (names are unique per user, case-insensitive; slug derived from the name).
    An existing name returns that collection with 200 instead of a duplicate."""

    permission_classes = [IsAuthenticated]
    serializer_class = CollectionSerializer

    def get_queryset(self):
        return _collections_annotated(
            Collection.objects.filter(user=self.request.user)
        )

    def create(self, request, *args, **kwargs):
        ser = CollectionWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        existing = _existing_collection_by_name(request.user, ser.validated_data["name"])
        if existing is not None:
            return Response(
                CollectionSerializer(existing, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )
        slug = unique_collection_slug(request.user, ser.validated_data["name"])
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
        new_name = ser.validated_data.get("name")
        if new_name and _existing_collection_by_name(request.user, new_name, exclude=col):
            return Response(
                {"detail": "You already have a collection with this name."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if "cover_request_id" in request.data:
            cover, error = _resolve_cover_request(
                request, request.data["cover_request_id"]
            )
            if error is not None:
                return error
            col.cover_request = cover
        ser.save()
        return Response(CollectionSerializer(col, context={"request": request}).data)

    def delete(self, request, slug):
        self._get(request, slug).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CollectionItemView(APIView):
    """POST/DELETE /api/inference/collections/<slug>/items/<request_id>/ — add
    or remove a request from one of the caller's collections. Adds append at
    the end of the playlist order."""

    permission_classes = [IsAuthenticated]

    def post(self, request, slug, request_id):
        col = get_object_or_404(Collection, user=request.user, slug=slug)
        ir = _get_owned_or_visible_request(request, request_id)
        with transaction.atomic():
            next_pos = (
                col.items.aggregate(max_pos=Max("position"))["max_pos"] or 0
            ) + 1
            CollectionItem.objects.get_or_create(
                collection=col, request=ir, defaults={"position": next_pos}
            )
        return Response({"in_collection": True})

    def delete(self, request, slug, request_id):
        col = get_object_or_404(Collection, user=request.user, slug=slug)
        CollectionItem.objects.filter(collection=col, request_id=request_id).delete()
        return Response({"in_collection": False})


class CollectionOrderView(APIView):
    """PUT /api/inference/collections/<slug>/items/order/ — replace the
    playlist order with ``{"request_ids": [...]}``. Ids omitted from the body
    keep their relative order after the listed ones, so a partial list never
    loses items."""

    permission_classes = [IsAuthenticated]

    def put(self, request, slug):
        col = get_object_or_404(Collection, user=request.user, slug=slug)
        ids = request.data.get("request_ids")
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            return Response(
                {"detail": "request_ids must be a list of integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            items = list(col.items.select_for_update())
            by_request_id = {it.request_id: it for it in items}
            seen: set[int] = set()
            ordered = []
            for rid in ids:
                it = by_request_id.get(rid)
                if it is not None and rid not in seen:
                    seen.add(rid)
                    ordered.append(it)
            ordered += [it for it in items if it.request_id not in seen]
            changed = []
            for pos, it in enumerate(ordered):
                if it.position != pos:
                    it.position = pos
                    changed.append(it)
            if changed:
                CollectionItem.objects.bulk_update(changed, ["position"])
        return Response(_collection_with_items(col, request))


# --- Voice cloning: the voice-sample library (PRD 09) ------------------------


class VoiceSampleListCreateView(generics.ListCreateAPIView):
    """GET lists the caller's voice samples (the frontend groups them by
    speaker); POST creates one from an uploaded audio file (multipart). When no
    transcript is supplied we auto-fill it via the caller's own STT service —
    Dia needs a transcript to clone."""

    permission_classes = [IsAuthenticated]
    serializer_class = VoiceSampleSerializer

    def get_queryset(self):
        return VoiceSample.objects.filter(user=self.request.user).select_related("audio")

    def create(self, request, *args, **kwargs):
        from django.core.files.base import ContentFile

        from .openai_views import transcribe_audio_bytes, _wav_seconds

        upload = request.FILES.get("audio")
        if upload is None:
            return Response(
                {"detail": "`audio` file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size and upload.size > settings.STT_MAX_UPLOAD_BYTES:
            return Response(
                {"detail": "Audio file too large."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        ser = VoiceSampleWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        speaker_name = (data.get("speaker_name") or "Speaker").strip()
        audio_bytes = upload.read()
        ctype = (getattr(upload, "content_type", "") or "").split(";", 1)[0]

        asset = MediaAsset(
            user=request.user,
            kind=MediaAsset.INPUT_AUDIO,
            content_type=ctype,
            size_bytes=len(audio_bytes),
            duration_seconds=_wav_seconds(audio_bytes),
        )
        asset.file.save(
            getattr(upload, "name", "sample") or "sample",
            ContentFile(audio_bytes),
            save=False,
        )
        asset.save()

        transcript = (data.get("transcript") or "").strip()
        source = VoiceSample.SOURCE_MANUAL
        if not transcript:
            text, _err = transcribe_audio_bytes(
                request.user,
                audio_bytes,
                filename=getattr(upload, "name", "sample.wav") or "sample.wav",
                content_type=ctype or "audio/wav",
            )
            if text:
                transcript, source = text, VoiceSample.SOURCE_STT

        make_default = bool(data.get("is_default"))
        with transaction.atomic():
            existing = VoiceSample.objects.filter(
                user=request.user, speaker_name=speaker_name
            )
            # The first sample for a speaker is implicitly its default.
            if make_default or not existing.exists():
                make_default = True
                existing.filter(is_default=True).update(is_default=False)
            sample = VoiceSample.objects.create(
                user=request.user,
                speaker_name=speaker_name,
                label=(data.get("label") or "").strip(),
                is_default=make_default,
                audio=asset,
                transcript=transcript,
                transcript_source=source,
                language=(data.get("language") or "").strip(),
                duration_seconds=asset.duration_seconds,
            )
        return Response(
            VoiceSampleSerializer(sample, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class VoiceSampleDetailView(APIView):
    """GET / PATCH / DELETE one of the caller's voice samples. PATCH can edit
    the transcript/label/language/speaker, or promote the sample to be its
    speaker's default."""

    permission_classes = [IsAuthenticated]

    def _get(self, request, id):
        return get_object_or_404(
            VoiceSample.objects.select_related("audio"), id=id, user=request.user
        )

    def get(self, request, id):
        return Response(
            VoiceSampleSerializer(
                self._get(request, id), context={"request": request}
            ).data
        )

    def patch(self, request, id):
        sample = self._get(request, id)
        ser = VoiceSampleWriteSerializer(sample, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        with transaction.atomic():
            if "transcript" in data:
                sample.transcript = (data["transcript"] or "").strip()
                sample.transcript_source = VoiceSample.SOURCE_EDITED
            if "label" in data:
                sample.label = (data["label"] or "").strip()
            if "language" in data:
                sample.language = (data["language"] or "").strip()
            if data.get("speaker_name"):
                sample.speaker_name = data["speaker_name"].strip()
            if data.get("is_default"):
                VoiceSample.objects.filter(
                    user=request.user,
                    speaker_name=sample.speaker_name,
                    is_default=True,
                ).exclude(id=sample.id).update(is_default=False)
                sample.is_default = True
            sample.save()
        return Response(
            VoiceSampleSerializer(sample, context={"request": request}).data
        )

    def delete(self, request, id):
        sample = self._get(request, id)
        was_default, speaker, asset = sample.is_default, sample.speaker_name, sample.audio
        sample.delete()
        # The audio FK is CASCADE the other way (asset → sample), so removing
        # the sample leaves the private blob — drop it explicitly.
        try:
            asset.delete()
        except Exception:
            pass
        # If we removed the default, promote the most recent remaining sample.
        if was_default:
            nxt = (
                VoiceSample.objects.filter(user=request.user, speaker_name=speaker)
                .order_by("-created_on")
                .first()
            )
            if nxt is not None:
                VoiceSample.objects.filter(id=nxt.id).update(is_default=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


class VoiceSampleTranscribeView(APIView):
    """POST /api/inference/voice-samples/<id>/transcribe/ — (re)run STT on the
    sample's audio and store the text."""

    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        from .openai_views import transcribe_audio_bytes, _read_asset_bytes

        sample = get_object_or_404(
            VoiceSample.objects.select_related("audio"), id=id, user=request.user
        )
        audio_bytes = _read_asset_bytes(sample.audio)
        text, err = transcribe_audio_bytes(
            request.user,
            audio_bytes,
            content_type=sample.audio.content_type or "audio/wav",
            model_name=request.data.get("model"),
        )
        if not text:
            return Response(
                {"detail": f"Transcription unavailable ({err})."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        sample.transcript = text
        sample.transcript_source = VoiceSample.SOURCE_STT
        sample.save(update_fields=["transcript", "transcript_source", "modified_on"])
        return Response(
            VoiceSampleSerializer(sample, context={"request": request}).data
        )


class PublicUserCollectionsView(APIView):
    """GET /api/users/<handle>/collections/ — the user's PUBLIC
    collections, for their profile. 404 when the profile is disabled."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, handle):
        user, _ = _user_by_handle(handle)
        if user is None or not user.public_profile_enabled:
            raise Http404("no such profile")
        cols = _collections_annotated(
            Collection.objects.filter(user=user, visibility=VISIBILITY_PUBLIC)
        )
        return Response(
            CollectionSerializer(cols, many=True, context={"request": request}).data
        )


class PublicCollectionDetailView(APIView):
    """GET /api/users/<handle>/collections/<slug>/ — a PUBLIC collection +
    its publicly-visible items."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, handle, slug):
        user, _ = _user_by_handle(handle)
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
    """``GET /api/inference/assets/<id>/`` — serve a stored media asset.

    Public kinds on GCS 302 to the public bucket; everything else (private
    input audio, or any kind on MinIO/local disk) streams through the app so
    one URL shape works across storage backends and the owner gate applies.
    """

    permission_classes = [AllowAny]

    def get(self, request, id):
        from django.conf import settings
        from django.http import FileResponse, HttpResponseRedirect

        asset = get_object_or_404(MediaAsset, id=id)
        if asset.kind not in MediaAsset.PUBLIC_KINDS:
            if not request.user.is_authenticated or asset.user_id != request.user.id:
                raise PermissionDenied("Not your asset.")
        # Public assets on GCS: send the browser to the bucket instead of
        # streaming the bytes ourselves. Kept (rather than changing every
        # caller) so pre-GCS URLs in shared links keep working. The asset's
        # key never changes, so the redirect itself is immutable-cacheable.
        if asset.kind in MediaAsset.PUBLIC_KINDS and settings.MEDIA_DIRECT_PUBLIC_URLS:
            resp = HttpResponseRedirect(asset.file.url)
            resp["Cache-Control"] = "public, max-age=31536000, immutable"
            return resp
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
