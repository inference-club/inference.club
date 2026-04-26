"""OpenAI-compatible endpoints under /v1/.

These views authenticate the user by Bearer API key, find a matching online
provider, and proxy the request to that provider's agent. Streaming responses
are passed through unchanged so OpenAI SDK clients can stream as usual.
"""
import json
import logging
import time

import requests
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import InferenceRequest, Provider, ProviderModel
from .views import _tailnet_proxies, refresh_provider_models

logger = logging.getLogger("django")

# Per-request budget for the upstream call. LLM responses can be slow; this is
# generous but bounded so a hung agent doesn't pin a worker forever.
UPSTREAM_TIMEOUT_SECONDS = 300


def _online_providers(user):
    return [
        p
        for p in user.providers.filter(is_active=True).exclude(tailnet_hostname="")
        if p.is_online
    ]


def _find_provider_for_model(user, model_name):
    """Pick the first online provider serving ``model_name``.

    MVP routing: no load balancing, no fallback. If a provider has no models
    cached yet (just registered), we'll do a synchronous discovery before
    giving up — saves the user from clicking "refresh models" the first time.
    """
    if not model_name:
        return None
    pm = (
        ProviderModel.objects.filter(
            name=model_name,
            is_active=True,
            provider__user=user,
            provider__is_active=True,
        )
        .exclude(provider__tailnet_hostname="")
        .select_related("provider")
        .first()
    )
    if pm and pm.provider.is_online:
        return pm.provider

    # Self-healing: if the user has online providers with no models cached,
    # try to populate them now. Useful right after a fresh agent registers.
    for provider in _online_providers(user):
        if not provider.models.filter(is_active=True).exists():
            try:
                refresh_provider_models(provider)
            except Exception:
                continue
            if provider.models.filter(is_active=True, name=model_name).exists():
                return provider
    return None


class ModelsView(APIView):
    """``GET /v1/models`` — OpenAI-format list across the user's online providers."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        seen = {}
        for provider in _online_providers(request.user):
            created = int(provider.created_on.timestamp())
            for m in provider.models.filter(is_active=True):
                # De-dupe across providers; first writer wins.
                seen.setdefault(
                    m.name,
                    {
                        "id": m.name,
                        "object": "model",
                        "created": created,
                        "owned_by": provider.name,
                    },
                )
        return Response({"object": "list", "data": list(seen.values())})


class _ChatOrCompletionsProxy(APIView):
    """Shared proxy logic for /v1/chat/completions and /v1/completions."""

    permission_classes = [IsAuthenticated]
    upstream_path = ""  # set by subclass
    inference_type = ""  # set by subclass

    def post(self, request):
        body = request.data
        model_name = body.get("model")
        provider = _find_provider_for_model(request.user, model_name)
        if provider is None:
            return Response(
                {
                    "error": {
                        "message": (
                            f"No online provider serving model '{model_name}' "
                            "for this user."
                        ),
                        "type": "no_provider",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        endpoint = provider.tailnet_base_url.rstrip("/") + self.upstream_path
        stream = bool(body.get("stream"))
        ir = InferenceRequest.objects.create(
            user=request.user,
            provider=provider,
            model_name=model_name or "",
            inference_type=self.inference_type,
            payload=body,
            status="PROCESSING",
        )
        started = time.monotonic()

        try:
            # verify=False because tailnet HTTPS uses a Tailscale-issued cert
            # bound to the device's full *.ts.net hostname, and we may proxy
            # by the short MagicDNS name. The wire is encrypted by WireGuard.
            upstream = requests.post(
                endpoint,
                json=body,
                stream=stream,
                timeout=UPSTREAM_TIMEOUT_SECONDS,
                verify=False,
                proxies=_tailnet_proxies(),
            )
        except requests.RequestException as e:
            ir.status = "REQUESTED"
            ir.results = {"error": str(e)}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            logger.error("Upstream request failed: %s", e)
            return Response(
                {"error": {"message": str(e), "type": "upstream_error"}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not upstream.ok:
            # Pass through the upstream error body so the OpenAI client sees
            # a useful message.
            ir.status = "REQUESTED"
            ir.results = {"upstream_status": upstream.status_code}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            return Response(
                upstream.json() if upstream.headers.get("content-type", "").startswith("application/json") else {"error": upstream.text},
                status=upstream.status_code,
            )

        if stream:
            return self._stream_response(upstream, ir, started)
        return self._buffered_response(upstream, ir, started)

    def _buffered_response(self, upstream, ir, started):
        try:
            data = upstream.json()
        except ValueError:
            data = {"raw": upstream.text}
        ir.status = "PROCESSED"
        ir.results = data
        ir.latency_ms = int((time.monotonic() - started) * 1000)
        ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
        Provider.objects.filter(id=ir.provider_id).update(last_seen_at=timezone.now())
        return Response(data, status=upstream.status_code)

    def _stream_response(self, upstream, ir, started):
        chunks = []

        def gen():
            try:
                for chunk in upstream.iter_content(chunk_size=8192):
                    if chunk:
                        chunks.append(chunk)
                        yield chunk
            finally:
                ir.status = "PROCESSED"
                ir.results = {"streamed": True, "bytes": sum(len(c) for c in chunks)}
                ir.latency_ms = int((time.monotonic() - started) * 1000)
                ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
                Provider.objects.filter(id=ir.provider_id).update(
                    last_seen_at=timezone.now()
                )

        resp = StreamingHttpResponse(
            gen(),
            content_type=upstream.headers.get("content-type", "text/event-stream"),
            status=upstream.status_code,
        )
        resp["Cache-Control"] = "no-cache"
        # Tell intermediaries (nginx, etc.) not to buffer the SSE stream.
        resp["X-Accel-Buffering"] = "no"
        return resp


class ChatCompletionsView(_ChatOrCompletionsProxy):
    upstream_path = "/chat/completions"
    inference_type = "LLM"


class CompletionsView(_ChatOrCompletionsProxy):
    upstream_path = "/completions"
    inference_type = "LLM"
