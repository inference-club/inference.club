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

import requests
from django.conf import settings


@dataclass
class MintedKey:
    authkey: str
    login_server: str = ""


def mint_authkey_for_provider(provider) -> MintedKey:
    if settings.TAILSCALE_OAUTH_CLIENT_ID and settings.TAILSCALE_OAUTH_CLIENT_SECRET:
        try:
            return _mint_via_oauth(provider)
        except Exception:
            # Fall through to the static-key fallback so a misconfigured
            # OAuth client doesn't permanently brick registration.
            pass
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

    tailnet = settings.TAILSCALE_TAILNET or "-"
    resp = requests.post(
        f"https://api.tailscale.com/api/v2/tailnet/{tailnet}/keys",
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
            "description": f"club-host-{provider.id} ({provider.user.email})",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return MintedKey(authkey=resp.json()["key"])
