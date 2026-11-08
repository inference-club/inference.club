"""Remote MCP server (/mcp): JSON-RPC lifecycle + tools dispatching to /v1."""
import io
import wave
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.inference.models import (
    InferenceRequest, Provider, ProviderModel, ProviderService, link_catalog_model,
)

User = get_user_model()


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.ASYNC_ENABLED = True
    settings.SYNC_CAPACITY_WAIT_SECONDS = 0
    settings.MCP_TOOL_WAIT_SECONDS = 0


@pytest.fixture
def user(db):
    return User.objects.create_user(email="mcp@example.com", password="x")


@pytest.fixture
def client(user):
    tok, _ = Token.objects.get_or_create(user=user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {tok.key}")
    return c


def _rpc(c, method, params=None, rid=1):
    msg = {"jsonrpc": "2.0", "method": method, "id": rid}
    if params is not None:
        msg["params"] = params
    return c.post("/mcp", msg, format="json")


def _music_model(u):
    p = Provider.objects.create(user=u, name="node", tailnet_hostname="n1", is_active=True,
                                accepting_requests=True, last_seen_at=timezone.now())
    svc = ProviderService.objects.create(provider=p, name="ace", engine="other",
                                         service_type="music",
                                         access_policy=ProviderService.ACCESS_AUTHENTICATED)
    pm = ProviderModel(provider=p, name="acestep", service=svc)
    link_catalog_model(pm)
    pm.save()
    return pm


def _wav():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 4000)
    return buf.getvalue()


class _Resp:
    def __init__(self, content):
        self.content = content; self.status_code = 200; self.ok = True
        self.headers = {"content-type": "audio/wav"}; self.text = ""


def test_requires_auth(db):
    assert APIClient().post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                            format="json").status_code == 401


def test_initialize_and_list_tools(client):
    r = _rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "t", "version": "1"}}).json()
    assert r["result"]["protocolVersion"] == "2025-06-18"
    assert "tools" in r["result"]["capabilities"]
    assert client.post("/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"},
                       format="json").status_code == 202
    tools = {t["name"] for t in _rpc(client, "tools/list").json()["result"]["tools"]}
    assert {"generate_image", "generate_video", "get_job", "chat", "list_models"} <= tools


def test_generate_music_returns_url(client, user):
    _music_model(user)
    with patch("apps.inference.openai_views.requests.post", return_value=_Resp(_wav())):
        r = _rpc(client, "tools/call", {"name": "generate_music",
                                        "arguments": {"prompt": "lofi"}}).json()["result"]
    assert r["isError"] is False
    sc = r["structuredContent"]
    assert sc["status"] == "PROCESSED"
    assert sc["media"][0]["kind"] == "audio"
    assert any(c["type"] == "resource_link" for c in r["content"])


def test_busy_device_queues_and_get_job(client, user):
    pm = _music_model(user)
    InferenceRequest.objects.create(user=user, provider=pm.provider, model_name="acestep",
                                    inference_type="MUSIC", status="PROCESSING", is_async=True,
                                    job_service_type="music", payload={})
    with patch("apps.inference.openai_views.requests.post") as up, \
            patch("apps.inference.jobs.kick_dispatch"):
        r = _rpc(client, "tools/call", {"name": "generate_music",
                                        "arguments": {"prompt": "lofi"}}).json()["result"]
    up.assert_not_called()
    sc = r["structuredContent"]
    assert sc["status"] == "QUEUED" and sc["queued_reason"] == "at_capacity"
    r2 = _rpc(client, "tools/call", {"name": "get_job",
                                     "arguments": {"job_id": sc["job_id"]}}).json()["result"]
    assert r2["structuredContent"]["status"] == "QUEUED"


def test_tool_error_is_reported_not_raised(client):
    r = _rpc(client, "tools/call", {"name": "generate_image",
                                    "arguments": {"prompt": "x"}}).json()["result"]
    assert r["isError"] is True


def test_unknown_method(client):
    assert _rpc(client, "nope").json()["error"]["code"] == -32601
