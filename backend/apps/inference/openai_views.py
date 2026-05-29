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

from .models import (
    PROVIDER_LAST_SEEN_WINDOW,
    InferenceRequest,
    Provider,
    ProviderModel,
)
from .serializers import _user_github_login
from .views import _tailnet_proxies, refresh_provider_models

logger = logging.getLogger("django")

# Per-request budget for the upstream call. LLM responses can be slow; this is
# generous but bounded so a hung agent doesn't pin a worker forever.
UPSTREAM_TIMEOUT_SECONDS = 300


def _assemble_streamed_results(chunks, fallback_model):
    """Reconstruct an OpenAI-style result object from raw SSE stream bytes.

    A streamed response only passes through as opaque bytes, so to display it
    later we parse the ``data:`` SSE lines here: concatenate the per-token
    deltas into the full message and capture usage / model / finish_reason
    when present. The shape deliberately mirrors a buffered (non-streamed)
    response — ``choices[0].message.content`` (+ ``usage``) — so the dashboard
    renders both identically. ``usage`` is only available when the client
    requested ``stream_options.include_usage``.
    """
    text_parts = []
    reasoning_parts = []
    usage = None
    model = fallback_model or ""
    finish_reason = None
    role = "assistant"
    is_completions = False

    raw = b"".join(chunks).decode("utf-8", errors="replace")
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if not data or data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
        except ValueError:
            continue
        if isinstance(obj.get("model"), str):
            model = obj["model"]
        if isinstance(obj.get("usage"), dict):
            usage = obj["usage"]
        for ch in obj.get("choices") or []:
            if not isinstance(ch, dict):
                continue
            delta = ch.get("delta")
            if isinstance(delta, dict):
                if isinstance(delta.get("content"), str):
                    text_parts.append(delta["content"])
                # Reasoning models stream their thinking trace in a separate
                # field (vLLM/SGLang: reasoning_content; OpenRouter/Nemotron:
                # reasoning) alongside the answer in content.
                for rk in ("reasoning", "reasoning_content"):
                    if isinstance(delta.get(rk), str):
                        reasoning_parts.append(delta[rk])
                if isinstance(delta.get("role"), str):
                    role = delta["role"]
            elif isinstance(ch.get("text"), str):  # legacy completions stream
                is_completions = True
                text_parts.append(ch["text"])
            if ch.get("finish_reason"):
                finish_reason = ch["finish_reason"]

    content = "".join(text_parts)
    reasoning = "".join(reasoning_parts)
    if is_completions:
        choice = {"index": 0, "text": content, "finish_reason": finish_reason}
        obj_type = "text_completion"
    else:
        message = {"role": role, "content": content}
        if reasoning:
            message["reasoning"] = reasoning
        choice = {
            "index": 0,
            "message": message,
            "finish_reason": finish_reason,
        }
        obj_type = "chat.completion"

    results = {
        "streamed": True,
        "object": obj_type,
        "model": model,
        "choices": [choice],
        "_bytes": sum(len(c) for c in chunks),
    }
    if usage:
        results["usage"] = usage
    return results


def _online_providers(user):
    return [
        p
        for p in user.providers.filter(is_active=True).exclude(tailnet_hostname="")
        if p.is_online
    ]


def _model_accessible(pm, user, github_login) -> bool:
    """Whether the requesting user may route to this ProviderModel.

    Own models are always usable. Otherwise the model must be mapped to a
    service whose access policy grants this user. Models with no service (e.g.
    discovered only via live /v1/models) stay owner-only.
    """
    if pm.provider.user_id == user.id:
        return True
    if pm.service_id is None:
        return False
    return pm.service.grants_access_to(user, github_login)


def _find_provider_for_model(user, model_name):
    """Pick the first online provider serving ``model_name`` that ``user`` is
    allowed to use — their own node, or someone else's shared service.

    MVP routing: no load balancing. Own providers get a self-healing model
    refresh if they registered but haven't reported models yet.
    """
    if not model_name:
        return None

    github_login = _user_github_login(user)
    candidates = (
        ProviderModel.objects.filter(
            name=model_name,
            is_active=True,
            provider__is_active=True,
        )
        .exclude(provider__tailnet_hostname="")
        .select_related("provider", "service")
    )
    for pm in candidates:
        if _model_accessible(pm, user, github_login) and pm.provider.is_online:
            return pm.provider

    # Self-healing for the user's OWN providers: if one just registered and
    # hasn't reported models yet, discover now.
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
    """``GET /v1/models`` — OpenAI-format list of every model the requesting
    user may use: their own providers' models, plus shared services elsewhere
    on the network they have access to.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        seen = {}

        # 1) The user's own providers (with self-healing model discovery so a
        # freshly-registered or idle node still populates the dropdown).
        own = list(
            request.user.providers.filter(is_active=True).exclude(tailnet_hostname="")
        )
        for provider in own:
            if not provider.is_online or not provider.models.filter(is_active=True).exists():
                try:
                    refresh_provider_models(provider)
                    provider.refresh_from_db(fields=["last_seen_at"])
                except Exception:
                    continue
            if not provider.is_online:
                continue
            created = int(provider.created_on.timestamp())
            for m in provider.models.filter(is_active=True):
                seen.setdefault(
                    m.name,
                    {
                        "id": m.name,
                        "object": "model",
                        "created": created,
                        "owned_by": provider.name,
                    },
                )

        # 2) Shared models from other members' services the user can access.
        # Bound to recently-seen providers so we don't probe; access is checked
        # per service in Python.
        github_login = _user_github_login(request.user)
        cutoff = timezone.now() - PROVIDER_LAST_SEEN_WINDOW
        shared = (
            ProviderModel.objects.filter(
                is_active=True,
                provider__is_active=True,
                provider__last_seen_at__gte=cutoff,
                service__isnull=False,
            )
            .exclude(provider__tailnet_hostname="")
            .exclude(provider__user=request.user)
            .select_related("provider", "service")
        )
        for pm in shared:
            if pm.name in seen:
                continue
            if pm.service.grants_access_to(request.user, github_login):
                seen[pm.name] = {
                    "id": pm.name,
                    "object": "model",
                    "created": int(pm.provider.created_on.timestamp()),
                    "owned_by": pm.provider.name,
                }
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
                ir.results = _assemble_streamed_results(chunks, ir.model_name)
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
