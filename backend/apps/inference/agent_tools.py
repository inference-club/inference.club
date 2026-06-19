"""Tools the playground Agent (PRD 14) can call.

A tool is a plain Python callable plus an OpenAI function schema. The agent loop
(``agent.py``) hands the model a list of tool schemas; when the model emits a
``tool_call``, the loop runs the matching tool **as the requesting user** and
feeds the result back. Two design rules keep this safe and simple:

- **No privilege escalation.** A tool does exactly what the user could do
  themselves — ``generate_image`` mints a normal, owned ``InferenceRequest`` via
  the same runner the image endpoint uses, routed by the user's own preference.
- **Bounded output.** A tool's ``text`` is what re-enters the conversation, so
  the loop truncates it to ``AGENT_TOOL_OUTPUT_MAX_CHARS`` — the guardrail for
  the cluster LLM's small (10k) context window.

Adding a tool is: write a handler, wrap it in a ``Tool``, and register it in
``build_registry()``. V1/V2 tools (browse, scrape, more generation, MCP) slot in
the same way without touching the loop.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Optional

import requests
from django.conf import settings

from .models import InferenceRequest, MediaAsset, ProviderModel

logger = logging.getLogger("django")


# --- result + tool types -----------------------------------------------------


@dataclass
class ToolResult:
    """The outcome of one tool call.

    ``text`` is what the model sees next turn (truncated by the loop). ``data``
    is an optional structured payload streamed to the UI (e.g. image URLs) and
    never shown to the model. ``ok`` is False for a handled failure — the model
    still sees ``text`` (an error description) and can react, but the UI can
    style it as an error.
    """

    text: str
    data: Optional[dict] = None
    ok: bool = True


@dataclass
class ToolContext:
    """Per-request context passed to every handler. ``request`` is the DRF
    request (for building absolute asset URLs); ``user`` is the actor."""

    user: object
    request: object


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema for the function arguments
    handler: Callable[[ToolContext, dict], ToolResult]
    full_member_only: bool = False
    # Called with no args to decide if the tool is usable in this deployment
    # (e.g. a service URL is configured). None ⇒ always available.
    available: Optional[Callable[[], bool]] = None

    def is_available(self) -> bool:
        return self.available() if self.available is not None else True

    def spec(self) -> dict:
        """The OpenAI ``tools[]`` entry for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _is_full_member(user) -> bool:
    """Mirror core.permissions.IsFullMember: a signed-in, non-guest account."""
    return bool(
        getattr(user, "is_authenticated", False)
        and not getattr(user, "is_anonymous_account", False)
    )


class ToolRegistry:
    """The set of tools known to this deployment. ``for_user`` filters to the
    ones a given user may actually use (availability + membership + an optional
    request-level allow-list)."""

    def __init__(self, tools):
        self._tools = {t.name: t for t in tools}

    def get(self, name) -> Optional[Tool]:
        return self._tools.get(name)

    def for_user(self, user, enabled=None) -> list:
        out = []
        for tool in self._tools.values():
            if not tool.is_available():
                continue
            if tool.full_member_only and not _is_full_member(user):
                continue
            if enabled is not None and tool.name not in enabled:
                continue
            out.append(tool)
        return out

    @staticmethod
    def specs(tools) -> list:
        return [t.spec() for t in tools]

    def describe_for_user(self, user) -> list:
        """A JSON-able list of the tools available to ``user`` (for the UI)."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "full_member_only": t.full_member_only,
            }
            for t in self.for_user(user)
        ]


# --- model discovery ----------------------------------------------------------


def resolve_provider_model(user, service_type, preferred=None):
    """A ``ProviderModel`` of ``service_type`` the user can route to right now,
    honoring their routing preference (delegated to ``_find_provider_for_model``).
    ``preferred`` is an optional model slug to try first. Returns None if nothing
    is reachable."""
    from .openai_views import _find_provider_for_model

    if preferred:
        pm = _find_provider_for_model(user, preferred, service_type=service_type)
        if pm is not None:
            return pm
    slug = _discover_slug(user, service_type)
    if not slug:
        return None
    return _find_provider_for_model(user, slug, service_type=service_type)


def _discover_slug(user, service_type) -> Optional[str]:
    """The public slug of some accessible model of ``service_type`` — the user's
    own deployments first, then shared services they're granted. Routing
    (online/preference) is re-checked by the caller via _find_provider_for_model."""
    from .openai_views import _model_slug
    from .serializers import _user_real_github_login

    base = ProviderModel.objects.filter(
        is_active=True,
        provider__is_active=True,
        provider__accepting_requests=True,
        service__service_type=service_type,
    ).exclude(provider__tailnet_hostname="").select_related(
        "provider", "service", "catalog_model"
    )
    for pm in base.filter(provider__user=user):
        return _model_slug(pm)
    gh = _user_real_github_login(user)
    for pm in base.exclude(provider__user=user):
        if pm.service.grants_access_to(user, gh):
            return _model_slug(pm)
    return None


# --- tools --------------------------------------------------------------------


def _web_search(ctx: ToolContext, args: dict) -> ToolResult:
    """Keyless web search via the cluster's SearXNG JSON API."""
    query = (args.get("query") or "").strip()
    if not query:
        return ToolResult(text="No query was provided.", ok=False)
    n = args.get("num_results")
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = settings.AGENT_MAX_SEARCH_RESULTS
    n = max(1, min(n, settings.AGENT_MAX_SEARCH_RESULTS))

    from .views import _tailnet_proxies

    url = settings.AGENT_SEARXNG_URL.rstrip("/") + "/search"
    try:
        resp = requests.get(
            url,
            params={"q": query, "format": "json"},
            timeout=20,
            verify=False,
            proxies=_tailnet_proxies(),
        )
    except requests.RequestException as e:
        logger.warning("agent web_search failed: %s", e)
        return ToolResult(text=f"Web search failed: {e}", ok=False)
    if not resp.ok:
        return ToolResult(text=f"Web search returned HTTP {resp.status_code}.", ok=False)
    try:
        payload = resp.json()
    except ValueError:
        return ToolResult(text="Web search returned a non-JSON response.", ok=False)

    results = (payload.get("results") or [])[:n]
    if not results:
        return ToolResult(text=f"No results found for '{query}'.", data={"results": []})

    clean = []
    lines = []
    for i, r in enumerate(results, 1):
        title = (r.get("title") or "").strip()
        link = (r.get("url") or "").strip()
        snippet = (r.get("content") or "").strip()
        clean.append({"title": title, "url": link, "snippet": snippet})
        lines.append(f"{i}. {title}\n   {link}\n   {snippet}")
    text = f"Top {len(clean)} results for '{query}':\n\n" + "\n\n".join(lines)
    return ToolResult(text=text, data={"query": query, "results": clean})


# Output asset kinds → the media `kind` the UI renders inline.
_OUTPUT_KIND = {
    MediaAsset.OUTPUT_IMAGE: "image",
    MediaAsset.OUTPUT_VIDEO: "video",
    MediaAsset.OUTPUT_AUDIO: "audio",
}


def _run_generation(ctx, *, inference_type, service_type, payload, noun, preferred=None) -> ToolResult:
    """Create and run a media-generation InferenceRequest as the user, via the
    same per-modality runner the sync endpoints and async jobs use, then collect
    the produced asset URLs. Shared by the image/video/voice/music tools so each
    tool is just a payload shape — the result is real, owned, and gallery-visible."""
    from .openai_views import _RETRY_RUNNERS, _model_slug
    from .serializers import asset_url

    pm = resolve_provider_model(ctx.user, service_type, preferred=preferred)
    if pm is None:
        return ToolResult(
            text=f"No online {noun}-generation model is available to this user.", ok=False
        )
    slug = _model_slug(pm)
    payload = {**payload, "model": slug}
    ir = InferenceRequest.objects.create(
        user=ctx.user, provider=pm.provider, model_name=slug,
        inference_type=inference_type, payload=payload, status="PROCESSING",
    )
    runner = _RETRY_RUNNERS.get(inference_type)
    ok, err = runner(ir, pm)
    if not ok:
        return ToolResult(text=f"{noun.capitalize()} generation failed: {err}", ok=False)

    media = []
    for asset in ir.assets.all():
        kind = _OUTPUT_KIND.get(asset.kind)
        if not kind:
            continue
        u = asset_url(asset, ctx.request)
        if u:
            media.append({"id": asset.id, "url": u, "kind": kind})
    if not media:
        return ToolResult(text=f"The {noun} request completed but produced no output.", ok=False)
    return ToolResult(
        text=(
            f"Generated {len(media)} {noun} output(s). They are saved to the user's "
            "gallery and shown in the chat — do not paste URLs."
        ),
        data={"request_id": ir.id, "media": media},
    )


def _web_search_brave(ctx: ToolContext, args: dict) -> ToolResult:
    """Web search via the Brave Search API, using the user's personal key (or an
    instance-wide fallback). Goes to the public internet, not the tailnet."""
    query = (args.get("query") or "").strip()
    if not query:
        return ToolResult(text="No query was provided.", ok=False)
    key = getattr(ctx.user, "brave_api_key", "") or settings.AGENT_BRAVE_API_KEY
    if not key:
        return ToolResult(
            text="No Brave Search API key is set. Add one in the Agent settings to use Brave.",
            ok=False,
        )
    n = args.get("num_results")
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = settings.AGENT_MAX_SEARCH_RESULTS
    n = max(1, min(n, settings.AGENT_MAX_SEARCH_RESULTS))
    try:
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": n},
            headers={"Accept": "application/json", "X-Subscription-Token": key},
            timeout=20,
        )
    except requests.RequestException as e:
        return ToolResult(text=f"Brave search failed: {e}", ok=False)
    if not resp.ok:
        return ToolResult(text=f"Brave search returned HTTP {resp.status_code}.", ok=False)
    try:
        data = resp.json()
    except ValueError:
        return ToolResult(text="Brave search returned a non-JSON response.", ok=False)
    results = ((data.get("web") or {}).get("results") or [])[:n]
    if not results:
        return ToolResult(text=f"No results found for '{query}'.", data={"results": []})
    clean, lines = [], []
    for i, r in enumerate(results, 1):
        title, link = (r.get("title") or "").strip(), (r.get("url") or "").strip()
        snippet = (r.get("description") or "").strip()
        clean.append({"title": title, "url": link, "snippet": snippet})
        lines.append(f"{i}. {title}\n   {link}\n   {snippet}")
    text = f"Top {len(clean)} Brave results for '{query}':\n\n" + "\n\n".join(lines)
    return ToolResult(text=text, data={"query": query, "results": clean})


def _generate_image(ctx: ToolContext, args: dict) -> ToolResult:
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return ToolResult(text="No image prompt was provided.", ok=False)
    prompt = prompt[: settings.IMAGE_MAX_PROMPT_CHARS]
    return _run_generation(
        ctx, inference_type="IMAGE", service_type="image", noun="image",
        preferred=args.get("model"),
        payload={"prompt": prompt, "n": 1, "size": args.get("size"), "response_format": "url"},
    )


def _generate_video(ctx: ToolContext, args: dict) -> ToolResult:
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return ToolResult(text="No video prompt was provided.", ok=False)
    return _run_generation(
        ctx, inference_type="VIDEO", service_type="video", noun="video",
        payload={"prompt": prompt},
    )


def _generate_music(ctx: ToolContext, args: dict) -> ToolResult:
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return ToolResult(text="No music prompt was provided.", ok=False)
    payload = {"prompt": prompt}
    if args.get("lyrics"):
        payload["lyrics"] = str(args["lyrics"])
    return _run_generation(
        ctx, inference_type="MUSIC", service_type="music", noun="music", payload=payload,
    )


def _generate_voice(ctx: ToolContext, args: dict) -> ToolResult:
    text = (args.get("text") or "").strip()
    if not text:
        return ToolResult(text="No text was provided to speak.", ok=False)
    return _run_generation(
        ctx, inference_type="VOICE", service_type="tts", noun="voice",
        payload={"input": text},
    )


def _scrape_url(ctx: ToolContext, args: dict) -> ToolResult:
    """Read a web page as markdown via the existing Firecrawl-backed /v1/scrape
    modality (reuses the SCRAPE runner)."""
    url = (args.get("url") or "").strip()
    if not url:
        return ToolResult(text="No URL was provided.", ok=False)
    pm = resolve_provider_model(ctx.user, "scrape")
    if pm is None:
        return ToolResult(text="No scrape service is available to this user.", ok=False)

    from .openai_views import _rerun_scrape

    ir = InferenceRequest.objects.create(
        user=ctx.user, provider=pm.provider, model_name="",
        inference_type="SCRAPE", payload={"url": url}, status="PROCESSING",
    )
    ok, err = _rerun_scrape(ir, pm)
    if not ok:
        return ToolResult(text=f"Could not read the page: {err}", ok=False)
    results = ir.results or {}
    markdown = results.get("markdown") or ""
    title = results.get("title") or ""
    head = f"# {title}\n\n" if title else ""
    return ToolResult(
        text=(head + markdown) or "The page had no readable content.",
        data={"request_id": ir.id, "url": results.get("source_url") or url, "title": title},
    )


def _browse(ctx: ToolContext, args: dict) -> ToolResult:
    """Render a JS-heavy page in a real headless browser (browserless) and return
    its text. Complements scrape for sites that need a browser to load."""
    url = (args.get("url") or "").strip()
    if not url:
        return ToolResult(text="No URL was provided.", ok=False)

    from .views import _tailnet_proxies

    base = settings.AGENT_BROWSERLESS_URL.rstrip("/")
    params = {"token": settings.AGENT_BROWSERLESS_TOKEN} if settings.AGENT_BROWSERLESS_TOKEN else {}
    try:
        resp = requests.post(
            f"{base}/content", params=params, json={"url": url},
            timeout=45, verify=False, proxies=_tailnet_proxies(),
        )
    except requests.RequestException as e:
        return ToolResult(text=f"Browse failed: {e}", ok=False)
    if not resp.ok:
        return ToolResult(text=f"Browse returned HTTP {resp.status_code}.", ok=False)
    text = _html_to_text(resp.text)
    return ToolResult(text=text or "The page had no readable text.", data={"url": url})


def _html_to_text(html: str) -> str:
    """Cheap HTML → text: drop script/style, strip tags, collapse whitespace."""
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html or "")
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# --- registry -----------------------------------------------------------------


def build_registry() -> ToolRegistry:
    """The deployment's tool set. V0: web search + image generation."""
    return ToolRegistry(
        [
            Tool(
                name="web_search",
                description=(
                    "Search the web for current information and return the top "
                    "results (title, URL, snippet). Use for anything time-sensitive "
                    "or factual you are unsure about."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query.",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "How many results to return (1-"
                            f"{settings.AGENT_MAX_SEARCH_RESULTS}).",
                        },
                    },
                    "required": ["query"],
                },
                handler=_web_search,
                available=lambda: bool(settings.AGENT_SEARXNG_URL),
            ),
            Tool(
                name="web_search_brave",
                description=(
                    "Search the web using Brave Search (requires the user's Brave "
                    "API key). Use only if asked for Brave specifically or if the "
                    "default web search is unavailable."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query."},
                        "num_results": {"type": "integer"},
                    },
                    "required": ["query"],
                },
                handler=_web_search_brave,
                full_member_only=True,
            ),
            Tool(
                name="scrape_url",
                description=(
                    "Fetch a web page and return its main content as markdown. Use "
                    "to read an article or page the user references."
                ),
                parameters={
                    "type": "object",
                    "properties": {"url": {"type": "string", "description": "The page URL."}},
                    "required": ["url"],
                },
                handler=_scrape_url,
            ),
            Tool(
                name="browse",
                description=(
                    "Open a URL in a real headless browser and return its rendered "
                    "text. Use for JavaScript-heavy pages that scrape_url can't read."
                ),
                parameters={
                    "type": "object",
                    "properties": {"url": {"type": "string", "description": "The page URL."}},
                    "required": ["url"],
                },
                handler=_browse,
                available=lambda: bool(settings.AGENT_BROWSERLESS_URL),
            ),
            Tool(
                name="generate_image",
                description=(
                    "Generate an image from a text prompt. The image is saved to "
                    "the user's gallery and displayed in the conversation. Use when "
                    "the user asks to create, draw, or generate a picture."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "A detailed description of the image to create.",
                        },
                        "size": {"type": "string", "description": "Optional size like '1024x1024'."},
                    },
                    "required": ["prompt"],
                },
                handler=_generate_image,
            ),
            Tool(
                name="generate_video",
                description=(
                    "Generate a short video from a text prompt. Saved to the user's "
                    "gallery and shown in the chat."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "A description of the video."},
                    },
                    "required": ["prompt"],
                },
                handler=_generate_video,
            ),
            Tool(
                name="generate_music",
                description="Generate music/audio from a text prompt (and optional lyrics).",
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Style/description of the music."},
                        "lyrics": {"type": "string", "description": "Optional lyrics to sing."},
                    },
                    "required": ["prompt"],
                },
                handler=_generate_music,
            ),
            Tool(
                name="generate_voice",
                description="Speak text aloud, returning an audio clip saved to the gallery.",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The text to speak."},
                    },
                    "required": ["text"],
                },
                handler=_generate_voice,
            ),
        ]
        + _mcp_tools()
    )


def _mcp_tools() -> list:
    """External MCP-server tools (V2). Imported lazily to avoid a circular
    import, and best-effort so a misbehaving server can't break the registry."""
    try:
        from .agent_mcp import discover_mcp_tools

        return discover_mcp_tools()
    except Exception:
        logger.exception("MCP tool discovery failed")
        return []


_REGISTRY: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Process-wide registry (tools are stateless; availability is checked per
    call against live settings, so caching the registry is safe)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_registry()
    return _REGISTRY
