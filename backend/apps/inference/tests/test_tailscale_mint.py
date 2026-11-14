"""Tailscale auth-key minting: OAuth path request shape + static fallback."""

import re
from types import SimpleNamespace
from unittest import mock

import pytest
import requests

from apps.inference import tailscale


def _provider(email="someone@example.com", handle="brian.caffey"):
    return SimpleNamespace(id=7, user=SimpleNamespace(email=email, handle=handle, username="x"))


def _resp(status, payload):
    r = mock.Mock(status_code=status, text=str(payload))
    r.json.return_value = payload
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(f"{status}", response=r)
    else:
        r.raise_for_status.return_value = None
    return r


@pytest.fixture
def oauth_settings(settings):
    settings.TAILSCALE_OAUTH_CLIENT_ID = "cid"
    settings.TAILSCALE_OAUTH_CLIENT_SECRET = "secret"
    settings.TAILSCALE_STATIC_AUTHKEY = "tskey-static"
    settings.TAILSCALE_HOST_TAG = "tag:club-host"
    settings.TAILSCALE_TAILNET = "tailb224b8"
    return settings


def test_oauth_mint_sends_tailscale_safe_description(oauth_settings):
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        if url.endswith("/oauth/token"):
            return _resp(200, {"access_token": "at"})
        return _resp(200, {"key": "tskey-minted"})

    with mock.patch.object(tailscale.requests, "post", side_effect=fake_post):
        minted = tailscale.mint_authkey_for_provider(_provider())

    assert minted.authkey == "tskey-minted"
    url, kw = calls[1]
    # OAuth clients are bound to one tailnet; "-" avoids depending on the
    # MagicDNS-style TAILSCALE_TAILNET value.
    assert url == "https://api.tailscale.com/api/v2/tailnet/-/keys"
    desc = kw["json"]["description"]
    assert re.fullmatch(r"[A-Za-z0-9 _-]{1,50}", desc), desc
    assert "@" not in desc
    create = kw["json"]["capabilities"]["devices"]["create"]
    assert create["ephemeral"] and create["preauthorized"]
    assert create["tags"] == ["tag:club-host"]


def test_oauth_failure_falls_back_to_static_and_logs(oauth_settings, caplog):
    def fake_post(url, **kw):
        if url.endswith("/oauth/token"):
            return _resp(200, {"access_token": "at"})
        return _resp(400, {"message": "keys: description had invalid characters"})

    with mock.patch.object(tailscale.requests, "post", side_effect=fake_post):
        minted = tailscale.mint_authkey_for_provider(_provider())

    assert minted.authkey == "tskey-static"
    assert "OAuth key mint failed" in caplog.text
    assert "invalid characters" in caplog.text
