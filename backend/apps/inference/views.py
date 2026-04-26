import logging

import requests
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import InferenceRequest, Provider, ProviderModel
from .pagination import StandardResultsSetPagination
from .serializers import (
    AgentRegisterSerializer,
    InferenceRequestSerializer,
    ProviderSerializer,
)
from .tailscale import mint_authkey_for_provider

logger = logging.getLogger("django")


class InferenceRequestView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InferenceRequestSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return InferenceRequest.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class RetrieveInferenceRequestView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InferenceRequestSerializer
    lookup_field = "id"

    def get_queryset(self):
        return InferenceRequest.objects.filter(user=self.request.user)


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

        # Force a deterministic per-provider hostname so two agents from the
        # same user can't collide in the tailnet.
        canonical = f"club-host-{provider.id}"
        if provider.tailnet_hostname != canonical:
            provider.tailnet_hostname = canonical
            provider.save(update_fields=["tailnet_hostname", "modified_on"])

        minted = mint_authkey_for_provider(provider)

        return Response(
            {
                "provider_id": provider.id,
                "tailscale_authkey": minted.authkey,
                "tailscale_login_server": minted.login_server,
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


def refresh_provider_models(provider) -> int:
    """Hit the agent's /v1/models over the tailnet and sync ProviderModel rows.

    Returns the count of models the agent currently advertises. Raises
    RefreshError with diagnostic detail on transport failure so the calling
    view can surface it (only in non-prod / for the MVP debugging period).
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

    for name, pm in existing.items():
        if name not in incoming and pm.is_active:
            pm.is_active = False
            pm.save(update_fields=["is_active", "modified_on"])
    for name in incoming:
        ProviderModel.objects.update_or_create(
            provider=provider, name=name, defaults={"is_active": True}
        )
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
        return Response(
            {
                "refreshed": count,
                "error": error,
                "provider": ProviderSerializer(provider).data,
            }
        )
