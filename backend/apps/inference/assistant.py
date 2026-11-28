"""The in-app assistant: the agent loop (``agent.py``) driving the same tools
the remote MCP server offers (``mcp_server.TOOLS``), so "say it and it happens"
works identically inside the web app and from Claude, Hermes or the CLI.

``POST /v1/agent`` with ``"skill": "assistant"`` selects this toolset. Results
carry a ``summary`` sentence for the model to read back, and optionally a
``client_action`` (navigate, play) that the web app carries out.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from django.conf import settings
from django.utils import timezone

from .agent_tools import Tool, ToolContext, ToolRegistry, ToolResult, get_registry

SKILL = "assistant"

# Offered by MCP but left out in-app: `chat` (the assistant is already a model)
# and the workflow tools (make_song covers the common multi-step request).
_SKIP = {"chat", "list_workflow_templates", "run_workflow", "get_workflow_run"}

# Arguments where an empty string is a real value ("no default collection").
_EMPTY_OK = {"default_collection", "fallback_model", "description"}

PROMPT = """\
You are the inference.club assistant. You operate the person's own account for \
them: generate media, find and organise their library, change who can see \
things, change settings, play music and open pages. Often they are speaking to \
you, so what you say is read aloud.

How to work:
- Act, don't describe. If the request is clear, call the tool straight away.
- To refer to "that song" or "my latest image", call search_library first to \
get its id. Never invent ids.
- "A song about X with pictures" is one call to make_song.
- Generations are queued on home GPUs. When a tool returns a job id the work \
is under way: say so and stop. Do not wait, poll or resubmit.
- delete_item and delete_collection: ask first, and pass confirm: true only \
after the person has said yes in this conversation.
- When nothing else fits, use find_api then api_request.

How to answer:
- One or two short plain sentences saying what you did, in the past tense, \
using each tool's `summary`. No markdown, no lists, no URLs, no ids unless \
asked: results are shown on screen next to your words.
- If a tool failed, say what failed and what the person can do.
"""


def _for_model(payload) -> str:
    """The tool result as the model sees it: summary first, bulky fields
    trimmed, nothing the model has no use for."""
    if not isinstance(payload, dict):
        return str(payload)
    slim = {k: v for k, v in payload.items() if k not in ("client_action", "summary")}
    for k, v in list(slim.items()):
        if isinstance(v, list) and len(v) > 12:
            slim[k] = v[:12] + [f"… {len(v) - 12} more"]
    if "tracks" in slim:
        slim["tracks"] = [t.get("title") if isinstance(t, dict) else t for t in slim["tracks"]]
    if "lyrics" in slim and isinstance(slim["lyrics"], str):
        slim["lyrics"] = slim["lyrics"][:400]
    head = payload.get("summary") or ""
    return (head + "\n" if head else "") + json.dumps(slim, ensure_ascii=False)


def _wrap(spec) -> Tool:
    name = spec["name"]

    def handler(ctx: ToolContext, args: dict) -> ToolResult:
        from .mcp_server import ToolError, call_tool

        outer = getattr(ctx.request, "_request", ctx.request)
        outer.user = ctx.user
        outer._ic_tool_wait = settings.ASSISTANT_TOOL_WAIT_SECONDS
        if not getattr(outer, "_ic_turn", None):
            outer._ic_turn = uuid.uuid4().hex  # one id per assistant request
        # Small models write "None" or "" for arguments they mean to omit.
        args = {k: v for k, v in (args or {}).items()
                if v is not None and not (isinstance(v, str) and v.strip() in ("", "None", "null"))
                or k in _EMPTY_OK and v == ""}
        try:
            payload = call_tool(outer, name, args)
        except ToolError as e:
            return ToolResult(text=str(e), data={"summary": str(e)}, ok=False)
        except (KeyError, TypeError, ValueError) as e:
            msg = f"Bad arguments for {name}: {e}"
            return ToolResult(text=msg, data={"summary": msg}, ok=False)
        return ToolResult(text=_for_model(payload),
                          data=payload if isinstance(payload, dict) else None)

    schema = dict(spec["inputSchema"])
    return Tool(name=name, description=spec["description"], parameters=schema, handler=handler)


_REGISTRY: Optional[ToolRegistry] = None


def get_assistant_registry() -> ToolRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        from .mcp_server import TOOLS

        tools = [_wrap(t) for t in TOOLS if t["name"] not in _SKIP]
        search = get_registry().get("web_search")
        if search is not None:
            tools.append(search)
        _REGISTRY = ToolRegistry(tools)
    return _REGISTRY


def _open_item(user, ref):
    """The library item a page reference points at, if the person may see it."""
    from .models import InferenceRequest

    ref = str(ref or "")[:40]
    if not ref:
        return None
    ir = InferenceRequest.objects.filter(public_id=ref).first()
    if ir is None and ref.isdigit():
        ir = InferenceRequest.objects.filter(pk=int(ref)).first()
    return ir if ir is not None and ir.is_visible_to(user) else None


def system_messages(user, context=None) -> list:
    """The assistant's system prompt plus what the web app says about where the
    person is, so "make this public" can resolve."""
    lines = [PROMPT, f"Today is {timezone.now():%A %Y-%m-%d}. "
                     f"The person's handle is {getattr(user, 'handle', '') or 'unknown'}."]
    ctx = context if isinstance(context, dict) else {}
    if ctx.get("path"):
        lines.append(f"They are looking at the page {str(ctx['path'])[:200]}.")
    item = _open_item(user, ctx.get("item"))
    if item is not None:
        lines.append(f"The item open on that page has id {item.id} "
                     f"({item.inference_type.lower()}"
                     + (f" “{item.title[:80]}”" if item.title else "")
                     + "); 'this' or 'it' means that item.")
    if ctx.get("playing_id"):
        lines.append(f"The song playing now has id {int(ctx['playing_id'])}"
                     + (f" (“{str(ctx.get('playing_title'))[:80]}”)" if ctx.get("playing_title") else "")
                     + ".")
    if ctx.get("spoken"):
        lines.append("They are using voice: keep answers to one or two short sentences.")
    return [{"role": "system", "content": "\n".join(lines)}]
