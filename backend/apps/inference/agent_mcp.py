"""Minimal MCP (Model Context Protocol) client adapter (PRD 14 V2).

Lets external MCP servers contribute tools to the agent's registry. Each server
declared in ``settings.AGENT_MCP_SERVERS`` is queried once (``tools/list``) and
every tool it exposes becomes a registry ``Tool`` named ``<server>__<tool>``;
calling it round-trips through ``tools/call``.

Transport is MCP "Streamable HTTP": a single endpoint that takes JSON-RPC 2.0
POSTs. We request/accept JSON responses (not SSE) to keep the client dependency
-free and synchronous, which covers the common server configurations. Servers
that *only* speak SSE or stdio aren't supported here — a deliberate V2 scope cut.

Discovery is best-effort and lazy-cached: a server that's down at first use is
skipped (its tools simply don't appear) rather than breaking the agent.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests
from django.conf import settings

from .agent_tools import Tool, ToolResult

logger = logging.getLogger("django")


class MCPError(Exception):
    pass


class MCPClient:
    """A tiny JSON-RPC client for one MCP Streamable-HTTP server."""

    def __init__(self, name: str, url: str, token: str = "", timeout: int = 20):
        self.name = name
        self.url = url
        self.token = token
        self.timeout = timeout
        self._id = 0

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _rpc(self, method: str, params: dict) -> dict:
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        try:
            resp = requests.post(self.url, json=body, headers=self._headers(), timeout=self.timeout)
        except requests.RequestException as e:
            raise MCPError(str(e)) from e
        if not resp.ok:
            raise MCPError(f"HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise MCPError("non-JSON response") from e
        if isinstance(data, dict) and data.get("error"):
            raise MCPError(str(data["error"]))
        return (data or {}).get("result") or {}

    def list_tools(self) -> list:
        result = self._rpc("tools/list", {})
        tools = result.get("tools") or []
        return [t for t in tools if isinstance(t, dict) and t.get("name")]

    def call_tool(self, name: str, arguments: dict) -> str:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        return _flatten_content(result)


def _flatten_content(result: dict) -> str:
    """MCP tool results carry a ``content`` list of typed blocks; join the text
    ones into a single string the model can read."""
    parts = []
    for block in (result.get("content") or []):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            parts.append(str(block["text"]))
        elif block.get("text"):
            parts.append(str(block["text"]))
    if not parts and result.get("structuredContent"):
        import json

        return json.dumps(result["structuredContent"])[:4000]
    return "\n".join(parts) if parts else "(the tool returned no text content)"


def _wrap_tool(client: MCPClient, spec: dict) -> Tool:
    tool_name = spec["name"]
    qualified = f"{client.name}__{tool_name}"
    params = spec.get("inputSchema") or {"type": "object", "properties": {}}

    def handler(ctx, args) -> ToolResult:
        try:
            text = client.call_tool(tool_name, args or {})
        except MCPError as e:
            return ToolResult(text=f"MCP tool '{qualified}' failed: {e}", ok=False)
        return ToolResult(text=text)

    return Tool(
        name=qualified,
        description=(spec.get("description") or f"{tool_name} (via {client.name} MCP server)"),
        parameters=params if isinstance(params, dict) else {"type": "object", "properties": {}},
        handler=handler,
    )


def discover_mcp_tools() -> list:
    """Every tool from every configured MCP server. Best-effort: a server that
    errors is logged and skipped. Called once at registry build."""
    out: list = []
    for server in (getattr(settings, "AGENT_MCP_SERVERS", None) or []):
        if not isinstance(server, dict) or not server.get("name") or not server.get("url"):
            continue
        client = MCPClient(server["name"], server["url"], server.get("token", ""))
        try:
            specs = client.list_tools()
        except MCPError as e:
            logger.warning("MCP server %s unavailable: %s", server.get("name"), e)
            continue
        for spec in specs:
            try:
                out.append(_wrap_tool(client, spec))
            except Exception:  # a malformed spec must not break discovery
                logger.exception("skipping malformed MCP tool from %s", server.get("name"))
    return out
