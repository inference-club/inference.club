"""Playground Agent (PRD 14): the tool-calling loop, tool registry, the two V0
tools (web_search, generate_image), and the /v1/agent + /v1/agent/tools surface.
All upstream/model/search calls are mocked.
"""
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.inference.models import (
    InferenceRequest,
    MediaAsset,
    Provider,
    ProviderModel,
    ProviderService,
    link_catalog_model,
)

User = get_user_model()

# 1x1 PNG, base64 — a valid decodable image for the fake image upstream.
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture
def user(db):
    return User.objects.create_user(email="agent@example.com", password="x")


@pytest.fixture(autouse=True)
def _agent_settings(settings):
    settings.AGENT_ENABLED = True
    settings.AGENT_SEARXNG_URL = "http://searx.local:8080"
    settings.AGENT_MAX_ITERATIONS = 6
    settings.AGENT_TOOL_OUTPUT_MAX_CHARS = 4000


def _online_provider(u, host="n1"):
    return Provider.objects.create(
        user=u, name=f"node-{host}", tailnet_hostname=host,
        is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
    )


def _model(p, name, service_type):
    svc = ProviderService.objects.create(
        provider=p, name=service_type, engine="other", service_type=service_type,
        access_policy=ProviderService.ACCESS_AUTHENTICATED,
    )
    pm = ProviderModel(provider=p, name=name, service=svc)
    link_catalog_model(pm)
    pm.save()
    return pm


def _client(u):
    from rest_framework.test import APIClient
    c = APIClient()
    c.force_authenticate(user=u)
    return c


class _FakeResp:
    def __init__(self, payload, status=200, content_type="application/json"):
        self._p, self.status_code, self.ok = payload, status, 200 <= status < 300
        self.headers = {"content-type": content_type}
        self.text = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)

    def json(self):
        return self._p

    def close(self):
        pass

    def iter_lines(self, decode_unicode=False):
        """Emulate a streamed chat-completion: replay this (non-streaming) chat
        payload as SSE delta chunks so the agent's streaming model call parses it
        the same way it parses a real upstream. Non-chat payloads yield nothing."""
        p = self._p if isinstance(self._p, dict) else {}
        choices = p.get("choices") or []
        msg = (choices[0].get("message") if choices else {}) or {}
        rc = msg.get("reasoning_content") or msg.get("reasoning")
        if rc:
            yield "data: " + json.dumps({"choices": [{"index": 0, "delta": {"reasoning_content": rc}}]})
        if msg.get("content"):
            yield "data: " + json.dumps({"choices": [{"index": 0, "delta": {"content": msg["content"]}}]})
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            delta_tc = {
                "index": i, "id": tc.get("id"), "type": "function",
                "function": {"name": fn.get("name", ""), "arguments": fn.get("arguments", "")},
            }
            yield "data: " + json.dumps({"choices": [{"index": 0, "delta": {"tool_calls": [delta_tc]}}]})
        if p.get("usage"):
            yield "data: " + json.dumps({"choices": [], "usage": p["usage"]})
        yield "data: [DONE]"


def _chat_msg_tool(name, args, call_id="c1"):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }],
    }


def _chat_resp(message, usage=None):
    return _FakeResp({
        "choices": [{"message": message}],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    })


def _search_resp(n=2):
    return _FakeResp({"results": [
        {"title": f"Result {i}", "url": f"http://ex/{i}", "content": f"snippet {i}"}
        for i in range(n)
    ]})


def _image_upstream_resp():
    return _FakeResp({"created": 1, "data": [{"b64_json": PNG_B64}]})


def _post_agent(client, body):
    return client.post("/v1/agent", {**body, "stream": False}, format="json")


# --- plain answer (no tools) -------------------------------------------------


class TestPlainAnswer:
    def test_answers_without_tools_and_meters(self, user):
        _model(_online_provider(user), "chat-llm", "llm")
        with patch(
            "apps.inference.agent.requests.post",
            return_value=_chat_resp({"role": "assistant", "content": "Hello there."}),
        ):
            resp = _post_agent(_client(user), {
                "model": "chat-llm",
                "messages": [{"role": "user", "content": "hi"}],
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["content"] == "Hello there."
        assert body["tool_events"] == []
        assert body["usage"]["completion_tokens"] == 5
        # one LLM request recorded for metering
        ir = InferenceRequest.objects.get(user=user, inference_type="LLM")
        assert ir.status == "PROCESSED"
        assert ir.payload.get("agent") is True

    def test_no_provider_errors(self, user):
        # No model registered → routing fails.
        resp = _post_agent(_client(user), {
            "model": "missing", "messages": [{"role": "user", "content": "hi"}],
        })
        assert resp.status_code == 502
        assert resp.json()["error"]["type"] == "agent_error"


# --- web_search tool ---------------------------------------------------------


class TestWebSearch:
    def test_search_then_answer(self, user):
        _model(_online_provider(user), "chat-llm", "llm")
        # First model turn asks for a search; second answers.
        chat = patch("apps.inference.agent.requests.post", side_effect=[
            _chat_resp(_chat_msg_tool("web_search", {"query": "cats in space"})),
            _chat_resp({"role": "assistant", "content": "Cats love space."}),
        ])
        search = patch("apps.inference.agent_tools.requests.get", return_value=_search_resp(2))
        with chat, search:
            resp = _post_agent(_client(user), {
                "model": "chat-llm",
                "messages": [{"role": "user", "content": "search cats in space"}],
            })
        body = resp.json()
        assert body["content"] == "Cats love space."
        kinds = [e["type"] for e in body["tool_events"]]
        assert "tool_call" in kinds and "tool_result" in kinds
        result = next(e for e in body["tool_events"] if e["type"] == "tool_result")
        assert result["name"] == "web_search" and result["ok"] is True
        assert len(result["data"]["results"]) == 2
        # two model turns metered
        assert InferenceRequest.objects.filter(user=user, inference_type="LLM").count() == 2

    def test_search_disabled_when_unconfigured(self, user, settings):
        settings.AGENT_SEARXNG_URL = ""
        names = [t["name"] for t in _client(user).get("/v1/agent/tools").json()["data"]]
        assert "web_search" not in names
        assert "generate_image" in names

    def test_tool_output_truncated(self, user, settings):
        settings.AGENT_TOOL_OUTPUT_MAX_CHARS = 50
        _model(_online_provider(user), "chat-llm", "llm")
        big = [{"title": "T" * 100, "url": "http://x", "content": "C" * 100}]
        chat = patch("apps.inference.agent.requests.post", side_effect=[
            _chat_resp(_chat_msg_tool("web_search", {"query": "x"})),
            _chat_resp({"role": "assistant", "content": "done"}),
        ])
        search = patch("apps.inference.agent_tools.requests.get",
                       return_value=_FakeResp({"results": big}))
        with chat, search:
            resp = _post_agent(_client(user), {
                "model": "chat-llm", "messages": [{"role": "user", "content": "x"}],
            })
        result = next(e for e in resp.json()["tool_events"] if e["type"] == "tool_result")
        assert "…(truncated)" in result["summary"]
        assert len(result["summary"]) <= 50 + len("\n…(truncated)")


# --- generate_image tool -----------------------------------------------------


class TestGenerateImage:
    def test_generates_owned_image(self, user):
        p = _online_provider(user)
        _model(p, "chat-llm", "llm")
        _model(p, "image-model", "image")
        # The chat loop (agent) and _rerun_image (openai_views) both call the
        # *same* global requests.post — route by upstream path with one mock.
        chat_turns = iter([
            _chat_resp(_chat_msg_tool("generate_image", {"prompt": "a cat in a spaceship"})),
            _chat_resp({"role": "assistant", "content": "Here is your image."}),
        ])

        def _post(url, **kw):
            if url.endswith("/chat/completions"):
                return next(chat_turns)
            if url.endswith("/images/generations"):
                return _image_upstream_resp()
            raise AssertionError(f"unexpected upstream {url}")

        with patch("apps.inference.agent.requests.post", side_effect=_post):
            resp = _post_agent(_client(user), {
                "model": "chat-llm",
                "messages": [{"role": "user", "content": "make a cat in a spaceship"}],
            })
        body = resp.json()
        assert body["content"] == "Here is your image."
        result = next(e for e in body["tool_events"] if e["type"] == "tool_result")
        assert result["name"] == "generate_image" and result["ok"] is True
        assert len(result["data"]["media"]) == 1
        assert result["data"]["media"][0]["url"].startswith("http")
        assert result["data"]["media"][0]["kind"] == "image"
        # a real, owned image request + asset
        ir = InferenceRequest.objects.get(user=user, inference_type="IMAGE")
        assert ir.status == "PROCESSED"
        assert MediaAsset.objects.filter(user=user, kind="OUTPUT_IMAGE").count() == 1

    def test_no_image_provider_reports_to_model(self, user):
        _model(_online_provider(user), "chat-llm", "llm")  # no image model
        chat = patch("apps.inference.agent.requests.post", side_effect=[
            _chat_resp(_chat_msg_tool("generate_image", {"prompt": "x"})),
            _chat_resp({"role": "assistant", "content": "Sorry, no image model."}),
        ])
        with chat:
            resp = _post_agent(_client(user), {
                "model": "chat-llm", "messages": [{"role": "user", "content": "draw x"}],
            })
        result = next(e for e in resp.json()["tool_events"] if e["type"] == "tool_result")
        assert result["ok"] is False
        assert "image" in result["summary"].lower()
        assert not MediaAsset.objects.filter(user=user).exists()


# --- loop guards + endpoint --------------------------------------------------


class TestLoopGuards:
    def test_iteration_cap_forces_final_answer(self, user, settings):
        settings.AGENT_MAX_ITERATIONS = 2
        _model(_online_provider(user), "chat-llm", "llm")

        def _post(url, **kw):
            payload = kw.get("json") or {}
            if "tools" in payload:  # keep asking for a tool while tools are offered
                return _chat_resp(_chat_msg_tool("web_search", {"query": "x"}))
            return _chat_resp({"role": "assistant", "content": "forced final"})

        chat = patch("apps.inference.agent.requests.post", side_effect=_post)
        search = patch("apps.inference.agent_tools.requests.get", return_value=_search_resp(1))
        with chat, search:
            resp = _post_agent(_client(user), {
                "model": "chat-llm", "messages": [{"role": "user", "content": "loop"}],
            })
        body = resp.json()
        assert body["content"] == "forced final"
        # 2 tool rounds → 2 tool_calls; then a forced no-tools final
        calls = [e for e in body["tool_events"] if e["type"] == "tool_call"]
        assert len(calls) == 2

    def test_disabled_returns_503(self, user, settings):
        settings.AGENT_ENABLED = False
        resp = _post_agent(_client(user), {
            "model": "chat-llm", "messages": [{"role": "user", "content": "hi"}],
        })
        assert resp.status_code == 503

    def test_validation_errors(self, user):
        c = _client(user)
        assert c.post("/v1/agent", {"messages": []}, format="json").status_code == 400
        assert c.post("/v1/agent", {"model": "m"}, format="json").status_code == 400

    def test_requires_auth(self, db):
        from rest_framework.test import APIClient
        resp = APIClient().post("/v1/agent", {"model": "m", "messages": [{"role": "user", "content": "x"}]}, format="json")
        assert resp.status_code in (401, 403)


class TestToolsEndpoint:
    def test_lists_available_tools(self, user):
        data = _client(user).get("/v1/agent/tools").json()
        assert data["enabled"] is True
        names = {t["name"] for t in data["data"]}
        assert {"web_search", "generate_image", "scrape_url", "generate_video"} <= names

    def test_browse_gated_on_config(self, user, settings):
        settings.AGENT_BROWSERLESS_URL = ""
        names = {t["name"] for t in _client(user).get("/v1/agent/tools").json()["data"]}
        assert "browse" not in names
        settings.AGENT_BROWSERLESS_URL = "http://browserless.local:3000"
        names = {t["name"] for t in _client(user).get("/v1/agent/tools").json()["data"]}
        assert "browse" in names


# --- V1: scrape + generation modalities --------------------------------------


class TestScrapeTool:
    def test_scrape_reads_page(self, user):
        p = _online_provider(user)
        _model(p, "chat-llm", "llm")
        _model(p, "scrape-svc", "scrape")
        chat_turns = iter([
            _chat_resp(_chat_msg_tool("scrape_url", {"url": "http://example.com"})),
            _chat_resp({"role": "assistant", "content": "The page says hello."}),
        ])

        def _post(url, **kw):
            if url.endswith("/chat/completions"):
                return next(chat_turns)
            if url.endswith("/scrape"):
                return _FakeResp("scraped markdown body", content_type="text/markdown")
            raise AssertionError(f"unexpected {url}")

        with patch("apps.inference.agent.requests.post", side_effect=_post):
            resp = _post_agent(_client(user), {
                "model": "chat-llm",
                "messages": [{"role": "user", "content": "read example.com"}],
            })
        result = next(e for e in resp.json()["tool_events"] if e["type"] == "tool_result")
        assert result["ok"] is True and "scraped markdown body" in result["summary"]
        assert InferenceRequest.objects.filter(user=user, inference_type="SCRAPE").count() == 1
        assert MediaAsset.objects.filter(user=user, kind="OUTPUT_DOC").count() == 1

    def test_generate_video_without_provider_reports(self, user):
        _model(_online_provider(user), "chat-llm", "llm")  # no video service
        chat = patch("apps.inference.agent.requests.post", side_effect=[
            _chat_resp(_chat_msg_tool("generate_video", {"prompt": "a dog"})),
            _chat_resp({"role": "assistant", "content": "no video model sorry"}),
        ])
        with chat:
            resp = _post_agent(_client(user), {
                "model": "chat-llm", "messages": [{"role": "user", "content": "make a video"}],
            })
        result = next(e for e in resp.json()["tool_events"] if e["type"] == "tool_result")
        assert result["ok"] is False and "video" in result["summary"].lower()


# --- V1: Brave search + per-user key -----------------------------------------


def _guest(db):
    return User.objects.create_user(
        email="guest@example.com", password="x", account_type=User.AccountType.GUEST,
    )


class TestBrave:
    def test_brave_without_key_guides_user(self, user):
        _model(_online_provider(user), "chat-llm", "llm")
        chat = patch("apps.inference.agent.requests.post", side_effect=[
            _chat_resp(_chat_msg_tool("web_search_brave", {"query": "x"})),
            _chat_resp({"role": "assistant", "content": "set a key"}),
        ])
        with chat:
            resp = _post_agent(_client(user), {
                "model": "chat-llm", "messages": [{"role": "user", "content": "brave search x"}],
            })
        result = next(e for e in resp.json()["tool_events"] if e["type"] == "tool_result")
        assert result["ok"] is False and "brave" in result["summary"].lower()

    def test_brave_with_key_searches(self, user):
        user.brave_api_key = "secret"
        user.save(update_fields=["brave_api_key"])
        _model(_online_provider(user), "chat-llm", "llm")
        chat = patch("apps.inference.agent.requests.post", side_effect=[
            _chat_resp(_chat_msg_tool("web_search_brave", {"query": "x"})),
            _chat_resp({"role": "assistant", "content": "found it"}),
        ])
        brave = patch("apps.inference.agent_tools.requests.get", return_value=_FakeResp(
            {"web": {"results": [{"title": "T", "url": "http://b", "description": "d"}]}}
        ))
        with chat, brave:
            resp = _post_agent(_client(user), {
                "model": "chat-llm", "messages": [{"role": "user", "content": "brave x"}],
            })
        result = next(e for e in resp.json()["tool_events"] if e["type"] == "tool_result")
        assert result["ok"] is True and len(result["data"]["results"]) == 1

    def test_brave_tool_hidden_from_guests(self, db):
        guest = _guest(db)
        names = {t["name"] for t in _client(guest).get("/v1/agent/tools").json()["data"]}
        assert "web_search_brave" not in names
        assert "web_search" in names  # non-gated tools still offered

    def test_brave_key_endpoint_roundtrip(self, user):
        c = _client(user)
        assert c.get("/v1/agent/tools").json()["brave_key_set"] is False
        assert c.post("/v1/agent/brave-key", {"api_key": "abc"}, format="json").status_code == 200
        user.refresh_from_db()
        assert user.brave_api_key == "abc"
        assert c.get("/v1/agent/tools").json()["brave_key_set"] is True
        assert c.delete("/v1/agent/brave-key").status_code == 200
        user.refresh_from_db()
        assert user.brave_api_key == ""

    def test_brave_key_endpoint_blocks_guests(self, db):
        resp = _client(_guest(db)).post("/v1/agent/brave-key", {"api_key": "abc"}, format="json")
        assert resp.status_code == 403


# --- V2: skills + MCP --------------------------------------------------------


class TestSkills:
    def test_skills_listed(self, user):
        skills = _client(user).get("/v1/agent/tools").json()["skills"]
        names = {s["name"] for s in skills}
        assert {"researcher", "artist", "producer"} <= names

    def test_skill_narrows_tools_and_injects_prompt(self, user):
        _model(_online_provider(user), "chat-llm", "llm")
        captured = {}

        def _post(url, **kw):
            p = kw.get("json") or {}
            if "tools" in p:
                captured["tools"] = [t["function"]["name"] for t in p["tools"]]
            captured["sys"] = (p.get("messages") or [{}])[0].get("content", "")
            return _chat_resp({"role": "assistant", "content": "ok"})

        with patch("apps.inference.agent.requests.post", side_effect=_post):
            resp = _post_agent(_client(user), {
                "model": "chat-llm",
                "skill": "artist",
                "messages": [{"role": "user", "content": "draw a sunset"}],
            })
        assert resp.status_code == 200
        # Only the artist's tool is offered; its guidance leads the system prompt.
        assert captured["tools"] == ["generate_image"]
        assert "creative" in captured["sys"].lower()


MCP_URL = "http://mcp.local/rpc"


class TestMCP:
    def test_mcp_tool_registered_and_callable(self, user, settings):
        settings.AGENT_MCP_SERVERS = [{"name": "demo", "url": MCP_URL}]
        _model(_online_provider(user), "chat-llm", "llm")
        chat_turns = iter([
            _chat_resp(_chat_msg_tool("demo__echo", {"text": "hi"})),
            _chat_resp({"role": "assistant", "content": "the tool echoed."}),
        ])

        def _post(url, **kw):
            if url.endswith("/chat/completions"):
                return next(chat_turns)
            if url == MCP_URL:
                method = (kw.get("json") or {}).get("method")
                if method == "tools/list":
                    return _FakeResp({"result": {"tools": [{
                        "name": "echo", "description": "Echo text",
                        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
                    }]}})
                if method == "tools/call":
                    return _FakeResp({"result": {"content": [{"type": "text", "text": "echoed: hi"}]}})
            raise AssertionError(f"unexpected {url}")

        from apps.inference.agent import run_agent
        from apps.inference.agent_tools import build_registry

        with patch("apps.inference.agent.requests.post", side_effect=_post):
            reg = build_registry()
            assert reg.get("demo__echo") is not None
            events = list(run_agent(
                user=user, request=None, model="chat-llm", registry=reg,
                messages=[{"role": "user", "content": "echo hi"}],
            ))
        result = next(e for e in events if e["type"] == "tool_result")
        assert result["name"] == "demo__echo" and result["summary"] == "echoed: hi"

    def test_mcp_server_down_is_skipped(self, user, settings):
        settings.AGENT_MCP_SERVERS = [{"name": "demo", "url": MCP_URL}]
        from apps.inference.agent_tools import build_registry

        def _boom(url, **kw):
            raise Exception("connection refused")

        with patch("apps.inference.agent.requests.post", side_effect=_boom):
            reg = build_registry()
        assert reg.get("demo__echo") is None  # discovery failed → simply absent
