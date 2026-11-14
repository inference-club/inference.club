"""Mint Tailscale auth keys for provider agents.

Two paths, in priority order:

1. **OAuth client** (production). If TAILSCALE_OAUTH_CLIENT_ID/SECRET are set,
   we mint a fresh ephemeral, preauthorized, single-use, tagged auth key per
   provider. Each agent gets a unique short-lived credential.

2. **Static reusable auth key** (bootstrap / MVP). If TAILSCALE_STATIC_AUTHKEY
   is set, we hand the same reusable+ephemeral+tagged key to every agent.
   Less secure (compromise of one agent compromises the key) but trivially
   easy to set up while iterating.

Falls back to an empty key if neither is configured — registration succeeds
but the agent will fail to join the tailnet, which is the right "loud" failure
mode.
"""
from dataclasses import dataclass

import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class MintedKey:
    authkey: str
    login_server: str = ""


def mint_authkey_for_provider(provider) -> MintedKey:
    if settings.TAILSCALE_OAUTH_CLIENT_ID and settings.TAILSCALE_OAUTH_CLIENT_SECRET:
        try:
            return _mint_via_oauth(provider)
        except Exception as exc:
            # Fall through to the static-key fallback so a misconfigured
            # OAuth client doesn't permanently brick registration — but say
            # so loudly, or an expired static key looks like a tsnet bug.
            detail = getattr(getattr(exc, "response", None), "text", "")[:300]
            logger.error(
                "Tailscale OAuth key mint failed for provider %s; falling back "
                "to TAILSCALE_STATIC_AUTHKEY: %s %s",
                provider.id, exc, detail,
            )
    if settings.TAILSCALE_STATIC_AUTHKEY:
        return MintedKey(authkey=settings.TAILSCALE_STATIC_AUTHKEY)
    return MintedKey(authkey="")


def _mint_via_oauth(provider) -> MintedKey:
    token_resp = requests.post(
        "https://api.tailscale.com/api/v2/oauth/token",
        data={
            "client_id": settings.TAILSCALE_OAUTH_CLIENT_ID,
            "client_secret": settings.TAILSCALE_OAUTH_CLIENT_SECRET,
        },
        timeout=10,
    )
    token_resp.raise_for_status()
    access = token_resp.json()["access_token"]

    # Always "-" (the OAuth client's own tailnet). TAILSCALE_TAILNET holds the
    # MagicDNS name used to build agent FQDNs (e.g. "tailXXXX"), which the
    # keys API does not necessarily accept as a tailnet identifier.
    resp = requests.post(
        "https://api.tailscale.com/api/v2/tailnet/-/keys",
        headers={"Authorization": f"Bearer {access}"},
        json={
            "capabilities": {
                "devices": {
                    "create": {
                        "reusable": False,
                        "ephemeral": True,
                        "preauthorized": True,
                        "tags": [settings.TAILSCALE_HOST_TAG],
                    }
                }
            },
            "expirySeconds": 900,
            "description": _key_description(provider),
        },
        timeout=10,
    )
    resp.raise_for_status()
    return MintedKey(authkey=resp.json()["key"])


def _key_description(provider) -> str:
    """Tailscale rejects descriptions with characters outside [A-Za-z0-9 -_]
    (an email's "@" or parentheses -> 400 "description had invalid
    characters") and caps them at 50 chars."""
    handle = getattr(provider.user, "handle", "") or getattr(provider.user, "username", "")
    desc = f"club-host-{provider.id} {handle}".strip()
    return re.sub(r"[^A-Za-z0-9 _-]", "-", desc)[:50]
