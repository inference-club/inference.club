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


def _stream_model(user, model_name, messages, specs) -> Iterator[dict]:
    """One STREAMING chat completion. Yields live ``reasoning``/``token`` events
    as deltas arrive from the upstream, then a final ``_result`` sentinel event
    carrying ``message`` / ``usage`` / ``error`` for the loop's bookkeeping.

    Records an InferenceRequest (LLM) for metering, mirroring ``_call_model``. A
    non-OK HTTP response (e.g. a model with no tool parser → 400) is reported via
    the sentinel BEFORE any delta is emitted, so the caller can fall back to a
    non-streaming call cleanly.
    """
    from .openai_views import (
        UPSTREAM_TIMEOUT_SECONDS,
        _find_provider_for_model,
        _model_slug,
    )
    from .views import _tailnet_proxies

    pm = _find_provider_for_model(user, model_name)
    if pm is None:
        yield {"type": "_result", "message": None, "usage": {},
               "error": f"No online provider serving model '{model_name}' for this user."}
        return

    provider = pm.provider
    served = pm.name
    canonical = _model_slug(pm)
    body = {
        "model": served or model_name,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
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
            "stream": True,
            "tools": [s["function"]["name"] for s in (specs or [])],
        },
        status="PROCESSING",
    )
    endpoint = provider.tailnet_base_url.rstrip("/") + "/chat/completions"
    started = time.monotonic()

    try:
        upstream = requests.post(
            endpoint, json=body, timeout=UPSTREAM_TIMEOUT_SECONDS,
            verify=False, proxies=_tailnet_proxies(), stream=True,
        )
    except requests.RequestException as e:
        _finalize_error(ir, started, str(e))
        yield {"type": "_result", "message": None, "usage": {}, "error": str(e)}
        return

    if not upstream.ok:
        txt = _upstream_error_text(upstream)
        _finalize_error(ir, started, txt)
        upstream.close()
        yield {"type": "_result", "message": None, "usage": {}, "error": txt}
        return

    content_parts: list = []
    reasoning_parts: list = []
    tool_calls: dict = {}  # index → {id, type, function:{name, arguments}}
    usage: dict = {}
    try:
        for line in upstream.iter_lines(decode_unicode=True):
            if not line:
                continue
            data_str = line[5:].strip() if line.startswith("data:") else line.strip()
            if not data_str or data_str == "[DONE]":
                if data_str == "[DONE]":
                    break
                continue
            try:
                chunk = json.loads(data_str)
            except ValueError:
                continue
            if chunk.get("usage"):
                usage = chunk["usage"]
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            # vLLM reasoning parsers stream the thinking trace under "reasoning"
            # (nemotron_v3) or "reasoning_content" depending on the build —
            # accept either so the UI's thinking trace populates.
            rc = delta.get("reasoning_content") or delta.get("reasoning")
            if rc:
                reasoning_parts.append(rc)
                yield {"type": "reasoning", "delta": rc}
            c = delta.get("content")
            if c:
                content_parts.append(c)
                yield {"type": "token", "delta": c}
            for tc in (delta.get("tool_calls") or []):
                idx = tc.get("index", 0)
                slot = tool_calls.setdefault(
                    idx, {"id": None, "type": "function",
                          "function": {"name": "", "arguments": ""}})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]
    except requests.RequestException as e:
        _finalize_error(ir, started, str(e))
        yield {"type": "_result", "message": None, "usage": usage, "error": str(e)}
        return
    finally:
        upstream.close()

    content = "".join(content_parts)
    msg: dict = {"role": "assistant", "content": content or None}
    if tool_calls:
        msg["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]
    if reasoning_parts:
        msg["reasoning_content"] = "".join(reasoning_parts)

    ir.status = "PROCESSED"
    ir.results = {"choices": [{"message": msg}], "usage": usage}
    ir.prompt_tokens = int(usage.get("prompt_tokens") or 0)
    ir.completion_tokens = int(usage.get("completion_tokens") or 0)
    ir.total_tokens = int(usage.get("total_tokens") or 0)
    ir.latency_ms = int((time.monotonic() - started) * 1000)
    ir.save(update_fields=[
        "status", "results", "prompt_tokens", "completion_tokens",
        "total_tokens", "latency_ms", "modified_on",
    ])
    from django.utils import timezone

    from .models import Provider
    Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())

    yield {"type": "_result", "message": msg, "usage": usage, "error": None}


def _model_turn(user, model, convo, offer_tools) -> Iterator[dict]:
    """One agent turn. Streams ``reasoning``/``token`` deltas live, then yields a
    ``_result`` sentinel (``message``/``usage``/``error``). Tries streaming first;
    if the stream fails before emitting any delta (e.g. upstream 400 on tools),
    falls back to a non-streaming ``_call_model`` and emits the answer's
    reasoning/tokens here (chunked) so the UI still streams — but only for a final
    answer, never for a tool-call turn."""
    streamed_any = False
    msg = None
    usage: dict = {}
    err = None
    for ev in _stream_model(user, model, convo, offer_tools):
        if ev.get("type") == "_result":
            msg, usage, err = ev["message"], ev["usage"], ev["error"]
        else:
            streamed_any = True
            yield ev

    if err and not streamed_any:
        msg, usage, err = _call_model(user, model, convo, offer_tools)
        if not err and msg is not None and not msg.get("tool_calls"):
            if msg.get("reasoning_content"):
                yield {"type": "reasoning", "delta": msg["reasoning_content"]}
            for delta in _chunk(msg.get("content") or ""):
                yield {"type": "token", "delta": delta}

    yield {"type": "_result", "message": msg, "usage": usage, "error": err}


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
        msg = usage = err = None
        for ev in _model_turn(user, model, convo, offer_tools):
            if ev.get("type") == "_result":
                msg, usage, err = ev["message"], ev["usage"], ev["error"]
            else:
                yield ev
        if err or msg is None:
            yield {"type": "error", "message": err or "The model returned no message."}
            return
        _accumulate(total_usage, usage)
        convo.append(msg)
        new_messages.append(msg)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            # The answer's tokens already streamed live during the turn above.
            yield from _emit_done(msg, total_usage, new_messages)
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
    msg = usage = err = None
    for ev in _model_turn(user, model, convo, None):
        if ev.get("type") == "_result":
            msg, usage, err = ev["message"], ev["usage"], ev["error"]
        else:
            yield ev
    if err or msg is None:
        yield {"type": "error", "message": err or "The model returned no message."}
        return
    _accumulate(total_usage, usage)
    convo.append(msg)
    new_messages.append(msg)
    yield from _emit_done(msg, total_usage, new_messages)


def _emit_done(msg, total_usage, new_messages) -> Iterator[dict]:
    """Emit the terminal ``done`` event. Any reasoning/token deltas were already
    streamed live during the model turn, so this only closes the stream."""
    yield {
        "type": "done",
        "usage": total_usage,
        "messages": new_messages,
        "message": msg,
    }
