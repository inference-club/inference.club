"""External LLM providers — OpenRouter / NVIDIA NIM / Groq (PRD 19).

Two jobs:
  1. Resolve a namespaced ``provider:model`` id to an OpenAI-compatible cloud the
     user holds a key for (``resolve_external_target``), so the chat proxy and the
     agent can forward to it over HTTPS with ``Authorization: Bearer <user key>``.
  2. Fetch + cache each provider's model catalog so users can browse and pin.

External providers are a different archetype from tailnet agents: real HTTPS
(``verify=True``), no SOCKS sidecar, a per-user Bearer key. They are LLM-only, so
only the LLM forward path consumes this module.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from django.core.cache import cache

from .external_keys import get_service, get_user_api_key, is_llm_provider

logger = logging.getLogger(__name__)

EXTERNAL_FETCH_TIMEOUT = 15
CATALOG_TTL = 3600  # provider model lists change slowly; cache per-provider 1h


@dataclass
class ExternalTarget:
    slug: str
    label: str
    base_url: str  # OpenAI-compatible root, no trailing slash
    upstream_model: str  # the id to send upstream (prefix stripped)
    api_key: str
    public_id: str  # the namespaced id, for logging/metering

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}


def split_external_model(model_id):
    """Return ``(slug, upstream_id)`` if ``model_id`` is a known LLM-provider
    namespaced id (``openrouter:anthropic/claude-3.7-sonnet``), else None.
    Splits on the FIRST colon — upstream ids contain ``/`` but not ``:``."""
    if not isinstance(model_id, str) or ":" not in model_id:
        return None
    slug, _, upstream = model_id.partition(":")
    if not is_llm_provider(slug) or not upstream:
        return None
    return slug, upstream


def resolve_external_target(user, model_id):
    """An ``ExternalTarget`` when ``model_id`` names an external provider model
    AND the user has a key for it; else None (caller falls back to tailnet)."""
    parsed = split_external_model(model_id)
    if parsed is None:
        return None
    slug, upstream = parsed
    key = get_user_api_key(user, slug)
    if not key:
        return None
    svc = get_service(slug)
    return ExternalTarget(
        slug=slug,
        label=svc.name,
        base_url=svc.base_url.rstrip("/"),
        upstream_model=upstream,
        api_key=key,
        public_id=model_id,
    )


def external_model_missing_key(user, model_id) -> bool:
    """True when ``model_id`` names an external provider the user has NO key for,
    so the caller can return a clear 'add your key' error rather than a vague
    no-provider."""
    parsed = split_external_model(model_id)
    if parsed is None:
        return False
    return not get_user_api_key(user, parsed[0])


def fetch_provider_catalog(user, slug, *, force=False):
    """The provider's raw model list (list of upstream dicts), cached per-provider
    ~1h. Uses the user's key to fetch. Raises ValueError (unknown provider),
    PermissionError (no key), or requests.HTTPError (upstream failure)."""
    svc = get_service(slug)
    if svc is None or not is_llm_provider(slug):
        raise ValueError(f"Unknown LLM provider: {slug}")
    key = get_user_api_key(user, slug)
    if not key:
        raise PermissionError(f"No API key set for {svc.name}.")
    ckey = f"extcatalog:{slug}"
    if not force:
        cached = cache.get(ckey)
        if cached is not None:
            return cached
    url = svc.base_url.rstrip("/") + svc.models_path
    resp = requests.get(
        url, headers={"Authorization": f"Bearer {key}"},
        timeout=EXTERNAL_FETCH_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    models = data.get("data") if isinstance(data, dict) else data
    if not isinstance(models, list):
        models = []
    cache.set(ckey, models, CATALOG_TTL)
    return models


def normalize_catalog_entry(raw: dict) -> dict:
    """Uniform shape for one catalog model across providers. OpenRouter nests
    caps under ``architecture``/``top_provider``; Groq/NVIDIA return flat
    ``{id}`` — default everything sensibly."""
    mid = raw.get("id") or raw.get("name") or ""
    arch = raw.get("architecture") if isinstance(raw.get("architecture"), dict) else {}
    top = raw.get("top_provider") if isinstance(raw.get("top_provider"), dict) else {}
    in_mods = arch.get("input_modalities") or ["text"]
    if not isinstance(in_mods, list):
        in_mods = ["text"]
    ctx = raw.get("context_length") or raw.get("context_window") or top.get("context_length")
    return {
        "model_id": mid,
        "display_name": raw.get("name") or mid,
        "context_length": ctx,
        "input_modalities": in_mods,
    }
