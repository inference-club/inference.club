"""HTTP surface for the playground Agent (PRD 14).

``POST /v1/agent`` runs the tool-calling loop and streams typed SSE events (or,
with ``stream:false``, returns one JSON object — handy for clients and tests).
``GET /v1/agent/tools`` lists the tools available to the requesting user.

Gated by ``IsAuthenticated`` + the ``inference`` throttle scope, so guests can
use the Agent exactly like plain chat; individual tools self-gate (e.g.
``full_member_only``) inside the registry.
"""
from __future__ import annotations

import json

from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsFullMember

from . import agent as agent_loop
from .agent_skills import describe_skills
from .agent_tools import get_registry
from .openai_views import _RateLimitHeadersMixin
from .throttling import AccountTypeScopedRateThrottle


def _disabled_response():
    return Response(
        {"error": {"message": "The Agent is not enabled on this server.", "type": "agent_disabled"}},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class AgentChatView(_RateLimitHeadersMixin, APIView):
    """``POST /v1/agent`` — run the agent loop."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "inference"

    def post(self, request):
        if not settings.AGENT_ENABLED:
            return _disabled_response()

        body = request.data if isinstance(request.data, dict) else {}
        model = body.get("model")
        messages = body.get("messages")
        if not model or not isinstance(model, str):
            return Response(
                {"error": {"message": "`model` is required.", "type": "invalid_request"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(messages, list) or not messages:
            return Response(
                {"error": {"message": "`messages` must be a non-empty list.", "type": "invalid_request"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(messages) > settings.INFERENCE_MAX_MESSAGES:
            return Response(
                {"error": {"message": "Too many messages.", "type": "request_too_large"}},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        tools = body.get("tools")
        if tools is not None and not isinstance(tools, list):
            tools = None
        skill = body.get("skill") if isinstance(body.get("skill"), str) else None

        events = agent_loop.run_agent(
            user=request.user,
            request=request,
            model=model,
            messages=messages,
            tools=tools,
            skill=skill,
            registry=get_registry(),
        )

        if body.get("stream") is False:
            return self._collect(events)
        return self._stream(events)

    def _stream(self, events):
        def gen():
            for ev in events:
                yield f"data: {json.dumps(ev)}\n\n"

        resp = StreamingHttpResponse(gen(), content_type="text/event-stream")
        resp["Cache-Control"] = "no-cache"
        resp["X-Accel-Buffering"] = "no"
        return resp

    def _collect(self, events):
        """Drain the loop into one JSON object (non-streaming clients/tests)."""
        tool_events, content, usage, messages, error = [], [], {}, [], None
        for ev in events:
            t = ev.get("type")
            if t in ("tool_call", "tool_result"):
                tool_events.append(ev)
            elif t == "token":
                content.append(ev.get("delta") or "")
            elif t == "done":
                usage = ev.get("usage") or {}
                messages = ev.get("messages") or []
            elif t == "error":
                error = ev.get("message")
        if error is not None:
            return Response(
                {"error": {"message": error, "type": "agent_error"}},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            {
                "content": "".join(content),
                "tool_events": tool_events,
                "messages": messages,
                "usage": usage,
            }
        )


class AgentToolsView(_RateLimitHeadersMixin, APIView):
    """``GET /v1/agent/tools`` — the tools this user may use (UI affordances)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "models"

    def get(self, request):
        if not settings.AGENT_ENABLED:
            return Response({"object": "list", "data": [], "enabled": False})
        return Response(
            {
                "object": "list",
                "enabled": True,
                "brave_key_set": bool(getattr(request.user, "brave_api_key", "")),
                "data": get_registry().describe_for_user(request.user),
                "skills": describe_skills(),
            }
        )


class AgentBraveKeyView(_RateLimitHeadersMixin, APIView):
    """``POST``/``DELETE /v1/agent/brave-key`` — set or clear the user's personal
    Brave Search API key (write-only; never returned). Full members only."""

    permission_classes = [IsFullMember]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "models"

    def post(self, request):
        key = (request.data or {}).get("api_key") if isinstance(request.data, dict) else None
        if not key or not isinstance(key, str):
            return Response(
                {"error": {"message": "`api_key` is required.", "type": "invalid_request"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.user.brave_api_key = key.strip()[:128]
        request.user.save(update_fields=["brave_api_key"])
        return Response({"brave_key_set": True})

    def delete(self, request):
        request.user.brave_api_key = ""
        request.user.save(update_fields=["brave_api_key"])
        return Response({"brave_key_set": False})
