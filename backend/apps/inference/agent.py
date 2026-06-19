"""The playground Agent loop (PRD 14).

A small, synchronous tool-calling loop over the existing chat proxy. Each turn
calls the chosen model with an OpenAI ``tools`` array; if the model returns
``tool_calls``, the loop runs them (as the user) and feeds the results back,
until the model answers or a budget is hit.

The loop is **stateless**: it takes the prior ``messages`` and yields events; it
holds no cross-user or cross-request state. Persistence (saving the conversation
as a ``ChatThread``) is the caller's concern — the loop just returns the new
messages in its ``done`` event.

It runs entirely in-process and reuses the inference core: ``_find_provider_for_model``
for routing, the tailnet forward for the model call, and per-modality runners
(via the tools) for media. Every model turn records an ``InferenceRequest`` so
agent usage is metered exactly like normal chat.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Iterator, Optional

import requests
from django.conf import settings

from .agent_tools import ToolContext, ToolRegistry, ToolResult, get_registry
from .models import InferenceRequest

logger = logging.getLogger("django")

SYSTEM_PROMPT = (
    "You are Agent, a helpful assistant inside the inference.club playground. "
    "You can call tools to search the web and generate media on the user's "
    "behalf. Prefer a tool when it gives a better or more current answer; "
    "otherwise just answer directly. Keep tool outputs in mind but be concise — "
    "the context window is small. When you generate an image, tell the user it "
    "is shown in the chat; do not paste raw URLs or base64."
)


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…(truncated)"


def _chunk(text: str) -> Iterator[str]:
    """Split a final answer into small pieces so the UI can stream it. Splits on
    whitespace, preserving it, so reassembly is exact."""
    for piece in re.findall(r"\S+\s*|\s+", text or ""):
        if piece:
            yield piece


def _accumulate(total: dict, usage: dict) -> None:
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        try:
            total[k] += int(usage.get(k) or 0)
        except (TypeError, ValueError):
            pass


def _call_model(user, model_name, messages, specs) -> tuple[Optional[dict], dict, Optional[str]]:
    """One non-streaming chat completion. Records an InferenceRequest (LLM) for
    metering. Returns ``(assistant_message, usage, error)``. When ``specs`` is
    provided but the upstream rejects the request (400 — e.g. a model with no
    tool parser), retries once without tools so the loop degrades gracefully."""
    from .openai_views import (
        UPSTREAM_TIMEOUT_SECONDS,
        _find_provider_for_model,
        _model_slug,
        _usage_tokens,
    )
    from .views import _tailnet_proxies

    pm = _find_provider_for_model(user, model_name)
    if pm is None:
        return None, {}, f"No online provider serving model '{model_name}' for this user."

    provider = pm.provider
    served = pm.name
    canonical = _model_slug(pm)
    body = {"model": served or model_name, "messages": messages, "stream": False}
    if specs:
        body["tools"] = specs
        body["tool_choice"] = "auto"

    ir = InferenceRequest.objects.create(
        user=user,
        provider=provider,
        model_name=canonical or model_name or "",
        inference_type="LLM",
        payload={
            "messages": messages,
            "agent": True,
            "tools": [s["function"]["name"] for s in (specs or [])],
        },
        status="PROCESSING",
    )
    endpoint = provider.tailnet_base_url.rstrip("/") + "/chat/completions"
    started = time.monotonic()

    def _do_post(payload):
        return requests.post(
            endpoint, json=payload, timeout=UPSTREAM_TIMEOUT_SECONDS,
            verify=False, proxies=_tailnet_proxies(),
        )

    try:
        upstream = _do_post(body)
        if not upstream.ok and specs and upstream.status_code == 400:
            # Model likely lacks a tool parser — retry as a plain answer.
            body.pop("tools", None)
            body.pop("tool_choice", None)
            upstream = _do_post(body)
    except requests.RequestException as e:
        _finalize_error(ir, started, str(e))
        return None, {}, str(e)

    if not upstream.ok:
        txt = _upstream_error_text(upstream)
        _finalize_error(ir, started, txt)
        return None, {}, txt

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
    from .models import Provider
    from django.utils import timezone
    Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())

    msg = _extract_message(data)
    if msg is None:
        return None, {}, "The model returned no message."
    return msg, (data.get("usage") or {}), None


def _extract_message(data) -> Optional[dict]:
    try:
        choice = data["choices"][0]
    except (KeyError, IndexError, TypeError):
        return None
    msg = choice.get("message") if isinstance(choice, dict) else None
    if not isinstance(msg, dict):
        return None
    # Normalize to the fields we persist/forward. Keep tool_calls + reasoning so
    # the model sees its own prior calls and the UI can show reasoning.
    out = {"role": msg.get("role") or "assistant", "content": msg.get("content")}
    if msg.get("tool_calls"):
        out["tool_calls"] = msg["tool_calls"]
    if msg.get("reasoning_content"):
        out["reasoning_content"] = msg["reasoning_content"]
    return out


def _upstream_error_text(upstream) -> str:
    try:
        if upstream.headers.get("content-type", "").startswith("application/json"):
            return json.dumps(upstream.json())[:500]
        return (upstream.text or "")[:500] or f"Upstream returned HTTP {upstream.status_code}"
    except Exception:
        return f"Upstream returned HTTP {upstream.status_code}"


def _finalize_error(ir, started, message) -> None:
    ir.status = "REQUESTED"
    ir.results = {"error": message}
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=["status", "results", "latency_ms", "modified_on"])


def _safe_run(tool, ctx, args) -> ToolResult:
    try:
        return tool.handler(ctx, args)
    except Exception as e:  # a tool must never crash the loop
        logger.exception("agent tool %s raised", tool.name)
        return ToolResult(text=f"Tool '{tool.name}' errored: {e}", ok=False)


def run_agent(
    *,
    user,
    request,
    model,
    messages,
    tools=None,
    skill=None,
    registry: Optional[ToolRegistry] = None,
) -> Iterator[dict]:
    """Run the agent loop, yielding event dicts (see PRD 14 §4.3):
    ``tool_call`` / ``tool_result`` / ``reasoning`` / ``token`` / ``error`` /
    ``done``. The caller serializes these (SSE) or collects them (sync).

    ``skill`` (PRD 14 V2) is an optional preset name that injects a system-prompt
    fragment and, unless ``tools`` overrides it, narrows the offered tool subset.
    """
    from .agent_skills import get_skill

    registry = registry or get_registry()
    deadline = time.monotonic() + settings.AGENT_WALL_CLOCK_SECONDS
    skill_obj = get_skill(skill)

    convo = [dict(m) for m in (messages or []) if isinstance(m, dict)]
    if not any(m.get("role") == "system" for m in convo):
        convo.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
    if skill_obj and skill_obj.system_prompt:
        # Prepend the skill's guidance as its own system message so it applies
        # even when the caller supplied a system prompt of their own.
        convo.insert(0, {"role": "system", "content": skill_obj.system_prompt})

    # Explicit request `tools` win; otherwise a skill narrows the toolset.
    enabled = tools if tools is not None else (skill_obj.tools if skill_obj else None)
    selected = registry.for_user(user, enabled=enabled)
    specs = ToolRegistry.specs(selected)
    selected_names = {t.name for t in selected}

    new_messages: list = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    ctx = ToolContext(user=user, request=request)

    for _step in range(max(1, settings.AGENT_MAX_ITERATIONS)):
        offer_tools = specs if (specs and time.monotonic() < deadline) else None
        msg, usage, err = _call_model(user, model, convo, offer_tools)
        if err:
            yield {"type": "error", "message": err}
            return
        _accumulate(total_usage, usage)
        convo.append(msg)
        new_messages.append(msg)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            yield from _emit_final(msg, total_usage, new_messages)
            return

        for call in tool_calls:
            fn = (call.get("function") or {}) if isinstance(call, dict) else {}
            name = fn.get("name") or ""
            call_id = call.get("id") or name
            try:
                args = json.loads(fn.get("arguments") or "{}")
                if not isinstance(args, dict):
                    args = {}
            except (ValueError, TypeError):
                args = {}
            yield {"type": "tool_call", "id": call_id, "name": name, "arguments": args}

            tool = registry.get(name)
            if tool is None or name not in selected_names:
                result = ToolResult(text=f"Unknown or unavailable tool '{name}'.", ok=False)
            else:
                result = _safe_run(tool, ctx, args)

            text = _truncate(result.text, settings.AGENT_TOOL_OUTPUT_MAX_CHARS)
            tool_msg = {
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": text,
            }
            convo.append(tool_msg)
            new_messages.append(tool_msg)
            yield {
                "type": "tool_result",
                "id": call_id,
                "name": name,
                "ok": result.ok,
                "summary": text,
                "data": result.data,
            }

        if time.monotonic() >= deadline:
            break

    # Budget/iteration cap hit: force a final answer with tools disabled.
    msg, usage, err = _call_model(user, model, convo, None)
    if err:
        yield {"type": "error", "message": err}
        return
    _accumulate(total_usage, usage)
    convo.append(msg)
    new_messages.append(msg)
    yield from _emit_final(msg, total_usage, new_messages)


def _emit_final(msg, total_usage, new_messages) -> Iterator[dict]:
    if msg.get("reasoning_content"):
        yield {"type": "reasoning", "delta": msg["reasoning_content"]}
    for delta in _chunk(msg.get("content") or ""):
        yield {"type": "token", "delta": delta}
    yield {
        "type": "done",
        "usage": total_usage,
        "messages": new_messages,
        "message": msg,
    }
