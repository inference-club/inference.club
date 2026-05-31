"""OpenAI-compatible endpoints under /v1/.

These views authenticate the user by Bearer API key, find a matching online
provider, and proxy the request to that provider's agent. Streaming responses
are passed through unchanged so OpenAI SDK clients can stream as usual.
"""
import json
import logging
import time

import requests
from django.conf import settings
from django.db.models import Q
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import (
    PROVIDER_LAST_SEEN_WINDOW,
    InferenceRequest,
    Provider,
    ProviderModel,
    slugify_model_id,
)
from .serializers import _user_github_login
from .views import _tailnet_proxies, refresh_provider_models, scope_usage

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


def _usage_tokens(results):
    """(prompt, completion, total) token counts from a result's ``usage``,
    or (None, None, None) when the provider didn't report them."""
    usage = results.get("usage") if isinstance(results, dict) else None
    if not isinstance(usage, dict):
        return None, None, None

    def _i(v):
        return v if isinstance(v, int) and v >= 0 else None

    prompt, completion, total = (
        _i(usage.get("prompt_tokens")),
        _i(usage.get("completion_tokens")),
        _i(usage.get("total_tokens")),
    )
    if total is None and (prompt is not None or completion is not None):
        total = (prompt or 0) + (completion or 0)
    return prompt, completion, total


def _content_len(content) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(
            len(p["text"])
            for p in content
            if isinstance(p, dict) and isinstance(p.get("text"), str)
        )
    return 0


def _request_too_large(body) -> str | None:
    """Guardrail against oversized jobs that could pin or OOM a provider's
    hardware. Returns an error message, or None if the request is within
    bounds."""
    msgs = body.get("messages")
    total_chars = 0
    if isinstance(msgs, list):
        if len(msgs) > settings.INFERENCE_MAX_MESSAGES:
            return (
                f"Too many messages: {len(msgs)} (max "
                f"{settings.INFERENCE_MAX_MESSAGES})."
            )
        for m in msgs:
            if isinstance(m, dict):
                total_chars += _content_len(m.get("content"))
    prompt = body.get("prompt")
    if isinstance(prompt, str):
        total_chars += len(prompt)
    elif isinstance(prompt, list):
        total_chars += sum(len(p) for p in prompt if isinstance(p, str))
    if total_chars > settings.INFERENCE_MAX_INPUT_CHARS:
        return (
            f"Input too large: {total_chars} characters (max "
            f"{settings.INFERENCE_MAX_INPUT_CHARS})."
        )
    return None


def _clamp_max_tokens(body) -> None:
    """Clamp an explicit, excessive max_tokens down to the configured ceiling.
    Absent max_tokens is left alone (the upstream timeout bounds runaway)."""
    cap = settings.INFERENCE_MAX_OUTPUT_TOKENS
    mt = body.get("max_tokens")
    if isinstance(mt, int) and mt > cap:
        body["max_tokens"] = cap


def _ensure_stream_usage(body) -> None:
    """Make the upstream emit token usage on a streamed response.

    Per the OpenAI streaming spec, servers only include a final `usage` chunk
    when the client sets `stream_options.include_usage`. Most clients (Open
    WebUI, the default SDK stream) don't, so streamed requests would otherwise
    report no tokens. We set it for the upstream call (without overriding an
    explicit client choice) so token accounting works for streams too. The
    extra usage chunk is standard OpenAI behavior and is passed through to the
    client unchanged."""
    so = body.get("stream_options")
    if not isinstance(so, dict):
        body["stream_options"] = {"include_usage": True}
    elif "include_usage" not in so:
        so["include_usage"] = True


class _RateLimitHeadersMixin:
    """Adds ``X-RateLimit-{Limit,Remaining,Reset}`` headers to responses, so
    OpenAI-style clients and scripts can see their headroom on every call.
    Reflects state *after* this request was counted."""

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        scope = getattr(self, "throttle_scope", None)
        user = getattr(request, "user", None)
        if scope and user is not None and user.is_authenticated:
            try:
                u = scope_usage(scope, user.pk)
                if u:
                    response["X-RateLimit-Limit"] = str(u["limit"])
                    response["X-RateLimit-Remaining"] = str(u["remaining"])
                    response["X-RateLimit-Reset"] = str(u["reset_in_seconds"])
            except Exception:  # headers are best-effort; never break the response
                pass
        return response


def _online_providers(user):
    return [
        p
        for p in user.providers.filter(
            is_active=True, accepting_requests=True
        ).exclude(tailnet_hostname="")
        if p.is_online
    ]


def _model_slug(pm) -> str:
    """The public, poolable id for a deployment: its CatalogModel slug, or a
    slug derived from the served name for rows not yet linked."""
    if pm.catalog_model_id is not None:
        return pm.catalog_model.slug
    return slugify_model_id(pm.name)


def _model_caps(pm) -> dict:
    """Capability fields for a deployment's catalog model, surfaced on
    /v1/models so clients (the playground) can adapt the UI. Extra fields are
    ignored by standard OpenAI clients."""
    cat = pm.catalog_model if pm.catalog_model_id else None
    # Prefer the live-probed served window over the catalog's HF-derived one.
    context = pm.served_context_len or (cat.native_context_length if cat else None)
    return {
        "input_modalities": (cat.input_modalities or ["text"]) if cat else ["text"],
        "output_modalities": (cat.output_modalities or ["text"]) if cat else ["text"],
        "supported_features": (cat.supported_features or []) if cat else [],
        "context_length": context,
    }


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


def _model_match_q(model_name):
    """A deployment matches the requested model id if it's pooled under the
    same catalog slug (the public, lowercased id) or its raw served name
    matches (exact, or case-insensitively for not-yet-linked rows)."""
    return (
        Q(catalog_model__slug=slugify_model_id(model_name))
        | Q(name=model_name)
        | Q(name__iexact=model_name)
    )


def _find_provider_for_model(user, model_name):
    """Pick the first online deployment of ``model_name`` that ``user`` is
    allowed to use — their own node, or someone else's shared service.

    Returns the matching ``ProviderModel`` (so the caller knows the real
    *served* name to forward upstream), or None. MVP routing: no load
    balancing. Own providers get a self-healing model refresh if they
    registered but haven't reported models yet.
    """
    if not model_name:
        return None

    github_login = _user_github_login(user)
    candidates = (
        ProviderModel.objects.filter(
            is_active=True,
            provider__is_active=True,
            provider__accepting_requests=True,
        )
        .exclude(provider__tailnet_hostname="")
        .filter(_model_match_q(model_name))
        .select_related("provider", "service", "catalog_model")
    )
    for pm in candidates:
        if _model_accessible(pm, user, github_login) and pm.provider.is_online:
            return pm

    # Self-healing for the user's OWN providers: if one just registered and
    # hasn't reported models yet, discover now.
    for provider in _online_providers(user):
        if not provider.models.filter(is_active=True).exists():
            try:
                refresh_provider_models(provider)
            except Exception:
                continue
        pm = (
            provider.models.filter(is_active=True)
            .filter(_model_match_q(model_name))
            .select_related("provider", "service", "catalog_model")
            .first()
        )
        if pm is not None:
            return pm
    return None


class ModelsView(_RateLimitHeadersMixin, APIView):
    """``GET /v1/models`` — OpenAI-format list of every model the requesting
    user may use: their own providers' models, plus shared services elsewhere
    on the network they have access to.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "models"

    def get(self, request):
        seen = {}

        # 1) The user's own providers (with self-healing model discovery so a
        # freshly-registered or idle node still populates the dropdown).
        own = list(
            request.user.providers.filter(
                is_active=True, accepting_requests=True
            ).exclude(tailnet_hostname="")
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
            for m in provider.models.filter(is_active=True).select_related("catalog_model"):
                slug = _model_slug(m)
                seen.setdefault(
                    slug,
                    {
                        "id": slug,
                        "object": "model",
                        "created": created,
                        "owned_by": provider.name,
                        **_model_caps(m),
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
                provider__accepting_requests=True,
                provider__last_seen_at__gte=cutoff,
                service__isnull=False,
            )
            .exclude(provider__tailnet_hostname="")
            .exclude(provider__user=request.user)
            .select_related("provider", "service", "catalog_model")
        )
        for pm in shared:
            slug = _model_slug(pm)
            if slug in seen:
                continue
            if pm.service.grants_access_to(request.user, github_login):
                seen[slug] = {
                    "id": slug,
                    "object": "model",
                    "created": int(pm.provider.created_on.timestamp()),
                    "owned_by": pm.provider.name,
                    **_model_caps(pm),
                }
        return Response({"object": "list", "data": list(seen.values())})


class _ChatOrCompletionsProxy(_RateLimitHeadersMixin, APIView):
    """Shared proxy logic for /v1/chat/completions and /v1/completions."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "inference"
    upstream_path = ""  # set by subclass
    inference_type = ""  # set by subclass

    def post(self, request):
        body = request.data
        model_name = body.get("model")

        # Guardrails: reject oversized inputs and clamp runaway output budgets
        # before we tie up a provider's GPU.
        too_large = _request_too_large(body) if isinstance(body, dict) else None
        if too_large:
            return Response(
                {"error": {"message": too_large, "type": "request_too_large"}},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        if isinstance(body, dict):
            _clamp_max_tokens(body)

        provider_model = _find_provider_for_model(request.user, model_name)
        if provider_model is None:
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

        provider = provider_model.provider
        served_name = provider_model.name
        canonical = _model_slug(provider_model)
        # The caller addresses the model by its public slug, but the upstream
        # backend (vLLM et al.) matches model ids case-sensitively against the
        # exact served name. Rewrite so pooling many providers under one slug
        # doesn't break the actual forward.
        if isinstance(body, dict) and served_name:
            body["model"] = served_name

        endpoint = provider.tailnet_base_url.rstrip("/") + self.upstream_path
        stream = bool(body.get("stream"))
        if stream and isinstance(body, dict):
            # Opt into streamed token usage so streams report tokens too.
            _ensure_stream_usage(body)
        ir = InferenceRequest.objects.create(
            user=request.user,
            provider=provider,
            # Record the canonical (pooled) id so dashboards/leaderboards
            # aggregate one model across providers, not per served-name variant.
            model_name=canonical or model_name or "",
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
        ir.prompt_tokens, ir.completion_tokens, ir.total_tokens = _usage_tokens(data)
        ir.latency_ms = int((time.monotonic() - started) * 1000)
        ir.save(
            update_fields=[
                "status",
                "results",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "latency_ms",
                "modified_on",
            ]
        )
        Provider.objects.filter(id=ir.provider_id).update(last_seen_at=timezone.now())
        return Response(data, status=upstream.status_code)

    def _stream_response(self, upstream, ir, started):
        chunks = []
        first_token_at = None

        def gen():
            nonlocal first_token_at
            try:
                for chunk in upstream.iter_content(chunk_size=8192):
                    if chunk:
                        if first_token_at is None:
                            first_token_at = time.monotonic()
                        chunks.append(chunk)
                        yield chunk
            finally:
                results = _assemble_streamed_results(chunks, ir.model_name)
                ir.status = "PROCESSED"
                ir.results = results
                ir.prompt_tokens, ir.completion_tokens, ir.total_tokens = _usage_tokens(results)
                ir.latency_ms = int((time.monotonic() - started) * 1000)
                if first_token_at is not None:
                    ir.ttft_ms = int((first_token_at - started) * 1000)
                ir.save(
                    update_fields=[
                        "status",
                        "results",
                        "prompt_tokens",
                        "completion_tokens",
                        "total_tokens",
                        "latency_ms",
                        "ttft_ms",
                        "modified_on",
                    ]
                )
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
