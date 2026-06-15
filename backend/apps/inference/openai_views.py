"""OpenAI-compatible endpoints under /v1/.

These views authenticate the user by Bearer API key, find a matching online
provider, and proxy the request to that provider's agent. Streaming responses
are passed through unchanged so OpenAI SDK clients can stream as usual.
"""
import json
import logging
import re
import time

import requests
from django.conf import settings
from django.db.models import Q
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .throttling import AccountTypeScopedRateThrottle, anon_scope_rate, is_anon_account
from rest_framework.views import APIView

from apps.accounts.models import CustomUser

from .models import (
    PROVIDER_LAST_SEEN_WINDOW,
    InferenceRequest,
    Provider,
    ProviderModel,
    slugify_model_id,
)
from .serializers import _user_real_github_login
from .sharing import SHARING_KEYS, file_into_collection, pop_sharing_params
from .views import _tailnet_proxies, refresh_provider_models, scope_usage

logger = logging.getLogger("django")

# Per-request budget for the upstream call. LLM responses can be slow; this is
# generous but bounded so a hung agent doesn't pin a worker forever.
UPSTREAM_TIMEOUT_SECONDS = 300


def _pop_async(request) -> bool:
    """Detect the inference.club ``async`` extension and strip it from the body
    so it never reaches the upstream server. Returns whether the caller wants
    the queued path. Only meaningful for JSON bodies (the async-submittable
    modalities are all JSON); multipart uploads stay synchronous."""
    body = request.data
    if not isinstance(body, dict):
        return False
    v = body.pop("async", None)
    if isinstance(v, bool):
        return v
    return v is not None and str(v).strip().lower() in {"1", "true", "yes", "on"}


def _enqueue_async(request, inference_type, payload, visibility, collection_name, model_name=""):
    """Create a queued job from a validated payload and return the 202 (or a
    503 if async is disabled). Imported lazily to avoid an import cycle."""
    from .job_views import submit_async

    return submit_async(
        request, inference_type, payload,
        visibility=visibility, collection_name=collection_name, model_name=model_name,
    )


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
                if is_anon_account(user):
                    u = scope_usage(
                        f"{scope}_anon", user.pk, rate=anon_scope_rate(scope)
                    )
                else:
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
    # Prefer the live-probed served window over the catalog's declared ceiling.
    context = pm.served_context_len or (cat.native_context_length if cat else None)
    # The modality/endpoint kind ("llm" | "stt" | "tts") lets the playground
    # route a model to the right surface (chat vs. transcription). Unlinked
    # (live-discovered) models default to "llm".
    service_type = pm.service.service_type if pm.service_id else "llm"
    # Capabilities are the catalog's (model-identity) features UNION the
    # operator's per-deployment declarations (e.g. an STT service launched with
    # a ForcedAligner declares "timestamps"). Per-deployment because the same
    # model id may or may not expose a feature depending on how it was served.
    features = list((cat.supported_features or []) if cat else [])
    if pm.service_id:
        for f in pm.service.declared_features or []:
            if f not in features:
                features.append(f)
    return {
        "input_modalities": (cat.input_modalities or ["text"]) if cat else ["text"],
        "output_modalities": (cat.output_modalities or ["text"]) if cat else ["text"],
        "supported_features": features,
        "context_length": context,
        "service_type": service_type,
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


def _service_type_q(service_type):
    """Restrict a ProviderModel query to a service type (e.g. only STT
    services for a transcription request). ``None`` means no restriction — the
    LLM path stays unchanged, including live-discovered models with no linked
    service."""
    if not service_type:
        return Q()
    return Q(service__service_type=service_type)


def _own_provider_match(user, model_name, service_type=None):
    """An online deployment of ``model_name`` on one of ``user``'s OWN nodes,
    with self-healing: if a node just registered and hasn't reported models
    yet, discover them now. Returns a ProviderModel or None."""
    for provider in _online_providers(user):
        if not provider.models.filter(is_active=True).exists():
            try:
                refresh_provider_models(provider)
            except Exception:
                continue
        pm = (
            provider.models.filter(is_active=True)
            .filter(_model_match_q(model_name))
            .filter(_service_type_q(service_type))
            .select_related("provider", "service", "catalog_model")
            .first()
        )
        if pm is not None:
            return pm
    return None


def _any_provider_match(user, model_name, github_login, service_type=None):
    """The first online deployment of ``model_name`` the user may route to —
    own node or someone else's shared service. Returns a ProviderModel or
    None."""
    candidates = (
        ProviderModel.objects.filter(
            is_active=True,
            provider__is_active=True,
            provider__accepting_requests=True,
        )
        .exclude(provider__tailnet_hostname="")
        .filter(_model_match_q(model_name))
        .filter(_service_type_q(service_type))
        .select_related("provider", "service", "catalog_model")
    )
    for pm in candidates:
        if _model_accessible(pm, user, github_login) and pm.provider.is_online:
            return pm
    return None


def _find_provider_for_model(user, model_name, service_type=None):
    """Pick an online deployment of ``model_name`` that ``user`` is allowed to
    use, honoring their global routing preference:

    - ``ONLY_OWN``   — only the user's own nodes; no fallback to the network.
    - ``PREFER_OWN`` — the user's own nodes first, else any accessible node.
    - ``ANY`` (default) — any accessible node; own nodes get a self-healing
      discovery pass as a fallback.

    ``service_type`` (e.g. ``"stt"``) restricts routing to services of that
    kind, so a transcription request can only land on an STT service. ``None``
    (the LLM default) imposes no restriction and preserves prior behavior.

    Returns the matching ``ProviderModel`` (so the caller knows the real
    *served* name to forward upstream), or None. MVP routing: no load
    balancing within a tier.
    """
    if not model_name:
        return None

    pref = getattr(user, "routing_preference", None) or CustomUser.ROUTING_ANY
    github_login = _user_real_github_login(user)

    if pref == CustomUser.ROUTING_ONLY_OWN:
        return _own_provider_match(user, model_name, service_type)

    if pref == CustomUser.ROUTING_PREFER_OWN:
        return _own_provider_match(user, model_name, service_type) or _any_provider_match(
            user, model_name, github_login, service_type
        )

    # ANY (default): any accessible node, with own-node self-healing fallback.
    return _any_provider_match(
        user, model_name, github_login, service_type
    ) or _own_provider_match(user, model_name, service_type)


class ModelsView(_RateLimitHeadersMixin, APIView):
    """``GET /v1/models`` — OpenAI-format list of every model the requesting
    user may use: their own providers' models, plus shared services elsewhere
    on the network they have access to.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
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
            for m in provider.models.filter(is_active=True).select_related("catalog_model", "service"):
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
        github_login = _user_real_github_login(request.user)
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
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "inference"
    upstream_path = ""  # set by subclass
    inference_type = ""  # set by subclass

    def post(self, request):
        body = request.data
        # Popped here so the verbatim body forward (and stored payload) never
        # includes the inference.club sharing extensions.
        visibility, collection_name = pop_sharing_params(request)
        go_async = _pop_async(request)
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
            message = (
                f"No online provider serving model '{model_name}' for this user."
            )
            if getattr(request.user, "routing_preference", None) == CustomUser.ROUTING_ONLY_OWN:
                message += (
                    " Your routing preference is set to use only your own nodes; "
                    "no online node of yours serves this model."
                )
            return Response(
                {
                    "error": {
                        "message": message,
                        "type": "no_provider",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        provider = provider_model.provider
        served_name = provider_model.name
        canonical = _model_slug(provider_model)
        # Async opt-in: queue the request (buffered, late-bound to whatever
        # provider is free at run time) instead of proxying inline. Stored with
        # the canonical model id, not the served name, so the dispatcher can
        # re-route. Done before the served-name rewrite below.
        if go_async:
            job_body = dict(body)
            job_body["model"] = canonical or model_name or ""
            return _enqueue_async(
                request, self.inference_type, job_body,
                visibility, collection_name, model_name=canonical or model_name or "",
            )
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
            visibility=visibility or "",
        )
        file_into_collection(request.user, ir, collection_name)
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


def _store_input_audio(user, ir, upload, data: bytes):
    """Persist the uploaded audio as an INPUT_AUDIO MediaAsset linked to the
    request, so the playground/profile can replay it. Best-effort: a storage
    hiccup must not fail the transcription. Returns the asset or None."""
    from django.core.files.base import ContentFile

    from .models import MediaAsset

    try:
        asset = MediaAsset(
            user=user,
            inference_request=ir,
            kind=MediaAsset.INPUT_AUDIO,
            content_type=getattr(upload, "content_type", "") or "",
            size_bytes=len(data),
        )
        asset.file.save(
            getattr(upload, "name", "audio") or "audio",
            ContentFile(data),
            save=False,
        )
        asset.save()
        return asset
    except Exception as e:  # storage misconfig shouldn't break inference
        logger.warning("input-audio store failed: %s", e)
        return None


class AudioTranscriptionsView(_RateLimitHeadersMixin, APIView):
    """``POST /v1/audio/transcriptions`` — OpenAI-compatible speech-to-text.

    Deliberately separate from the JSON LLM proxy: the request is
    ``multipart/form-data`` (an audio file + form fields), the response is a
    single buffered JSON body (no streaming), and routing is restricted to
    STT services. Shares provider routing, request logging, and rate-limit
    headers with the LLM path; nothing else.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "inference"
    inference_type = "STT"
    upstream_path = "/audio/transcriptions"

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"error": {"message": "`file` is required.", "type": "missing_file"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size and upload.size > settings.STT_MAX_UPLOAD_BYTES:
            return Response(
                {
                    "error": {
                        "message": (
                            f"Audio file too large: {upload.size} bytes (max "
                            f"{settings.STT_MAX_UPLOAD_BYTES})."
                        ),
                        "type": "file_too_large",
                    }
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        ctype = (upload.content_type or "").split(";", 1)[0].strip().lower()
        if ctype and ctype not in settings.STT_ALLOWED_CONTENT_TYPES:
            return Response(
                {
                    "error": {
                        "message": f"Unsupported audio content-type: {ctype!r}.",
                        "type": "unsupported_media_type",
                    }
                },
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )

        visibility, collection_name = pop_sharing_params(request)
        model_name = request.data.get("model")
        provider_model = _find_provider_for_model(
            request.user, model_name, service_type="stt"
        )
        if provider_model is None:
            return Response(
                {
                    "error": {
                        "message": (
                            f"No online speech-to-text provider serving model "
                            f"'{model_name}' for this user."
                        ),
                        "type": "no_provider",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        provider = provider_model.provider
        served_name = provider_model.name
        canonical = _model_slug(provider_model)
        caps = _model_caps(provider_model)
        supports_ts = "timestamps" in (caps.get("supported_features") or [])

        # Build the upstream form, rewriting the model id to the served name and
        # downgrading verbose_json/timestamp requests the model can't satisfy
        # (some ASR servers, e.g. Qwen3-ASR, 400 on verbose_json).
        data_fields, granularities = [], []
        for key in request.data.keys():
            # The multipart QueryDict is immutable, so sharing extensions are
            # skipped here instead of popped.
            if key == "file" or key in SHARING_KEYS:
                continue
            values = (
                request.data.getlist(key)
                if hasattr(request.data, "getlist")
                else [request.data.get(key)]
            )
            for v in values:
                if key in ("timestamp_granularities", "timestamp_granularities[]"):
                    granularities.append((key, v))
                    continue
                if key == "model":
                    v = served_name or v
                if key == "response_format" and v == "verbose_json" and not supports_ts:
                    v = "json"
                data_fields.append((key, v))
        if "model" not in request.data and served_name:
            data_fields.append(("model", served_name))
        requested_format = request.data.get("response_format") or "json"
        if supports_ts:
            data_fields.extend(granularities)

        # Read the upload once: forward the same bytes upstream and (optionally)
        # persist them. Bounded by STT_MAX_UPLOAD_BYTES checked above.
        audio_bytes = upload.read()

        ir = InferenceRequest.objects.create(
            user=request.user,
            provider=provider,
            model_name=canonical or model_name or "",
            inference_type="STT",
            payload={
                "model": canonical or model_name or "",
                "filename": getattr(upload, "name", "") or "",
                "content_type": ctype,
                "size_bytes": len(audio_bytes),
                "response_format": requested_format,
                "language": request.data.get("language") or None,
                "prompt": request.data.get("prompt") or None,
            },
            status="PROCESSING",
            visibility=visibility or "",
        )
        file_into_collection(request.user, ir, collection_name)

        asset = None
        if settings.STT_STORE_INPUT_AUDIO:
            asset = _store_input_audio(request.user, ir, upload, audio_bytes)
            if asset is not None:
                ir.payload["asset_id"] = asset.id
                ir.save(update_fields=["payload", "modified_on"])

        endpoint = provider.tailnet_base_url.rstrip("/") + self.upstream_path
        started = time.monotonic()
        try:
            upstream = requests.post(
                endpoint,
                files={"file": (getattr(upload, "name", "audio"), audio_bytes, ctype or "application/octet-stream")},
                data=data_fields,
                timeout=UPSTREAM_TIMEOUT_SECONDS,
                verify=False,
                proxies=_tailnet_proxies(),
            )
        except requests.RequestException as e:
            ir.status = "REQUESTED"
            ir.results = {"error": str(e)}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            logger.error("Upstream transcription failed: %s", e)
            return Response(
                {"error": {"message": str(e), "type": "upstream_error"}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not upstream.ok:
            ir.status = "REQUESTED"
            ir.results = {"upstream_status": upstream.status_code}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            return Response(
                upstream.json()
                if upstream.headers.get("content-type", "").startswith("application/json")
                else {"error": upstream.text},
                status=upstream.status_code,
            )

        try:
            payload = upstream.json()
        except ValueError:
            payload = {"text": upstream.text}

        seconds = _audio_seconds(payload)
        ir.status = "PROCESSED"
        ir.results = payload
        ir.audio_seconds = seconds
        ir.latency_ms = int((time.monotonic() - started) * 1000)
        ir.save(
            update_fields=["status", "results", "audio_seconds", "latency_ms", "modified_on"]
        )
        if asset is not None and seconds is not None and asset.duration_seconds is None:
            asset.duration_seconds = seconds
            asset.save(update_fields=["duration_seconds", "modified_on"])
        Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())
        return Response(payload, status=upstream.status_code)


def _audio_seconds(payload):
    """Audio duration (seconds) from a transcription response — the metering
    signal. OpenAI-compatible servers report it as ``usage.seconds`` (Qwen3-
    ASR) or a top-level ``duration`` (verbose_json). Returns a float or None."""
    if not isinstance(payload, dict):
        return None
    usage = payload.get("usage")
    if isinstance(usage, dict):
        for key in ("seconds", "duration", "input_seconds"):
            v = usage.get(key)
            if isinstance(v, (int, float)) and v >= 0:
                return float(v)
    dur = payload.get("duration")
    if isinstance(dur, (int, float)) and dur >= 0:
        return float(dur)
    return None


# --- image generation ------------------------------------------------------


def _store_output_image(user, ir, b64_str, index):
    """Decode an upstream base64 image and persist it as an OUTPUT_IMAGE
    MediaAsset in MinIO. Returns the asset, or None on bad data."""
    import base64

    from django.core.files.base import ContentFile

    from .models import MediaAsset

    try:
        raw = base64.b64decode(b64_str)
    except (ValueError, TypeError):
        return None
    asset = MediaAsset(
        user=user,
        inference_request=ir,
        kind=MediaAsset.OUTPUT_IMAGE,
        content_type="image/png",
        size_bytes=len(raw),
    )
    asset.file.save(f"image-{index}.png", ContentFile(raw), save=False)
    asset.save()
    return asset


def _asset_url(request, asset) -> str:
    from .serializers import asset_url

    return asset_url(asset, request)


class _ImageProxyBase(_RateLimitHeadersMixin, APIView):
    """Shared logic for /v1/images/* : synchronous, buffered, b64_json forced
    upstream, outputs stored in MinIO. Deliberately separate from the JSON LLM
    proxy and the STT view; routes only to ``image`` services."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "inference"
    inference_type = "IMAGE"
    upstream_path = ""  # set by subclass

    def _no_provider(self, model_name):
        return Response(
            {
                "error": {
                    "message": (
                        f"No online image provider serving model "
                        f"'{model_name}' for this user."
                    ),
                    "type": "no_provider",
                }
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    def _finalize(self, request, ir, upstream, started, requested_format):
        """Store output images, shape the client response (url default /
        b64_json on request), and finalize the InferenceRequest."""
        if not upstream.ok:
            ir.status = "REQUESTED"
            ir.results = {"upstream_status": upstream.status_code}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            return Response(
                upstream.json()
                if upstream.headers.get("content-type", "").startswith("application/json")
                else {"error": upstream.text},
                status=upstream.status_code,
            )

        try:
            payload = upstream.json()
        except ValueError:
            payload = {}
        data = payload.get("data") if isinstance(payload, dict) else None
        out_data, asset_ids = [], []
        for i, item in enumerate(data or []):
            if not isinstance(item, dict):
                continue
            b64 = item.get("b64_json")
            asset = _store_output_image(request.user, ir, b64, i) if b64 else None
            if asset is not None:
                asset_ids.append(asset.id)
            entry = {}
            if requested_format == "b64_json":
                entry["b64_json"] = b64
            elif asset is not None:
                entry["url"] = _asset_url(request, asset)
            if item.get("revised_prompt"):
                entry["revised_prompt"] = item["revised_prompt"]
            if entry:
                out_data.append(entry)

        ir.status = "PROCESSED"
        ir.image_count = len(asset_ids)
        ir.results = {
            "created": payload.get("created") if isinstance(payload, dict) else None,
            "image_asset_ids": asset_ids,
            "count": len(asset_ids),
        }
        ir.latency_ms = int((time.monotonic() - started) * 1000)
        ir.save(
            update_fields=["status", "image_count", "results", "latency_ms", "modified_on"]
        )
        Provider.objects.filter(id=ir.provider_id).update(last_seen_at=timezone.now())
        return Response(
            {"created": payload.get("created") if isinstance(payload, dict) else None,
             # Mirrors the mesh/video endpoints — lets the UI link the stored
             # request (e.g. set a generated image as cover art) without a
             # follow-up list query.
             "request_id": str(ir.id),
             "data": out_data},
            status=upstream.status_code,
        )

    def _forward_error(self, ir, started, exc):
        ir.status = "REQUESTED"
        ir.results = {"error": str(exc)}
        ir.latency_ms = int((time.monotonic() - started) * 1000)
        ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
        logger.error("Upstream image request failed: %s", exc)
        return Response(
            {"error": {"message": str(exc), "type": "upstream_error"}},
            status=status.HTTP_502_BAD_GATEWAY,
        )


def _riva_encoding(response_format):
    """Map an OpenAI ``response_format`` to a (riva_encoding, content_type, ext).
    Riva returns WAV (LINEAR_PCM) natively; we support that and OGG/Opus, and
    fall back to WAV for formats Riva can't produce (mp3/aac/flac) rather than
    transcoding."""
    fmt = (response_format or "wav").lower()
    if fmt in ("opus", "ogg"):
        return "OGGOPUS", "audio/ogg", "ogg"
    # wav, pcm, and the unsupported mp3/aac/flac all resolve to WAV.
    return "LINEAR_PCM", "audio/wav", "wav"


def _wav_seconds(audio: bytes):
    """Duration (seconds) of a WAV blob, for metering. None for non-WAV."""
    import io
    import wave

    try:
        with wave.open(io.BytesIO(audio)) as w:
            rate = w.getframerate()
            return round(w.getnframes() / float(rate), 3) if rate else None
    except Exception:
        return None


def _flatten_voices(data) -> list:
    """Flatten Riva's nested list_voices shape
    ``{"en-US,es-US,...": {"voices": [...]}}`` into a sorted unique list."""
    out: list[str] = []
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, dict) and isinstance(v.get("voices"), list):
                out.extend(str(x) for x in v["voices"])
            elif isinstance(v, list):
                out.extend(str(x) for x in v)
    elif isinstance(data, list):
        out.extend(str(x) for x in data)
    return sorted(set(out))


class AudioSpeechView(_RateLimitHeadersMixin, APIView):
    """``POST /v1/audio/speech`` — OpenAI-compatible text-to-speech.

    The request is the OpenAI shape (`model`, `input`, `voice`, …); we adapt it
    to the provider's NVIDIA Riva ``/v1/audio/synthesize`` endpoint, store the
    generated audio (public OUTPUT_AUDIO), and return the raw audio bytes —
    exactly like the OpenAI API. Routes only to `tts` services.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "inference"
    inference_type = "TTS"

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        visibility, collection_name = pop_sharing_params(request)
        go_async = _pop_async(request)
        text = body.get("input")
        if not isinstance(text, str) or not text.strip():
            return Response(
                {"error": {"message": "`input` is required.", "type": "missing_input"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(text) > settings.TTS_MAX_INPUT_CHARS:
            return Response(
                {"error": {"message": "Input text too long.", "type": "request_too_large"}},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        model_name = body.get("model")
        provider_model = _find_provider_for_model(
            request.user, model_name, service_type="tts"
        )
        if provider_model is None:
            return Response(
                {
                    "error": {
                        "message": f"No online text-to-speech provider serving model "
                        f"'{model_name}' for this user.",
                        "type": "no_provider",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        provider = provider_model.provider
        canonical = _model_slug(provider_model)
        voice = body.get("voice") or settings.TTS_DEFAULT_VOICE
        language = body.get("language") or settings.TTS_DEFAULT_LANGUAGE
        try:
            sample_rate = int(body.get("sample_rate_hz") or settings.TTS_DEFAULT_SAMPLE_RATE)
        except (TypeError, ValueError):
            sample_rate = settings.TTS_DEFAULT_SAMPLE_RATE
        requested_format = body.get("response_format") or "wav"
        encoding, content_type, ext = _riva_encoding(requested_format)

        stored_payload = {
            "model": canonical or model_name or "",
            "input": text,
            "voice": voice,
            "language": language,
            "response_format": requested_format,
        }
        if go_async:
            return _enqueue_async(
                request, self.inference_type, stored_payload,
                visibility, collection_name, model_name=canonical or model_name or "",
            )

        ir = InferenceRequest.objects.create(
            user=request.user,
            provider=provider,
            model_name=canonical or model_name or "",
            inference_type="TTS",
            payload=stored_payload,
            status="PROCESSING",
            visibility=visibility or "",
        )
        file_into_collection(request.user, ir, collection_name)

        # Adapt to Riva's multipart /audio/synthesize. Sent as multipart form
        # fields (files with (None, value)) to match the NIM's expectation.
        endpoint = provider.tailnet_base_url.rstrip("/") + "/audio/synthesize"
        fields = {
            "text": (None, text),
            "language": (None, language),
            "voice": (None, voice),
            "sample_rate_hz": (None, str(sample_rate)),
            "encoding": (None, encoding),
        }
        started = time.monotonic()
        try:
            upstream = requests.post(
                endpoint, files=fields, timeout=UPSTREAM_TIMEOUT_SECONDS,
                verify=False, proxies=_tailnet_proxies(),
            )
        except requests.RequestException as e:
            ir.status = "REQUESTED"
            ir.results = {"error": str(e)}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            logger.error("Upstream speech synthesis failed: %s", e)
            return Response(
                {"error": {"message": str(e), "type": "upstream_error"}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not upstream.ok:
            ir.status = "REQUESTED"
            ir.results = {"upstream_status": upstream.status_code}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            return Response(
                upstream.json()
                if upstream.headers.get("content-type", "").startswith("application/json")
                else {"error": upstream.text[:500]},
                status=upstream.status_code,
            )

        audio = upstream.content
        out_ct = upstream.headers.get("content-type") or content_type
        seconds = _wav_seconds(audio)

        from django.core.files.base import ContentFile

        from .models import MediaAsset

        asset = None
        try:
            asset = MediaAsset(
                user=request.user, inference_request=ir, kind=MediaAsset.OUTPUT_AUDIO,
                content_type=out_ct, size_bytes=len(audio), duration_seconds=seconds,
            )
            asset.file.save(f"speech.{ext}", ContentFile(audio), save=False)
            asset.save()
        except Exception as e:
            logger.warning("output-audio store failed: %s", e)

        ir.status = "PROCESSED"
        ir.audio_seconds = seconds
        ir.results = {
            "audio_asset_id": asset.id if asset else None,
            "content_type": out_ct,
            "voice": voice,
            "characters": len(text),
        }
        ir.latency_ms = int((time.monotonic() - started) * 1000)
        ir.save(
            update_fields=["status", "audio_seconds", "results", "latency_ms", "modified_on"]
        )
        Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())

        from django.http import HttpResponse

        resp = HttpResponse(audio, content_type=out_ct)
        resp["Content-Disposition"] = f'inline; filename="speech.{ext}"'
        return resp


# --- Voice cloning (Dia) — see docs/prd/09-voice-cloning.md ------------------

_SPEAKER_TAG_RE = re.compile(r"\[S(\d+)\]")


def _normalize_script(text):
    """Normalize a voice script and report which speakers it uses.

    Returns ``(normalized_text, speakers_used:set, error:str|None)``:

    - No ``[S*]`` tag at all → treat the whole thing as one line and prefix
      ``[S1] `` (the single-speaker default).
    - Has tags → must start with ``[S1]`` and use only ``[S1]``/``[S2]``
      (``[S3]+`` is rejected in V1).
    """
    s = (text or "").strip()
    nums = [int(n) for n in _SPEAKER_TAG_RE.findall(s)]
    if not nums:
        return "[S1] " + s, {"S1"}, None
    if not s.startswith("[S1]"):
        return None, None, "Script must start with [S1]."
    bad = sorted({n for n in nums if n not in (1, 2)})
    if bad:
        tags = ", ".join(f"[S{n}]" for n in bad)
        return None, None, f"Only [S1] and [S2] are supported (found {tags})."
    return s, {f"S{n}" for n in nums}, None


def _has_feature(pm, feature):
    return feature in (_model_caps(pm).get("supported_features") or [])


def _find_voice_provider(user, model_name):
    """Pick an online ``tts`` deployment that can voice-clone (advertises the
    ``voice-cloning`` feature). With an explicit ``model_name`` we defer to the
    normal router (the agent's voice route picks the Dia backend); otherwise we
    scan for the first accessible voice-cloning model."""
    if model_name:
        return _find_provider_for_model(user, model_name, service_type="tts")
    for provider in _online_providers(user):
        for pm in (
            provider.models.filter(is_active=True)
            .filter(service__service_type="tts")
            .select_related("provider", "service", "catalog_model")
        ):
            if _has_feature(pm, "voice-cloning"):
                return pm
    github_login = _user_real_github_login(user)
    candidates = (
        ProviderModel.objects.filter(
            is_active=True,
            provider__is_active=True,
            provider__accepting_requests=True,
        )
        .exclude(provider__tailnet_hostname="")
        .filter(service__service_type="tts")
        .select_related("provider", "service", "catalog_model")
    )
    for pm in candidates:
        if (
            _has_feature(pm, "voice-cloning")
            and _model_accessible(pm, user, github_login)
            and pm.provider.is_online
        ):
            return pm
    return None


def _pick_stt_model(user, model_name=None):
    """An online STT deployment for internal (voice-sample) transcription."""
    if model_name:
        return _find_provider_for_model(user, model_name, service_type="stt")
    for provider in _online_providers(user):
        pm = (
            provider.models.filter(is_active=True)
            .filter(service__service_type="stt")
            .select_related("provider", "service", "catalog_model")
            .first()
        )
        if pm is not None:
            return pm
    github_login = _user_real_github_login(user)
    candidates = (
        ProviderModel.objects.filter(
            is_active=True,
            provider__is_active=True,
            provider__accepting_requests=True,
        )
        .exclude(provider__tailnet_hostname="")
        .filter(service__service_type="stt")
        .select_related("provider", "service", "catalog_model")
    )
    for pm in candidates:
        if _model_accessible(pm, user, github_login) and pm.provider.is_online:
            return pm
    return None


def transcribe_audio_bytes(user, audio_bytes, filename="sample.wav",
                           content_type="audio/wav", model_name=None):
    """Best-effort STT used to auto-fill a voice sample's transcript. Returns
    ``(text, error)``. Intentionally *not* a billable ``InferenceRequest`` — a
    library utility, like a thumbnail. If no STT provider is online the caller
    keeps the sample with an empty transcript and the UI nudges for a manual
    one (Dia can't clone without it)."""
    pm = _pick_stt_model(user, model_name)
    if pm is None:
        return None, "no_stt_provider"
    provider = pm.provider
    endpoint = provider.tailnet_base_url.rstrip("/") + "/audio/transcriptions"
    try:
        upstream = requests.post(
            endpoint,
            files={"file": (filename, audio_bytes, content_type or "application/octet-stream")},
            data=[("model", pm.name), ("response_format", "json")],
            timeout=UPSTREAM_TIMEOUT_SECONDS,
            verify=False,
            proxies=_tailnet_proxies(),
        )
    except requests.RequestException as e:
        return None, str(e)
    if not upstream.ok:
        return None, f"upstream_{upstream.status_code}"
    try:
        payload = upstream.json()
    except ValueError:
        payload = {"text": upstream.text}
    return (payload.get("text") or "").strip(), None


def _read_asset_bytes(asset):
    """Read a stored MediaAsset's bytes through the storage backend."""
    f = asset.file
    f.open("rb")
    try:
        return f.read()
    finally:
        try:
            f.close()
        except Exception:
            pass


def _ffmpeg_to_wav(data, sample_rate=44100):
    """Transcode arbitrary audio bytes (webm/opus/mp3/m4a/ogg/…) to 16-bit PCM
    mono WAV via ffmpeg. Returns wav bytes, or ``None`` if ffmpeg is missing or
    the decode fails.

    Browser voice samples are recorded as webm/opus, which Dia's ``soundfile``
    (libsndfile) reader can't open ("Format not recognised"), so any audio
    prompt must be normalized to a real WAV here first. Uses temp files (not a
    pipe) so ffmpeg writes a proper seekable RIFF header."""
    import os
    import shutil
    import subprocess
    import tempfile

    if not data or shutil.which("ffmpeg") is None:
        return None
    inp = outp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".in", delete=False) as fin:
            fin.write(data)
            inp = fin.name
        outp = inp + ".wav"
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", inp,
             "-ac", "1", "-ar", str(sample_rate), outp],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
        )
        if proc.returncode == 0 and os.path.exists(outp) and os.path.getsize(outp) > 44:
            with open(outp, "rb") as f:
                return f.read()
    except Exception as e:
        logger.warning("ffmpeg transcode failed: %s", e)
    finally:
        for p in (inp, outp):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass
    return None


def _is_wav(data) -> bool:
    return bool(data) and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def _concat_wavs(wavs, gap_seconds=0.3):
    """Concatenate uniform PCM WAV clips (mono, same rate — as produced by
    ``_ffmpeg_to_wav``) into one WAV with a short silence gap between speakers.
    Pure stdlib (``wave``), no numpy/soundfile. Returns wav bytes or ``None``."""
    import io as _io
    import wave

    try:
        out = _io.BytesIO()
        writer = None
        params = None
        for i, wb in enumerate(wavs):
            r = wave.open(_io.BytesIO(wb), "rb")
            try:
                if writer is None:
                    params = r.getparams()
                    writer = wave.open(out, "wb")
                    writer.setparams(params)
                writer.writeframes(r.readframes(r.getnframes()))
            finally:
                r.close()
            if i < len(wavs) - 1 and params is not None:
                gap = int(params.framerate * gap_seconds) * params.sampwidth * params.nchannels
                writer.writeframes(b"\x00" * gap)
        if writer is not None:
            writer.close()
            return out.getvalue()
    except Exception as e:
        logger.warning("wav concat failed: %s", e)
    return None


def _clamp(val, lo, hi, default):
    try:
        n = float(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


class VoiceGenerationsView(_RateLimitHeadersMixin, APIView):
    """``POST /v1/voice/generations`` — Dia voice cloning / text-to-dialogue.

    A JSON shape (``model``, ``input`` script, optional ``speakers`` map of
    ``S1``/``S2`` → voice-sample id, and Dia sampling controls). Routes only to
    ``tts`` services advertising ``voice-cloning``. The view resolves the
    referenced private voice samples to ``(audio, transcript)``, assembles
    Dia's audio prompt, forwards a multipart request through the agent
    (``/v1/voice/generations`` → Dia's ``/generate``), stores the result as a
    public ``OUTPUT_AUDIO``, and returns the bytes. See
    docs/prd/09-voice-cloning.md.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "inference"
    inference_type = "VOICE"
    upstream_path = "/voice/generations"

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        visibility, collection_name = pop_sharing_params(request)
        raw_text = body.get("input")
        if not isinstance(raw_text, str) or not raw_text.strip():
            return Response(
                {"error": {"message": "`input` is required.", "type": "missing_input"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(raw_text) > settings.TTS_MAX_INPUT_CHARS:
            return Response(
                {"error": {"message": "Input text too long.", "type": "request_too_large"}},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        text, speakers_used, err = _normalize_script(raw_text)
        if err:
            return Response(
                {"error": {"message": err, "type": "invalid_script"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        model_name = body.get("model")
        provider_model = _find_voice_provider(request.user, model_name)
        if provider_model is None:
            return Response(
                {
                    "error": {
                        "message": f"No online voice-cloning provider serving model "
                        f"'{model_name}' for this user.",
                        "type": "no_provider",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        provider = provider_model.provider
        canonical = _model_slug(provider_model)

        # Resolve speaker → voice sample (only speakers the script actually uses,
        # in S1→S2 order so prompt audio and prompt transcript line up).
        from .models import VoiceSample

        speakers = body.get("speakers") if isinstance(body.get("speakers"), dict) else {}
        resolved = []
        for key in ("S1", "S2"):
            if key not in speakers_used or not speakers.get(key):
                continue
            try:
                sample = VoiceSample.objects.select_related("audio").get(
                    id=speakers[key], user=request.user
                )
            except (VoiceSample.DoesNotExist, ValueError, TypeError):
                return Response(
                    {"error": {"message": f"Voice sample {speakers[key]!r} not found.",
                               "type": "invalid_voice_sample"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not (sample.transcript or "").strip():
                return Response(
                    {"error": {"message": f"Voice sample for {sample.speaker_name!r} has no "
                               f"transcript; Dia needs one to clone.",
                               "type": "missing_transcript"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            resolved.append((key, sample))

        cfg_scale = _clamp(body.get("cfg_scale"), 1.0, 5.0, 3.0)
        temperature = _clamp(body.get("temperature"), 0.1, 2.0, 1.8)
        top_p = _clamp(body.get("top_p"), 0.1, 1.0, 0.95)
        cfg_filter_top_k = int(_clamp(body.get("cfg_filter_top_k"), 1, 100, 45))
        speed_factor = _clamp(body.get("speed_factor"), 0.5, 2.0, 1.0)
        max_new_tokens = int(_clamp(body.get("max_new_tokens"), 256, 4096, 3072))
        try:
            seed = int(body.get("seed"))
        except (TypeError, ValueError):
            seed = -1

        # Assemble the cloning prompt: one tagged transcript line per speaker,
        # and a single audio prompt (the clip, or two clips concatenated). Each
        # clip is transcoded to real WAV first — browser samples are webm/opus,
        # which Dia's soundfile reader can't open.
        audio_prompt_bytes = None
        prompt_transcript = ""
        prompt_note = None
        if resolved:
            lines = [f"[{k}] {s.transcript.strip()}" for k, s in resolved]
            clips = []
            for _key, s in resolved:
                raw = _read_asset_bytes(s.audio)
                wav = _ffmpeg_to_wav(raw)
                if wav is None and _is_wav(raw):
                    wav = raw  # already a real WAV (e.g. ffmpeg unavailable)
                if wav is None:
                    return Response(
                        {"error": {"message": f"Could not decode the voice-sample "
                                   f"audio for {s.speaker_name!r} (format "
                                   f"{s.audio.content_type or 'unknown'!r}). Re-record "
                                   f"the sample or upload a WAV/MP3.",
                                   "type": "audio_decode_failed"}},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                clips.append(wav)
            prompt_transcript = "\n".join(lines)
            if len(clips) == 1:
                audio_prompt_bytes = clips[0]
            else:
                concat = _concat_wavs(clips)
                if concat is not None:
                    audio_prompt_bytes = concat
                else:
                    # Couldn't merge two voices — clone S1 only.
                    audio_prompt_bytes = clips[0]
                    prompt_transcript = lines[0]
                    prompt_note = "multi_voice_clone_unavailable"

        ir = InferenceRequest.objects.create(
            user=request.user,
            provider=provider,
            model_name=canonical or model_name or "",
            inference_type="VOICE",
            payload={
                "model": canonical or model_name or "",
                "input": text,
                "speakers": {k: s.id for k, s in resolved},
                "cfg_scale": cfg_scale,
                "temperature": temperature,
                "top_p": top_p,
                "cfg_filter_top_k": cfg_filter_top_k,
                "speed_factor": speed_factor,
                "max_new_tokens": max_new_tokens,
                "seed": seed,
            },
            status="PROCESSING",
            visibility=visibility or "",
        )
        file_into_collection(request.user, ir, collection_name)

        fields = {
            "text": (None, text),
            "max_new_tokens": (None, str(max_new_tokens)),
            "cfg_scale": (None, str(cfg_scale)),
            "temperature": (None, str(temperature)),
            "top_p": (None, str(top_p)),
            "cfg_filter_top_k": (None, str(cfg_filter_top_k)),
            "speed_factor": (None, str(speed_factor)),
            "seed": (None, str(seed)),
        }
        if audio_prompt_bytes is not None:
            fields["audio_prompt_text"] = (None, prompt_transcript)
            fields["audio_prompt"] = ("prompt.wav", audio_prompt_bytes, "audio/wav")

        endpoint = provider.tailnet_base_url.rstrip("/") + self.upstream_path
        started = time.monotonic()
        try:
            upstream = requests.post(
                endpoint, files=fields, timeout=UPSTREAM_TIMEOUT_SECONDS,
                verify=False, proxies=_tailnet_proxies(),
            )
        except requests.RequestException as e:
            ir.status = "REQUESTED"
            ir.results = {"error": str(e)}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            logger.error("Upstream voice generation failed: %s", e)
            return Response(
                {"error": {"message": str(e), "type": "upstream_error"}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not upstream.ok:
            err_text = (upstream.text or "")[:1000]
            ir.status = "REQUESTED"
            ir.results = {"upstream_status": upstream.status_code, "error": err_text}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            return Response(
                upstream.json()
                if upstream.headers.get("content-type", "").startswith("application/json")
                else {"error": {"message": err_text, "type": "upstream_error"}},
                status=upstream.status_code,
            )

        audio = upstream.content
        out_ct = (upstream.headers.get("content-type") or "audio/wav").split(";", 1)[0]
        try:
            seconds = float(upstream.headers.get("x-duration-seconds") or 0) or _wav_seconds(audio)
        except (TypeError, ValueError):
            seconds = _wav_seconds(audio)
        used_seed = upstream.headers.get("x-seed")

        from django.core.files.base import ContentFile

        from .models import MediaAsset

        asset = None
        try:
            asset = MediaAsset(
                user=request.user, inference_request=ir, kind=MediaAsset.OUTPUT_AUDIO,
                content_type=out_ct, size_bytes=len(audio), duration_seconds=seconds,
            )
            asset.file.save("voice.wav", ContentFile(audio), save=False)
            asset.save()
        except Exception as e:
            logger.warning("voice output-audio store failed: %s", e)

        ir.status = "PROCESSED"
        ir.audio_seconds = seconds
        ir.results = {
            "audio_asset_id": asset.id if asset else None,
            "content_type": out_ct,
            "seed": used_seed,
            "characters": len(text),
        }
        if prompt_note:
            ir.results["note"] = prompt_note
        ir.latency_ms = int((time.monotonic() - started) * 1000)
        ir.save(
            update_fields=["status", "audio_seconds", "results", "latency_ms", "modified_on"]
        )
        Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())

        from django.http import HttpResponse

        resp = HttpResponse(audio, content_type=out_ct)
        resp["Content-Disposition"] = 'inline; filename="voice.wav"'
        if used_seed:
            resp["x-seed"] = used_seed
        return resp


# Output format → (content_type, file extension) for generated music. The agent
# passes the real Content-Type back from ACE-Step's audio download, so this is
# only the fallback + the stored-file extension.
_MUSIC_FORMATS = {
    "mp3": ("audio/mpeg", "mp3"),
    "wav": ("audio/wav", "wav"),
    "wav32": ("audio/wav", "wav"),
    "flac": ("audio/flac", "flac"),
    "opus": ("audio/ogg", "opus"),
    "aac": ("audio/aac", "aac"),
}


class MusicGenerationsView(_RateLimitHeadersMixin, APIView):
    """``POST /v1/music/generations`` — text-to-music (generate a song).

    The request is a simple JSON shape (``model``, ``prompt``, optional
    ``lyrics`` and generation controls). It routes only to ``music`` services
    (e.g. ACE-Step). ACE-Step's own API is async (submit a job, poll, download),
    but the agent runs that whole loop and hands us the finished audio in one
    reply — so this view looks just like TTS: forward, store the generated
    audio (public ``OUTPUT_AUDIO``), and return the raw bytes.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "inference"
    inference_type = "MUSIC"
    upstream_path = "/music/generations"

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        visibility, collection_name = pop_sharing_params(request)
        go_async = _pop_async(request)
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return Response(
                {"error": {"message": "`prompt` is required.", "type": "missing_prompt"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        lyrics = body.get("lyrics") if isinstance(body.get("lyrics"), str) else ""
        if len(prompt) + len(lyrics) > settings.TTS_MAX_INPUT_CHARS:
            return Response(
                {"error": {"message": "Prompt/lyrics too long.", "type": "request_too_large"}},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        model_name = body.get("model")
        provider_model = _find_provider_for_model(
            request.user, model_name, service_type="music"
        )
        if provider_model is None:
            return Response(
                {
                    "error": {
                        "message": f"No online music-generation provider serving model "
                        f"'{model_name}' for this user.",
                        "type": "no_provider",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        provider = provider_model.provider
        served_name = provider_model.name
        canonical = _model_slug(provider_model)

        # --- coerce generation controls to safe ranges --------------------
        def _num(val, lo, hi, default):
            try:
                n = float(val)
            except (TypeError, ValueError):
                return default
            return max(lo, min(hi, n))

        audio_format = str(body.get("audio_format") or "mp3").lower()
        if audio_format not in _MUSIC_FORMATS:
            audio_format = "mp3"
        out_ct_fallback, ext = _MUSIC_FORMATS[audio_format]
        steps = int(_num(body.get("inference_steps"), 1, 200, 8))
        guidance = _num(body.get("guidance_scale"), 0, 30, 7.0)
        randomize = body.get("use_random_seed")
        randomize = True if randomize is None else bool(randomize)
        try:
            seed = int(body.get("seed"))
        except (TypeError, ValueError):
            seed = -1
        duration = body.get("audio_duration")
        duration = _num(duration, 5, 300, None) if duration is not None else None

        # ACE-Step's /release_task request shape. The agent forwards this body
        # verbatim, then polls and downloads the rendered audio.
        forward = {
            "model": served_name or canonical or model_name or "",
            "prompt": prompt,
            "lyrics": lyrics,
            "inference_steps": steps,
            "guidance_scale": guidance,
            "use_random_seed": randomize,
            "seed": seed,
            "audio_format": audio_format,
            "task_type": "text2music",
        }
        if duration is not None:
            forward["audio_duration"] = duration
        if isinstance(body.get("bpm"), (int, float)):
            forward["bpm"] = int(body["bpm"])
        if isinstance(body.get("key_scale"), str) and body["key_scale"].strip():
            forward["key_scale"] = body["key_scale"].strip()
        if isinstance(body.get("vocal_language"), str) and body["vocal_language"].strip():
            forward["vocal_language"] = body["vocal_language"].strip()

        stored_payload = {
            "model": canonical or model_name or "",
            "prompt": prompt,
            "lyrics": lyrics,
            "audio_duration": duration,
            "inference_steps": steps,
            "guidance_scale": guidance,
            "seed": seed,
            "use_random_seed": randomize,
            "audio_format": audio_format,
            # Stored so a retry / "reproduce in playground" is faithful.
            "bpm": forward.get("bpm"),
            "key_scale": forward.get("key_scale", ""),
        }
        if go_async:
            return _enqueue_async(
                request, self.inference_type, stored_payload,
                visibility, collection_name, model_name=canonical or model_name or "",
            )

        ir = InferenceRequest.objects.create(
            user=request.user,
            provider=provider,
            model_name=canonical or model_name or "",
            inference_type="MUSIC",
            payload=stored_payload,
            status="PROCESSING",
            visibility=visibility or "",
        )
        file_into_collection(request.user, ir, collection_name)

        endpoint = provider.tailnet_base_url.rstrip("/") + self.upstream_path
        started = time.monotonic()
        try:
            upstream = requests.post(
                endpoint, json=forward, timeout=UPSTREAM_TIMEOUT_SECONDS,
                verify=False, proxies=_tailnet_proxies(),
            )
        except requests.RequestException as e:
            ir.status = "REQUESTED"
            ir.results = {"error": str(e)}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            logger.error("Upstream music generation failed: %s", e)
            return Response(
                {"error": {"message": str(e), "type": "upstream_error"}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not upstream.ok:
            # Capture the agent's error text (it surfaces the ACE-Step failure
            # reason, e.g. a missing codec) so a failed run is diagnosable from
            # the request record, not just a bare status code.
            err_text = (upstream.text or "")[:1000]
            ir.status = "REQUESTED"
            ir.results = {"upstream_status": upstream.status_code, "error": err_text}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            return Response(
                upstream.json()
                if upstream.headers.get("content-type", "").startswith("application/json")
                else {"error": {"message": err_text, "type": "upstream_error"}},
                status=upstream.status_code,
            )

        audio = upstream.content
        out_ct = (upstream.headers.get("content-type") or out_ct_fallback).split(";", 1)[0]
        seconds = _wav_seconds(audio) or duration

        from django.core.files.base import ContentFile

        from .models import MediaAsset

        asset = None
        try:
            asset = MediaAsset(
                user=request.user, inference_request=ir, kind=MediaAsset.OUTPUT_AUDIO,
                content_type=out_ct, size_bytes=len(audio), duration_seconds=seconds,
            )
            asset.file.save(f"song.{ext}", ContentFile(audio), save=False)
            asset.save()
        except Exception as e:
            logger.warning("music output-audio store failed: %s", e)

        ir.status = "PROCESSED"
        ir.audio_seconds = seconds
        ir.results = {
            "audio_asset_id": asset.id if asset else None,
            "content_type": out_ct,
            "characters": len(prompt) + len(lyrics),
        }
        ir.latency_ms = int((time.monotonic() - started) * 1000)
        ir.save(
            update_fields=["status", "audio_seconds", "results", "latency_ms", "modified_on"]
        )
        Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())

        from django.http import HttpResponse

        resp = HttpResponse(audio, content_type=out_ct)
        resp["Content-Disposition"] = f'inline; filename="song.{ext}"'
        return resp


def _decode_image_input(image):
    """Decode an inbound conditioning image (``data:`` URI or raw base64) to
    ``(bytes, content_type)``, or ``(None, None)`` when it's an http(s) URL or
    unparseable. Used to persist the first-frame image as an INPUT_IMAGE asset
    so an image-to-video run is replayable and unfurls with its source frame."""
    import base64

    if not isinstance(image, str) or not image.strip():
        return None, None
    s = image.strip()
    if s.startswith("http://") or s.startswith("https://"):
        return None, None  # a remote URL — nothing to store locally
    ct = "image/png"
    if s.startswith("data:"):
        header, _, b64 = s.partition(",")
        if ";base64" not in header or not b64:
            return None, None
        mime = header[5:].split(";", 1)[0].strip()
        if mime:
            ct = mime
        s = b64
    try:
        return base64.b64decode(s), ct
    except (ValueError, TypeError):
        return None, None


def _ltx_params(upstream) -> dict:
    """The resolved (snapped) generation params LTX returns in the
    ``X-LTX-Params`` response header, as a dict. Empty when absent/unparseable."""
    raw = upstream.headers.get("X-LTX-Params") or upstream.headers.get("x-ltx-params")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


class VideoGenerationsView(_RateLimitHeadersMixin, APIView):
    """``POST /v1/videos/generations`` — text/image-to-video (generate an MP4).

    A simple JSON shape (``model``, ``prompt``, optional first-frame ``image``
    and generation controls). It routes only to ``video`` services (e.g. LTX-2).
    Like music/TTS this is one-shot: forward, store the generated video (public
    ``OUTPUT_VIDEO``), persist the optional conditioning image (``INPUT_IMAGE``,
    used as the share/OG preview), and return the raw MP4 bytes.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "inference"
    inference_type = "VIDEO"
    upstream_path = "/videos/generations"

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        visibility, collection_name = pop_sharing_params(request)
        go_async = _pop_async(request)
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return Response(
                {"error": {"message": "`prompt` is required.", "type": "missing_prompt"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(prompt) > settings.IMAGE_MAX_PROMPT_CHARS:
            return Response(
                {"error": {"message": "Prompt too long.", "type": "request_too_large"}},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        model_name = body.get("model")
        provider_model = _find_provider_for_model(
            request.user, model_name, service_type="video"
        )
        if provider_model is None:
            return Response(
                {
                    "error": {
                        "message": f"No online video-generation provider serving model "
                        f"'{model_name}' for this user.",
                        "type": "no_provider",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        provider = provider_model.provider
        served_name = provider_model.name
        canonical = _model_slug(provider_model)

        def _num(val, lo, hi, default):
            try:
                n = float(val)
            except (TypeError, ValueError):
                return default
            return max(lo, min(hi, n))

        def _int(val, lo, hi, default):
            v = _num(val, lo, hi, default)
            return int(v) if v is not None else None

        # --- generation controls, coerced to LTX's safe ranges -------------
        negative_prompt = body.get("negative_prompt")
        negative_prompt = negative_prompt.strip() if isinstance(negative_prompt, str) else ""
        image = body.get("image") if isinstance(body.get("image"), str) else ""
        image_strength = _num(body.get("image_strength"), 0.0, 1.0, 1.0)
        duration = body.get("duration")
        duration = _num(duration, 1, 20, None) if duration is not None else None
        num_frames = (
            _int(body.get("num_frames"), 1, 1281, None)
            if body.get("num_frames") is not None
            else None
        )
        fps = _num(body.get("fps"), 1, 60, None) if body.get("fps") is not None else None
        width = _int(body.get("width"), 64, 1920, None) if body.get("width") is not None else None
        height = _int(body.get("height"), 64, 1920, None) if body.get("height") is not None else None
        steps = (
            _int(body.get("num_inference_steps"), 1, 100, None)
            if body.get("num_inference_steps") is not None
            else None
        )
        guidance = (
            _num(body.get("guidance_scale"), 0, 30, None)
            if body.get("guidance_scale") is not None
            else None
        )
        enhance_prompt = bool(body.get("enhance_prompt"))
        try:
            seed = int(body.get("seed"))
        except (TypeError, ValueError):
            seed = None

        # The LTX /generate request shape. The agent forwards this body verbatim
        # to the upstream server's POST /generate and streams the MP4 back.
        forward = {"prompt": prompt, "enhance_prompt": enhance_prompt}
        if served_name or canonical or model_name:
            forward["model"] = served_name or canonical or model_name
        if negative_prompt:
            forward["negative_prompt"] = negative_prompt
        if image:
            forward["image"] = image
            forward["image_strength"] = image_strength
        if duration is not None:
            forward["duration"] = duration
        if num_frames is not None:
            forward["num_frames"] = num_frames
        if fps is not None:
            forward["fps"] = fps
        if width is not None:
            forward["width"] = width
        if height is not None:
            forward["height"] = height
        if steps is not None:
            forward["num_inference_steps"] = steps
        if guidance is not None:
            forward["guidance_scale"] = guidance
        if seed is not None:
            forward["seed"] = seed

        stored_payload = {
            # Stored so a retry / "reproduce in playground" is faithful. The
            # (potentially large) base64 image is NOT stored here — the
            # persisted INPUT_IMAGE asset is the source of truth for replay.
            "model": canonical or model_name or "",
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "has_image": bool(image),
            "image_strength": image_strength if image else None,
            "duration": duration,
            "num_frames": num_frames,
            "fps": fps,
            "width": width,
            "height": height,
            "num_inference_steps": steps,
            "guidance_scale": guidance,
            "enhance_prompt": enhance_prompt,
            "seed": seed,
        }

        def _store_first_frame(target):
            """Persist the optional first-frame image (public, like outputs) so
            the image-to-video run is replayable and its share link unfurls."""
            if not image:
                return
            from django.core.files.base import ContentFile

            from .models import MediaAsset

            raw_img, img_ct = _decode_image_input(image)
            if not raw_img:
                return
            try:
                src = MediaAsset(
                    user=request.user, inference_request=target,
                    kind=MediaAsset.INPUT_IMAGE,
                    content_type=img_ct or "image/png", size_bytes=len(raw_img),
                )
                ext = (img_ct or "image/png").rsplit("/", 1)[-1] or "png"
                src.file.save(f"first-frame.{ext}", ContentFile(raw_img), save=False)
                src.save()
            except Exception as e:
                logger.warning("video input-image store failed: %s", e)

        if go_async:
            from . import jobs as _jobs
            from .job_views import accepted

            if not _jobs.async_enabled():
                return Response(
                    {"error": {"message": "Async processing is not enabled.",
                               "type": "async_disabled"}},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            job = _jobs.enqueue_job(
                request.user, self.inference_type, stored_payload,
                model_name=canonical or model_name or "",
                visibility=visibility or "", collection_name=collection_name,
                idempotency_key=request.headers.get("Idempotency-Key", "") or "",
            )
            _store_first_frame(job)  # so image-to-video can run from the queue
            return accepted(job)

        ir = InferenceRequest.objects.create(
            user=request.user,
            provider=provider,
            model_name=canonical or model_name or "",
            inference_type="VIDEO",
            payload=stored_payload,
            status="PROCESSING",
            visibility=visibility or "",
        )
        file_into_collection(request.user, ir, collection_name)
        _store_first_frame(ir)

        endpoint = provider.tailnet_base_url.rstrip("/") + self.upstream_path
        started = time.monotonic()
        try:
            upstream = requests.post(
                endpoint, json=forward, timeout=UPSTREAM_TIMEOUT_SECONDS,
                verify=False, proxies=_tailnet_proxies(),
            )
        except requests.RequestException as e:
            ir.status = "REQUESTED"
            ir.results = {"error": str(e)}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            logger.error("Upstream video generation failed: %s", e)
            return Response(
                {"error": {"message": str(e), "type": "upstream_error"}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not upstream.ok:
            err_text = (upstream.text or "")[:1000]
            ir.status = "REQUESTED"
            ir.results = {"upstream_status": upstream.status_code, "error": err_text}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            return Response(
                upstream.json()
                if upstream.headers.get("content-type", "").startswith("application/json")
                else {"error": {"message": err_text, "type": "upstream_error"}},
                status=upstream.status_code,
            )

        video = upstream.content
        out_ct = (upstream.headers.get("content-type") or "video/mp4").split(";", 1)[0]
        resolved = _ltx_params(upstream)
        # Duration: prefer the resolved frame count / fps the server actually
        # used, falling back to the requested duration.
        r_frames = resolved.get("num_frames")
        r_fps = resolved.get("fps")
        if isinstance(r_frames, (int, float)) and isinstance(r_fps, (int, float)) and r_fps:
            seconds = round(r_frames / float(r_fps), 3)
        else:
            seconds = duration

        from django.core.files.base import ContentFile

        from .models import MediaAsset

        asset = None
        try:
            asset = MediaAsset(
                user=request.user, inference_request=ir, kind=MediaAsset.OUTPUT_VIDEO,
                content_type=out_ct, size_bytes=len(video), duration_seconds=seconds,
                metadata={k: resolved[k] for k in ("width", "height", "fps", "num_frames")
                          if isinstance(resolved.get(k), (int, float))},
            )
            asset.file.save("video.mp4", ContentFile(video), save=False)
            asset.save()
        except Exception as e:
            logger.warning("video output store failed: %s", e)

        ir.status = "PROCESSED"
        ir.audio_seconds = seconds  # reused as the duration meter for video
        ir.results = {
            "video_asset_id": asset.id if asset else None,
            "content_type": out_ct,
            "duration": seconds,
            "params": resolved or None,
        }
        ir.latency_ms = int((time.monotonic() - started) * 1000)
        ir.save(
            update_fields=["status", "audio_seconds", "results", "latency_ms", "modified_on"]
        )
        Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())

        from django.http import HttpResponse

        resp = HttpResponse(video, content_type=out_ct)
        resp["Content-Disposition"] = 'inline; filename="video.mp4"'
        return resp


class AudioVoicesView(_RateLimitHeadersMixin, APIView):
    """``GET /v1/audio/voices?model=<id>`` — the voices a TTS model offers.

    An inference.club extension (not in OpenAI's API) that proxies the
    provider's Riva ``list_voices`` so the playground can populate a dropdown
    that matches what the NIM actually serves.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "models"

    def get(self, request):
        model_name = request.query_params.get("model")
        provider_model = _find_provider_for_model(
            request.user, model_name, service_type="tts"
        )
        if provider_model is None:
            return Response(
                {"error": {"message": "No text-to-speech model found.", "type": "no_provider"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        endpoint = provider_model.provider.tailnet_base_url.rstrip("/") + "/audio/list_voices"
        try:
            upstream = requests.get(
                endpoint, timeout=30, verify=False, proxies=_tailnet_proxies()
            )
            upstream.raise_for_status()
            data = upstream.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning("list_voices failed: %s", e)
            return Response(
                {"error": {"message": "Could not load voices.", "type": "upstream_error"}},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"voices": _flatten_voices(data)})


class ImageGenerationsView(_ImageProxyBase):
    """``POST /v1/images/generations`` — OpenAI-compatible text-to-image."""

    upstream_path = "/images/generations"

    def post(self, request):
        body = request.data
        if not isinstance(body, dict):
            return Response(
                {"error": {"message": "JSON body required.", "type": "invalid_request"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Popped before `forward = dict(body)` below so the copy is clean.
        visibility, collection_name = pop_sharing_params(request)
        go_async = _pop_async(request)
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return Response(
                {"error": {"message": "`prompt` is required.", "type": "missing_prompt"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(prompt) > settings.IMAGE_MAX_PROMPT_CHARS:
            return Response(
                {"error": {"message": "Prompt too long.", "type": "request_too_large"}},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        model_name = body.get("model")
        provider_model = _find_provider_for_model(
            request.user, model_name, service_type="image"
        )
        if provider_model is None:
            return self._no_provider(model_name)

        provider = provider_model.provider
        served_name = provider_model.name
        canonical = _model_slug(provider_model)
        requested_format = body.get("response_format") or "url"

        n_in = body.get("n")
        if isinstance(n_in, int) and n_in > settings.IMAGE_MAX_N:
            n_in = settings.IMAGE_MAX_N
        stored_payload = {
            "model": canonical or model_name or "",
            "prompt": prompt,
            "n": n_in,
            "size": body.get("size"),
            "quality": body.get("quality"),
            "response_format": requested_format,
        }
        if go_async:
            return _enqueue_async(
                request, self.inference_type, stored_payload,
                visibility, collection_name, model_name=canonical or model_name or "",
            )

        # Forward a copy: force b64_json (the only thing the server returns and
        # what we need to store), rewrite the model id, clamp n.
        forward = dict(body)
        forward["response_format"] = "b64_json"
        if served_name:
            forward["model"] = served_name
        if n_in is not None:
            forward["n"] = n_in

        ir = InferenceRequest.objects.create(
            user=request.user,
            provider=provider,
            model_name=canonical or model_name or "",
            inference_type="IMAGE",
            payload=stored_payload,
            status="PROCESSING",
            visibility=visibility or "",
        )
        file_into_collection(request.user, ir, collection_name)

        endpoint = provider.tailnet_base_url.rstrip("/") + self.upstream_path
        started = time.monotonic()
        try:
            upstream = requests.post(
                endpoint, json=forward, timeout=UPSTREAM_TIMEOUT_SECONDS,
                verify=False, proxies=_tailnet_proxies(),
            )
        except requests.RequestException as e:
            return self._forward_error(ir, started, e)
        return self._finalize(request, ir, upstream, started, requested_format)


class ImageEditsView(_ImageProxyBase):
    """``POST /v1/images/edits`` — edit a source image with a prompt
    (multipart: image + prompt, optional mask)."""

    upstream_path = "/images/edits"

    def post(self, request):
        upload = request.FILES.get("image")
        if upload is None:
            return Response(
                {"error": {"message": "`image` file is required.", "type": "missing_file"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size and upload.size > settings.IMAGE_MAX_UPLOAD_BYTES:
            return Response(
                {"error": {"message": "Image too large.", "type": "file_too_large"}},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        ctype = (upload.content_type or "").split(";", 1)[0].strip().lower()
        if ctype and ctype not in settings.IMAGE_ALLOWED_CONTENT_TYPES:
            return Response(
                {"error": {"message": f"Unsupported image type: {ctype!r}.",
                           "type": "unsupported_media_type"}},
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )
        prompt = request.data.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return Response(
                {"error": {"message": "`prompt` is required.", "type": "missing_prompt"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        visibility, collection_name = pop_sharing_params(request)

        model_name = request.data.get("model")
        provider_model = _find_provider_for_model(
            request.user, model_name, service_type="image"
        )
        if provider_model is None:
            return self._no_provider(model_name)

        provider = provider_model.provider
        served_name = provider_model.name
        canonical = _model_slug(provider_model)
        requested_format = request.data.get("response_format") or "url"

        image_bytes = upload.read()
        mask = request.FILES.get("mask")
        mask_bytes = mask.read() if mask is not None else None

        ir = InferenceRequest.objects.create(
            user=request.user,
            provider=provider,
            model_name=canonical or model_name or "",
            inference_type="IMAGE",
            payload={
                "model": canonical or model_name or "",
                "prompt": prompt,
                "size": request.data.get("size"),
                "n": request.data.get("n"),
                "response_format": requested_format,
                "edit": True,
            },
            status="PROCESSING",
            visibility=visibility or "",
        )
        file_into_collection(request.user, ir, collection_name)

        # Store the source image (public, like outputs) so the edit is replayable.
        from django.core.files.base import ContentFile

        from .models import MediaAsset

        try:
            src = MediaAsset(
                user=request.user, inference_request=ir, kind=MediaAsset.INPUT_IMAGE,
                content_type=ctype or "image/png", size_bytes=len(image_bytes),
            )
            src.file.save(getattr(upload, "name", "source.png") or "source.png",
                          ContentFile(image_bytes), save=False)
            src.save()
        except Exception as e:  # storage hiccup shouldn't fail the edit
            logger.warning("input-image store failed: %s", e)

        # Build the multipart forward.
        files = {"image": (getattr(upload, "name", "image.png"), image_bytes,
                           ctype or "application/octet-stream")}
        if mask_bytes is not None:
            files["mask"] = (getattr(mask, "name", "mask.png"), mask_bytes,
                             (mask.content_type or "image/png"))
        data_fields = [("prompt", prompt), ("response_format", "b64_json")]
        if served_name:
            data_fields.append(("model", served_name))
        for key in ("size", "n"):
            v = request.data.get(key)
            if v not in (None, ""):
                if key == "n":
                    try:
                        v = str(min(int(v), settings.IMAGE_MAX_N))
                    except (TypeError, ValueError):
                        continue
                data_fields.append((key, v))

        endpoint = provider.tailnet_base_url.rstrip("/") + self.upstream_path
        started = time.monotonic()
        try:
            upstream = requests.post(
                endpoint, files=files, data=data_fields,
                timeout=UPSTREAM_TIMEOUT_SECONDS, verify=False, proxies=_tailnet_proxies(),
            )
        except requests.RequestException as e:
            return self._forward_error(ir, started, e)
        return self._finalize(request, ir, upstream, started, requested_format)


# --- web scrape (URL → markdown) -------------------------------------------


class ScrapeView(_RateLimitHeadersMixin, APIView):
    """``POST /v1/scrape`` — fetch a URL and return clean markdown (Firecrawl).

    A "high-level" inference modality: the provider's scrape service crawls the
    page and uses an LLM under the hood for clean extraction. The agent returns
    the markdown, which we persist as an OUTPUT_DOC asset so workflows (the
    ``scrape`` node) can chain it into a dialog/summary step. Body: ``{"url":
    "...", "model": "firecrawl"}`` (+ optional ``async``). See PRD 12.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "inference"
    inference_type = "SCRAPE"

    def post(self, request):
        body = request.data
        if not isinstance(body, dict):
            return Response(
                {"error": {"message": "JSON body required.", "type": "invalid_request"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        visibility, collection_name = pop_sharing_params(request)
        go_async = _pop_async(request)
        url = body.get("url")
        if not isinstance(url, str) or not url.strip():
            return Response(
                {"error": {"message": "`url` is required.", "type": "missing_url"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        url = url.strip()

        model_name = body.get("model")
        provider_model = _find_provider_for_model(
            request.user, model_name, service_type="scrape"
        )
        if provider_model is None:
            return Response(
                {"error": {"message": (
                    f"No online web-scrape provider serving model "
                    f"'{model_name}' for this user."), "type": "no_provider"}},
                status=status.HTTP_404_NOT_FOUND,
            )

        provider = provider_model.provider
        canonical = _model_slug(provider_model)
        stored_payload = {"model": canonical or model_name or "", "url": url}

        if go_async:
            return _enqueue_async(
                request, self.inference_type, stored_payload,
                visibility, collection_name, model_name=canonical or model_name or "",
            )

        ir = InferenceRequest.objects.create(
            user=request.user, provider=provider,
            model_name=canonical or model_name or "",
            inference_type="SCRAPE", payload=stored_payload,
            status="PROCESSING", visibility=visibility or "",
        )
        file_into_collection(request.user, ir, collection_name)

        ok, err = _run_scrape(ir, provider, url, time.monotonic())
        if not ok:
            return Response(
                {"error": {"message": err or "scrape failed", "type": "upstream_error"}},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        r = ir.results or {}
        return Response(
            {
                "request_id": str(ir.id),
                "markdown": r.get("markdown", ""),
                "title": r.get("title", ""),
                "source_url": r.get("source_url", url),
                "doc_asset_id": r.get("doc_asset_id"),
                "chars": r.get("chars", 0),
            },
            status=status.HTTP_200_OK,
        )


# --- video compose (central FFmpeg render) ---------------------------------


class ComposeView(_RateLimitHeadersMixin, APIView):
    """``POST /v1/videos/compose`` — assemble a narrated slideshow MP4 from
    per-section image + audio assets (PRD 12 §5.5). Rendered centrally on the
    worker with FFmpeg — *not* on a provider cluster — so it always runs as an
    async job. Body: ``{"images": [asset_id…], "audio": [asset_id…]}`` (the
    workflow ``compose`` node passes the upstream steps' outputs, which carry
    the same asset ids). An optional ``captions`` list (strings or section
    dicts, aligned to the sections) is burned in over each clip, and an optional
    ``music`` asset is ducked under the narration as a music bed (V4). Returns
    the queued job (202)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "inference"
    inference_type = "RENDER"

    def post(self, request):
        from . import workflows

        body = request.data
        if not isinstance(body, dict):
            return Response(
                {"error": {"message": "JSON body required.", "type": "invalid_request"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        visibility, collection_name = pop_sharing_params(request)
        _pop_async(request)  # compose is always async; strip the flag if present

        image_ids = workflows._extract_asset_ids(body.get("images"))
        audio_ids = workflows._extract_asset_ids(body.get("audio"))
        if not image_ids or not audio_ids:
            return Response(
                {"error": {"message": (
                    "`images` and `audio` must be non-empty lists of asset ids."),
                    "type": "invalid_request"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = {"images": image_ids, "audio": audio_ids}
        captions = body.get("captions")
        if isinstance(captions, list) and captions:
            payload["captions"] = captions
        music_ids = workflows._extract_asset_ids(body.get("music"))
        if music_ids:
            payload["music"] = music_ids
        return _enqueue_async(
            request, self.inference_type, payload, visibility, collection_name,
        )


# --- image-to-3D (mesh) ----------------------------------------------------

# Valid TRELLIS.2 render resolutions: 512 (fast) · 1024 · 1536 (sharpest).
MESH_RESOLUTIONS = {"512", "1024", "1536"}


def _coerce_mesh_options(raw):
    """Validate & whitelist the client's ``options`` JSON for a mesh request.

    Returns ``(options_dict, error_message)``. The error is a string when the
    options are malformed (the caller turns it into a 400), else None. Only the
    knobs we expose pass through; ``formats`` is always forced to GLB (our
    canonical artifact) and ``response_mode`` is left to the agent.
    """
    opts = {"formats": ["glb"]}
    if raw in (None, ""):
        return opts, None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None, "`options` was not valid JSON."
    if not isinstance(raw, dict):
        return None, "`options` must be a JSON object."

    if "resolution" in raw and raw["resolution"] is not None:
        res = str(raw["resolution"])
        if res not in MESH_RESOLUTIONS:
            return None, f"resolution must be one of {sorted(MESH_RESOLUTIONS)}."
        opts["resolution"] = res
    if raw.get("randomize_seed"):
        opts["randomize_seed"] = True
    if "seed" in raw and raw["seed"] is not None:
        try:
            opts["seed"] = int(raw["seed"])
        except (TypeError, ValueError):
            return None, "seed must be an integer."
    if "texture_size" in raw and raw["texture_size"] is not None:
        try:
            ts = int(raw["texture_size"])
        except (TypeError, ValueError):
            return None, "texture_size must be an integer."
        if not (512 <= ts <= 4096):
            return None, "texture_size must be between 512 and 4096."
        opts["texture_size"] = ts
    return opts, None


def _parse_trellis_metadata(header_value):
    """Parse the ``X-Trellis-Metadata`` response header (seed, vertices, faces,
    timing). Returns a dict (possibly empty) — never raises."""
    if not header_value:
        return {}
    try:
        meta = json.loads(header_value)
    except (ValueError, TypeError):
        return {}
    return meta if isinstance(meta, dict) else {}


class Mesh3DGenerationsView(_RateLimitHeadersMixin, APIView):
    """``POST /v1/3d/generations`` — image-to-3D (multipart: ``image`` +
    optional ``options`` JSON string). Routes only to ``mesh`` services
    (e.g. TRELLIS.2): one image in, a textured GLB out.

    The agent speaks the same multipart shape upstream and returns the raw GLB
    bytes plus generation metadata in the ``X-Trellis-Metadata`` header. We
    store the GLB as an ``OUTPUT_MODEL`` asset (and the source as
    ``INPUT_IMAGE``), then hand the client a JSON manifest with the stored
    model URL — the dashboard loads that straight into a three.js viewer.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "inference"
    upstream_path = "/3d/generations"

    def _no_provider(self, model_name):
        return Response(
            {"error": {"message": (
                f"No online image-to-3D provider serving model '{model_name}' "
                "for this user. Run an agent with a service of type: mesh."),
                "type": "no_provider"}},
            status=status.HTTP_404_NOT_FOUND,
        )

    def post(self, request):
        upload = request.FILES.get("image")
        if upload is None:
            return Response(
                {"error": {"message": "`image` file is required.", "type": "missing_file"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size and upload.size > settings.IMAGE_MAX_UPLOAD_BYTES:
            return Response(
                {"error": {"message": "Image too large.", "type": "file_too_large"}},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        ctype = (upload.content_type or "").split(";", 1)[0].strip().lower()
        if ctype and ctype not in settings.IMAGE_ALLOWED_CONTENT_TYPES:
            return Response(
                {"error": {"message": f"Unsupported image type: {ctype!r}.",
                           "type": "unsupported_media_type"}},
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )

        visibility, collection_name = pop_sharing_params(request)
        options, opt_err = _coerce_mesh_options(request.data.get("options"))
        if opt_err is not None:
            return Response(
                {"error": {"message": opt_err, "type": "invalid_options"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        model_name = request.data.get("model")
        provider_model = _find_provider_for_model(
            request.user, model_name, service_type="mesh"
        )
        if provider_model is None:
            return self._no_provider(model_name)

        provider = provider_model.provider
        served_name = provider_model.name
        canonical = _model_slug(provider_model)
        image_bytes = upload.read()

        ir = InferenceRequest.objects.create(
            user=request.user,
            provider=provider,
            model_name=canonical or model_name or "",
            inference_type="MESH",
            payload={
                "model": canonical or model_name or "",
                "options": options,
                "source_filename": getattr(upload, "name", "input.png"),
            },
            status="PROCESSING",
            visibility=visibility or "",
        )
        file_into_collection(request.user, ir, collection_name)

        from django.core.files.base import ContentFile

        from .models import MediaAsset

        # Store the source image (public, like outputs) so every surface can
        # show "the image that became this model" and the run is replayable.
        try:
            src = MediaAsset(
                user=request.user, inference_request=ir, kind=MediaAsset.INPUT_IMAGE,
                content_type=ctype or "image/png", size_bytes=len(image_bytes),
            )
            src.file.save(getattr(upload, "name", "source.png") or "source.png",
                          ContentFile(image_bytes), save=False)
            src.save()
        except Exception as e:  # storage hiccup shouldn't fail the generation
            logger.warning("mesh input-image store failed: %s", e)

        files = {"image": (getattr(upload, "name", "image.png"), image_bytes,
                           ctype or "application/octet-stream")}
        data_fields = [("options", json.dumps(options))]
        if served_name:
            data_fields.append(("model", served_name))

        endpoint = provider.tailnet_base_url.rstrip("/") + self.upstream_path
        started = time.monotonic()
        try:
            upstream = requests.post(
                endpoint, files=files, data=data_fields,
                timeout=UPSTREAM_TIMEOUT_SECONDS, verify=False, proxies=_tailnet_proxies(),
            )
        except requests.RequestException as e:
            ir.status = "REQUESTED"
            ir.results = {"error": str(e)}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            logger.error("Upstream mesh request failed: %s", e)
            return Response(
                {"error": {"message": str(e), "type": "upstream_error"}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not upstream.ok:
            ir.status = "REQUESTED"
            ir.results = {"upstream_status": upstream.status_code}
            ir.latency_ms = int((time.monotonic() - started) * 1000)
            ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
            return Response(
                upstream.json()
                if upstream.headers.get("content-type", "").startswith("application/json")
                else {"error": upstream.text[:500]},
                status=upstream.status_code,
            )

        glb = upstream.content
        meta = _parse_trellis_metadata(upstream.headers.get("X-Trellis-Metadata"))
        out_ct = (upstream.headers.get("content-type") or "model/gltf-binary").split(";", 1)[0]

        asset = None
        try:
            asset = MediaAsset(
                user=request.user, inference_request=ir, kind=MediaAsset.OUTPUT_MODEL,
                content_type=out_ct or "model/gltf-binary", size_bytes=len(glb),
                metadata=meta,
            )
            asset.file.save("model.glb", ContentFile(glb), save=False)
            asset.save()
        except Exception as e:
            logger.warning("mesh output-model store failed: %s", e)

        ir.status = "PROCESSED"
        ir.results = {
            "model_asset_id": asset.id if asset else None,
            "content_type": out_ct,
            "metadata": meta,
            "options": options,
        }
        ir.latency_ms = int((time.monotonic() - started) * 1000)
        ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
        Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())

        model_url = _asset_url(request, asset) if asset else None
        return Response(
            {
                "created": int(timezone.now().timestamp()),
                "request_id": str(ir.id),
                "metadata": meta,
                "data": [{"url": model_url, "type": "model/gltf-binary"}],
            },
            status=status.HTTP_200_OK,
        )


# ===========================================================================
# Retry: re-run a FAILED inference request *in place*.
#
# A failed request keeps everything needed to run again: its `payload` (the
# original parameters) and, for file inputs (STT/MESH), the stored INPUT_AUDIO /
# INPUT_IMAGE asset. The runners below reconstruct each modality's upstream call
# from that and update the SAME InferenceRequest row, mirroring the forward +
# store logic of the corresponding /v1 view. The live inference views are left
# untouched; this path is purely additive.
# ===========================================================================

# inference_type → routing service_type (None = LLM, no restriction).
_RETRY_SERVICE_TYPE = {
    "LLM": None, "STT": "stt", "TTS": "tts",
    "IMAGE": "image", "MESH": "mesh", "MUSIC": "music", "VIDEO": "video",
    "SCRAPE": "scrape", "RENDER": "render",
}


def _retry_endpoint(provider, path: str) -> str:
    return provider.tailnet_base_url.rstrip("/") + path


def _retry_store_exc(ir, started, exc):
    ir.status = "REQUESTED"
    ir.results = {"error": str(exc)}
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
    logger.error("retry %s upstream failed: %s", ir.inference_type, exc)
    return False, str(exc)


def _retry_store_upstream_error(ir, started, upstream):
    """Persist a non-2xx upstream reply (its text carries the real reason, e.g.
    a provider-side error) so the failed retry is diagnosable."""
    try:
        if upstream.headers.get("content-type", "").startswith("application/json"):
            txt = json.dumps(upstream.json())[:1000]
        else:
            txt = (upstream.text or "")[:1000]
    except Exception:
        txt = (getattr(upstream, "text", "") or "")[:1000]
    ir.status = "REQUESTED"
    ir.results = {"upstream_status": upstream.status_code, "error": txt}
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
    return False, txt or f"Upstream returned HTTP {upstream.status_code}"


def _store_output_doc(user, ir, markdown, *, title="", source_url=""):
    """Persist scraped markdown as an OUTPUT_DOC MediaAsset (PRD 12). The page
    title + source url live in ``metadata``. Returns the asset, or None."""
    from django.core.files.base import ContentFile

    from .models import MediaAsset  # noqa: F811

    raw = (markdown or "").encode("utf-8")
    asset = MediaAsset(
        user=user, inference_request=ir, kind=MediaAsset.OUTPUT_DOC,
        content_type="text/markdown; charset=utf-8", size_bytes=len(raw),
        metadata={"title": title or "", "source_url": source_url or ""},
    )
    asset.file.save("document.md", ContentFile(raw), save=False)
    asset.save()
    return asset


def _run_scrape(ir, provider, url, started):
    """Forward a scrape to the provider agent's ``/scrape``, store the returned
    markdown as an OUTPUT_DOC asset, and finalize ``ir``. The agent replies with
    the extracted markdown as text/markdown plus X-Scrape-Title /
    X-Scrape-Source-Url headers (it tolerates a Firecrawl-shaped JSON too).
    Shared by ScrapeView (sync) and ``_rerun_scrape`` (async/retry). Returns
    ``(ok, error)``."""
    try:
        upstream = requests.post(
            _retry_endpoint(provider, "/scrape"), json={"url": url},
            timeout=UPSTREAM_TIMEOUT_SECONDS, verify=False, proxies=_tailnet_proxies(),
        )
    except requests.RequestException as e:
        return _retry_store_exc(ir, started, e)
    if not upstream.ok:
        return _retry_store_upstream_error(ir, started, upstream)

    ctype = (upstream.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try:
            j = upstream.json()
            d = (j.get("data") or {}) if isinstance(j, dict) else {}
            meta = d.get("metadata") or {}
            markdown = d.get("markdown") or ""
            title = meta.get("title") or ""
            source_url = meta.get("sourceURL") or url
        except ValueError:
            markdown, title, source_url = upstream.text or "", "", url
    else:
        markdown = upstream.text or ""
        title = upstream.headers.get("X-Scrape-Title") or ""
        source_url = upstream.headers.get("X-Scrape-Source-Url") or url

    asset = None
    try:
        asset = _store_output_doc(ir.user, ir, markdown, title=title, source_url=source_url)
    except Exception as e:
        logger.warning("scrape: doc store failed: %s", e)

    ir.status = "PROCESSED"
    ir.results = {
        "markdown": markdown,
        "doc_asset_id": asset.id if asset else None,
        "title": title,
        "source_url": source_url,
        "chars": len(markdown),
    }
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
    Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())
    return True, None


def _rerun_scrape(ir, provider_model):
    url = (ir.payload or {}).get("url") or ""
    if not url:
        return _retry_simple_fail(ir, "No URL stored for this scrape request.")
    return _run_scrape(ir, provider_model.provider, url, time.monotonic())


def _rerun_render(ir, provider_model):
    """RENDER (compose) runner — central FFmpeg, no provider. ``provider_model``
    is None (the dispatcher claims RENDER jobs centrally; see jobs.CENTRAL_TYPES)."""
    from . import render

    return render.run_render_job(ir)


def _retry_read_input_asset(ir, kind):
    """Bytes + content-type of the request's stored input asset of ``kind``
    (INPUT_AUDIO / INPUT_IMAGE), or (None, None) if it wasn't kept."""
    from .models import MediaAsset  # noqa: F811

    a = ir.assets.filter(kind=kind).order_by("created_on").first()
    if a is None or not a.file:
        return None, None
    try:
        with a.file.open("rb") as f:
            return f.read(), (a.content_type or "")
    except Exception as e:
        logger.warning("retry: reading input asset failed: %s", e)
        return None, None


def _retry_save_output_audio(ir, audio, out_ct, ext, seconds):
    from django.core.files.base import ContentFile

    from .models import MediaAsset  # noqa: F811

    asset = None
    try:
        asset = MediaAsset(
            user=ir.user, inference_request=ir, kind=MediaAsset.OUTPUT_AUDIO,
            content_type=out_ct, size_bytes=len(audio), duration_seconds=seconds,
        )
        asset.file.save(f"output.{ext}", ContentFile(audio), save=False)
        asset.save()
    except Exception as e:
        logger.warning("retry: output-audio store failed: %s", e)
    return asset


def _rerun_llm(ir, provider_model):
    provider = provider_model.provider
    body = dict(ir.payload or {})
    body["model"] = provider_model.name or body.get("model") or ir.model_name
    body["stream"] = False  # retries are always buffered
    path = "/chat/completions" if "messages" in body else "/completions"
    started = time.monotonic()
    try:
        upstream = requests.post(
            _retry_endpoint(provider, path), json=body,
            timeout=UPSTREAM_TIMEOUT_SECONDS, verify=False, proxies=_tailnet_proxies(),
        )
    except requests.RequestException as e:
        return _retry_store_exc(ir, started, e)
    if not upstream.ok:
        return _retry_store_upstream_error(ir, started, upstream)
    try:
        data = upstream.json()
    except ValueError:
        data = {"raw": upstream.text}
    ir.status = "PROCESSED"
    ir.results = data
    ir.prompt_tokens, ir.completion_tokens, ir.total_tokens = _usage_tokens(data)
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=[
        "status", "results", "prompt_tokens", "completion_tokens",
        "total_tokens", "latency_ms", "modified_on",
    ])
    Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())
    return True, None


def _rerun_stt(ir, provider_model):
    from .models import MediaAsset  # noqa: F811

    provider = provider_model.provider
    audio, ctype = _retry_read_input_asset(ir, MediaAsset.INPUT_AUDIO)
    if audio is None:
        return _retry_simple_fail(
            ir, "The original audio wasn't stored, so this transcription can't be retried."
        )
    p = ir.payload or {}
    caps = _model_caps(provider_model)
    supports_ts = "timestamps" in (caps.get("supported_features") or [])
    requested_format = p.get("response_format") or "json"
    fmt = requested_format
    if fmt == "verbose_json" and not supports_ts:
        fmt = "json"
    data_fields = [("model", provider_model.name or p.get("model") or ir.model_name),
                   ("response_format", fmt)]
    if p.get("language"):
        data_fields.append(("language", p["language"]))
    if p.get("prompt"):
        data_fields.append(("prompt", p["prompt"]))
    started = time.monotonic()
    try:
        upstream = requests.post(
            _retry_endpoint(provider, "/audio/transcriptions"),
            files={"file": (p.get("filename") or "audio", audio, ctype or "application/octet-stream")},
            data=data_fields,
            timeout=UPSTREAM_TIMEOUT_SECONDS, verify=False, proxies=_tailnet_proxies(),
        )
    except requests.RequestException as e:
        return _retry_store_exc(ir, started, e)
    if not upstream.ok:
        return _retry_store_upstream_error(ir, started, upstream)
    try:
        payload = upstream.json()
    except ValueError:
        payload = {"text": upstream.text}
    ir.status = "PROCESSED"
    ir.results = payload
    ir.audio_seconds = _audio_seconds(payload)
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=["status", "results", "audio_seconds", "latency_ms", "modified_on"])
    Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())
    return True, None


def _rerun_tts(ir, provider_model):
    provider = provider_model.provider
    p = ir.payload or {}
    text = p.get("input") or ""
    voice = p.get("voice") or settings.TTS_DEFAULT_VOICE
    language = p.get("language") or settings.TTS_DEFAULT_LANGUAGE
    requested_format = p.get("response_format") or "wav"
    encoding, content_type, ext = _riva_encoding(requested_format)
    fields = {
        "text": (None, text),
        "language": (None, language),
        "voice": (None, voice),
        "sample_rate_hz": (None, str(settings.TTS_DEFAULT_SAMPLE_RATE)),
        "encoding": (None, encoding),
    }
    started = time.monotonic()
    try:
        upstream = requests.post(
            _retry_endpoint(provider, "/audio/synthesize"), files=fields,
            timeout=UPSTREAM_TIMEOUT_SECONDS, verify=False, proxies=_tailnet_proxies(),
        )
    except requests.RequestException as e:
        return _retry_store_exc(ir, started, e)
    if not upstream.ok:
        return _retry_store_upstream_error(ir, started, upstream)
    audio = upstream.content
    out_ct = upstream.headers.get("content-type") or content_type
    seconds = _wav_seconds(audio)
    asset = _retry_save_output_audio(ir, audio, out_ct, ext, seconds)
    ir.status = "PROCESSED"
    ir.audio_seconds = seconds
    ir.results = {"audio_asset_id": asset.id if asset else None,
                  "content_type": out_ct, "voice": voice, "characters": len(text)}
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=["status", "audio_seconds", "results", "latency_ms", "modified_on"])
    Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())
    return True, None


def _rerun_image(ir, provider_model):
    provider = provider_model.provider
    p = ir.payload or {}
    requested_format = p.get("response_format") or "url"
    forward = {
        "model": provider_model.name or p.get("model") or ir.model_name,
        "prompt": p.get("prompt") or "",
        "response_format": "b64_json",
    }
    if p.get("n") is not None:
        forward["n"] = p["n"]
    if p.get("size"):
        forward["size"] = p["size"]
    if p.get("quality"):
        forward["quality"] = p["quality"]
    started = time.monotonic()
    try:
        upstream = requests.post(
            _retry_endpoint(provider, "/images/generations"), json=forward,
            timeout=UPSTREAM_TIMEOUT_SECONDS, verify=False, proxies=_tailnet_proxies(),
        )
    except requests.RequestException as e:
        return _retry_store_exc(ir, started, e)
    if not upstream.ok:
        return _retry_store_upstream_error(ir, started, upstream)
    try:
        payload = upstream.json()
    except ValueError:
        payload = {}
    data = payload.get("data") if isinstance(payload, dict) else None
    asset_ids = []
    for i, item in enumerate(data or []):
        if not isinstance(item, dict):
            continue
        b64 = item.get("b64_json")
        asset = _store_output_image(ir.user, ir, b64, i) if b64 else None
        if asset is not None:
            asset_ids.append(asset.id)
    ir.status = "PROCESSED"
    ir.image_count = len(asset_ids)
    ir.results = {
        "created": payload.get("created") if isinstance(payload, dict) else None,
        "image_asset_ids": asset_ids, "count": len(asset_ids),
    }
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=["status", "image_count", "results", "latency_ms", "modified_on"])
    Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())
    return True, None


def _rerun_mesh(ir, provider_model):
    from django.core.files.base import ContentFile

    from .models import MediaAsset  # noqa: F811

    provider = provider_model.provider
    image, ctype = _retry_read_input_asset(ir, MediaAsset.INPUT_IMAGE)
    if image is None:
        return _retry_simple_fail(
            ir, "The original image wasn't stored, so this 3D generation can't be retried."
        )
    p = ir.payload or {}
    options = p.get("options") or {}
    files = {"image": (p.get("source_filename") or "image.png", image, ctype or "application/octet-stream")}
    data_fields = [("options", json.dumps(options))]
    if provider_model.name:
        data_fields.append(("model", provider_model.name))
    started = time.monotonic()
    try:
        upstream = requests.post(
            _retry_endpoint(provider, "/3d/generations"), files=files, data=data_fields,
            timeout=UPSTREAM_TIMEOUT_SECONDS, verify=False, proxies=_tailnet_proxies(),
        )
    except requests.RequestException as e:
        return _retry_store_exc(ir, started, e)
    if not upstream.ok:
        return _retry_store_upstream_error(ir, started, upstream)
    glb = upstream.content
    meta = _parse_trellis_metadata(upstream.headers.get("X-Trellis-Metadata"))
    out_ct = (upstream.headers.get("content-type") or "model/gltf-binary").split(";", 1)[0]
    asset = None
    try:
        asset = MediaAsset(
            user=ir.user, inference_request=ir, kind=MediaAsset.OUTPUT_MODEL,
            content_type=out_ct or "model/gltf-binary", size_bytes=len(glb), metadata=meta,
        )
        asset.file.save("model.glb", ContentFile(glb), save=False)
        asset.save()
    except Exception as e:
        logger.warning("retry: mesh output store failed: %s", e)
    ir.status = "PROCESSED"
    ir.results = {"model_asset_id": asset.id if asset else None,
                  "content_type": out_ct, "metadata": meta, "options": options}
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])
    Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())
    return True, None


def _rerun_music(ir, provider_model):
    provider = provider_model.provider
    p = ir.payload or {}
    audio_format = str(p.get("audio_format") or "mp3").lower()
    out_ct_fallback, ext = _MUSIC_FORMATS.get(audio_format, _MUSIC_FORMATS["mp3"])
    forward = {
        "model": provider_model.name or p.get("model") or ir.model_name,
        "prompt": p.get("prompt") or "",
        "lyrics": p.get("lyrics") or "",
        "inference_steps": p.get("inference_steps") or 8,
        "guidance_scale": p.get("guidance_scale") if p.get("guidance_scale") is not None else 7.0,
        "use_random_seed": p.get("use_random_seed", True),
        "seed": p.get("seed", -1),
        "audio_format": audio_format,
        "task_type": "text2music",
    }
    duration = p.get("audio_duration")
    if duration is not None:
        forward["audio_duration"] = duration
    if isinstance(p.get("bpm"), (int, float)):
        forward["bpm"] = int(p["bpm"])
    if isinstance(p.get("key_scale"), str) and p["key_scale"].strip():
        forward["key_scale"] = p["key_scale"].strip()
    started = time.monotonic()
    try:
        upstream = requests.post(
            _retry_endpoint(provider, "/music/generations"), json=forward,
            timeout=UPSTREAM_TIMEOUT_SECONDS, verify=False, proxies=_tailnet_proxies(),
        )
    except requests.RequestException as e:
        return _retry_store_exc(ir, started, e)
    if not upstream.ok:
        return _retry_store_upstream_error(ir, started, upstream)
    audio = upstream.content
    out_ct = (upstream.headers.get("content-type") or out_ct_fallback).split(";", 1)[0]
    seconds = _wav_seconds(audio) or duration
    asset = _retry_save_output_audio(ir, audio, out_ct, ext, seconds)
    ir.status = "PROCESSED"
    ir.audio_seconds = seconds
    ir.results = {"audio_asset_id": asset.id if asset else None,
                  "content_type": out_ct, "characters": len(forward["prompt"]) + len(forward["lyrics"])}
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=["status", "audio_seconds", "results", "latency_ms", "modified_on"])
    Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())
    return True, None


def _rerun_video(ir, provider_model):
    import base64

    from .models import MediaAsset  # noqa: F811

    provider = provider_model.provider
    p = ir.payload or {}
    forward = {
        "model": provider_model.name or p.get("model") or ir.model_name,
        "prompt": p.get("prompt") or "",
        "enhance_prompt": bool(p.get("enhance_prompt")),
    }
    if p.get("negative_prompt"):
        forward["negative_prompt"] = p["negative_prompt"]
    if p.get("has_image"):
        image, ctype = _retry_read_input_asset(ir, MediaAsset.INPUT_IMAGE)
        if image is None:
            return _retry_simple_fail(
                ir, "The original first-frame image wasn't stored, so this video can't be retried."
            )
        forward["image"] = f"data:{ctype or 'image/png'};base64,{base64.b64encode(image).decode('ascii')}"
        if p.get("image_strength") is not None:
            forward["image_strength"] = p["image_strength"]
    for key in ("duration", "num_frames", "fps", "width", "height",
                "num_inference_steps", "guidance_scale", "seed"):
        if p.get(key) is not None:
            forward[key] = p[key]
    started = time.monotonic()
    try:
        upstream = requests.post(
            _retry_endpoint(provider, "/videos/generations"), json=forward,
            timeout=UPSTREAM_TIMEOUT_SECONDS, verify=False, proxies=_tailnet_proxies(),
        )
    except requests.RequestException as e:
        return _retry_store_exc(ir, started, e)
    if not upstream.ok:
        return _retry_store_upstream_error(ir, started, upstream)
    video = upstream.content
    out_ct = (upstream.headers.get("content-type") or "video/mp4").split(";", 1)[0]
    resolved = _ltx_params(upstream)
    r_frames, r_fps = resolved.get("num_frames"), resolved.get("fps")
    if isinstance(r_frames, (int, float)) and isinstance(r_fps, (int, float)) and r_fps:
        seconds = round(r_frames / float(r_fps), 3)
    else:
        seconds = p.get("duration")
    asset = None
    try:
        asset = MediaAsset(
            user=ir.user, inference_request=ir, kind=MediaAsset.OUTPUT_VIDEO,
            content_type=out_ct, size_bytes=len(video), duration_seconds=seconds,
            metadata={k: resolved[k] for k in ("width", "height", "fps", "num_frames")
                      if isinstance(resolved.get(k), (int, float))},
        )
        asset.file.save("video.mp4", ContentFile(video), save=False)
        asset.save()
    except Exception as e:
        logger.warning("retry: video output store failed: %s", e)
    ir.status = "PROCESSED"
    ir.audio_seconds = seconds
    ir.results = {"video_asset_id": asset.id if asset else None,
                  "content_type": out_ct, "duration": seconds, "params": resolved or None}
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=["status", "audio_seconds", "results", "latency_ms", "modified_on"])
    Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())
    return True, None


def _retry_simple_fail(ir, message):
    ir.status = "REQUESTED"
    ir.results = {"error": message}
    ir.save(update_fields=["status", "results", "modified_on"])
    return False, message


_RETRY_RUNNERS = {
    "LLM": _rerun_llm, "STT": _rerun_stt, "TTS": _rerun_tts,
    "IMAGE": _rerun_image, "MESH": _rerun_mesh, "MUSIC": _rerun_music,
    "VIDEO": _rerun_video, "SCRAPE": _rerun_scrape, "RENDER": _rerun_render,
}


def rerun_inference_request(ir):
    """Re-run a failed InferenceRequest in place. Resolves a current provider,
    resets the row to PROCESSING (dropping any stale OUTPUT_* assets but keeping
    INPUT_* ones), then dispatches to the modality runner. Returns (ok, error)."""
    from .models import MediaAsset  # noqa: F811

    itype = ir.inference_type
    if itype not in _RETRY_RUNNERS:
        return False, f"Retry isn't supported for {itype} requests."

    model_name = ir.model_name or (ir.payload or {}).get("model")
    provider_model = _find_provider_for_model(
        ir.user, model_name, service_type=_RETRY_SERVICE_TYPE[itype]
    )
    if provider_model is None:
        return _retry_simple_fail(
            ir, f"No online provider is serving '{model_name}' right now."
        )

    # Clear stale outputs; keep stored inputs (needed to re-run STT/MESH).
    ir.assets.filter(kind__in=[
        MediaAsset.OUTPUT_AUDIO, MediaAsset.OUTPUT_IMAGE, MediaAsset.OUTPUT_MODEL,
        MediaAsset.OUTPUT_VIDEO,
    ]).delete()
    ir.provider = provider_model.provider
    ir.status = "PROCESSING"
    ir.results = None
    ir.latency_ms = None
    ir.ttft_ms = None
    ir.prompt_tokens = ir.completion_tokens = ir.total_tokens = None
    ir.audio_seconds = None
    ir.image_count = None
    ir.save(update_fields=[
        "provider", "status", "results", "latency_ms", "ttft_ms",
        "prompt_tokens", "completion_tokens", "total_tokens",
        "audio_seconds", "image_count", "modified_on",
    ])
    return _RETRY_RUNNERS[itype](ir, provider_model)


class RetryInferenceRequestView(_RateLimitHeadersMixin, APIView):
    """``POST /api/inference/requests/<id>/retry/`` — re-run a FAILED request in
    place (owner only). Synchronous, like the original endpoints."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "inference"

    def post(self, request, id):
        from .models import InferenceRequest

        ir = InferenceRequest.objects.filter(id=id).first()
        if ir is None:
            return Response(
                {"error": {"message": "No such inference request.", "type": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if ir.user_id != request.user.id:
            return Response(
                {"error": {"message": "You can only retry your own requests.", "type": "forbidden"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        if ir.status == "PROCESSING":
            return Response(
                {"error": {"message": "This request is still running.", "type": "conflict"}},
                status=status.HTTP_409_CONFLICT,
            )
        if ir.status == "PROCESSED":
            return Response(
                {"error": {"message": "This request already succeeded.", "type": "conflict"}},
                status=status.HTTP_409_CONFLICT,
            )

        ok, err = rerun_inference_request(ir)
        if not ok:
            return Response(
                {"error": {"message": err or "Retry failed.", "type": "upstream_error"},
                 "id": ir.id, "status": ir.status},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"id": ir.id, "status": ir.status}, status=status.HTTP_200_OK)
