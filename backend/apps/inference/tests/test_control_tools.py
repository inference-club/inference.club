"""Control tools (apps/inference/control_tools.py): the account actions shared
by the MCP server, the in-app assistant and the ``ic`` CLI."""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.inference import agent as agent_loop
from apps.inference.models import Collection, InferenceRequest

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}
    settings.FRONTEND_BASE_URL = "https://app.example"
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@pytest.fixture
def user(db):
    return User.objects.create_user(email="owner@ex.com", password="x")


@pytest.fixture
def other(db):
    return User.objects.create_user(email="other@ex.com", password="x")


def _client(u):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {Token.objects.get_or_create(user=u)[0].key}")
    return c


def _call(u, tool, **args):
    r = _client(u).post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                 "params": {"name": tool, "arguments": args}}, format="json")
    assert r.status_code == 200, r.content
    res = r.json()["result"]
    return res.get("structuredContent") or {}, res["isError"], res["content"][0]["text"]


def _song(u, title="Rain", visibility="PRIVATE", **payload):
    return InferenceRequest.objects.create(
        user=u, inference_type="MUSIC", status="PROCESSED", title=title,
        visibility=visibility, payload={"prompt": "lofi piano", **payload})


def test_tools_are_listed_with_schemas(user):
    r = _client(user).post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                           format="json")
    tools = {t["name"]: t for t in r.json()["result"]["tools"]}
    for name in ("search_library", "update_item", "set_visibility_many", "delete_item",
                 "save_collection", "collection_items", "get_settings", "update_settings",
                 "services", "play_music", "open_page", "make_song", "api_request"):
        assert name in tools
        assert tools[name]["inputSchema"]["type"] == "object"
        assert "handler" not in tools[name]  # only JSON-able fields leave the server


def test_search_finds_by_title_and_reports_a_summary(user, other):
    _song(user, "Urban Rainfall")
    _song(user, "Desert Noon")
    _song(other, "Rain elsewhere")
    out, err, _ = _call(user, "search_library", kind="song", query="rain")
    assert not err
    assert [i["title"] for i in out["items"]] == ["Urban Rainfall"]
    assert out["summary"].startswith("Found 1 song")
    assert out["items"][0]["page"].startswith("https://app.example/dashboard/")


def test_update_item_renames_and_changes_visibility(user):
    s = _song(user)
    out, err, _ = _call(user, "update_item", id=s.id, title="Harbor Light",
                        visibility="UNLISTED", starred=True)
    assert not err
    s.refresh_from_db()
    assert (s.title, s.visibility) == ("Harbor Light", "UNLISTED")
    assert "renamed it to “Harbor Light”" in out["summary"]
    assert out["item"]["starred"] is True


def test_cannot_change_someone_elses_item(user, other):
    s = _song(other, visibility="PUBLIC")
    _, err, text = _call(user, "update_item", id=s.id, visibility="SECRET")
    assert err and "403" in text
    s.refresh_from_db()
    assert s.visibility == "PUBLIC"


def test_set_visibility_many_by_search(user):
    a, b = _song(user, "Rain one"), _song(user, "Rain two")
    keep = _song(user, "Sunshine")
    out, err, _ = _call(user, "set_visibility_many", visibility="PUBLIC", kind="song",
                        query="rain")
    assert not err and sorted(out["changed"]) == sorted([a.id, b.id])
    keep.refresh_from_db()
    assert keep.visibility == "PRIVATE"


def test_delete_takes_two_calls(user):
    s = _song(user)
    # confirm: true on the first call is not enough — nobody has been asked yet.
    out, err, _ = _call(user, "delete_item", id=s.id, confirm=True)
    assert not err and out["needs_confirmation"] is True
    assert InferenceRequest.objects.filter(id=s.id).exists()
    out, err, _ = _call(user, "delete_item", id=s.id, confirm=True)
    assert not err and out["deleted"] == s.id
    assert not InferenceRequest.objects.filter(id=s.id).exists()


def test_collections_create_fill_and_rename(user):
    s = _song(user)
    out, _, _ = _call(user, "collection_items", collection="Road trip", item_ids=[s.id])
    assert out["count"] == 1  # created on first use
    out, _, _ = _call(user, "get_collection", collection="road trip")
    assert [i["id"] for i in out["items"]] == [s.id]
    _call(user, "save_collection", collection="Road trip", name="Long drive",
          visibility="PUBLIC")
    col = Collection.objects.get(user=user)
    assert (col.name, col.visibility) == ("Long drive", "PUBLIC")
    _, err, text = _call(user, "get_collection", collection="nope")
    assert err and "Long drive" in text  # the error names what does exist


def test_settings_round_trip_and_never_leak_the_token(user):
    out, err, text = _call(user, "update_settings", default_visibility="SECRET",
                           default_collection="Drafts")
    assert not err
    user.refresh_from_db()
    assert user.default_request_visibility == "SECRET"
    assert user.default_collection_name == "Drafts"
    out, _, text = _call(user, "get_settings")
    assert out["settings"]["default_collection"] == "Drafts"
    assert Token.objects.get(user=user).key not in text


def test_api_request_reaches_the_api_but_not_credentials(user):
    out, err, text = _call(user, "api_request", method="GET", path="/api/account/")
    assert not err and out["status"] == 200
    assert out["data"]["api_token"] == "[hidden]"
    assert Token.objects.get(user=user).key not in text
    for path in ("/api/token/", "/api/login/", "/admin/", "/v1/agent", "/mcp",
                 "/api/inference/agent/register/"):
        _, err, _ = _call(user, "api_request", method="POST", path=path)
        assert err, path
    _, err, _ = _call(user, "api_request", method="PUT", path="/api/inference/api-keys/brave/",
                      body={"api_key": "x"})
    assert err
    _, err, text = _call(user, "api_request", method="GET", path="/v1/nope")
    assert err and "find_api" in text


def test_open_page_and_play_music_carry_client_actions(user):
    out, _, _ = _call(user, "open_page", page="music")
    assert out["client_action"] == {"type": "navigate", "path": "/dashboard/music"}
    assert out["url"] == "https://app.example/dashboard/music"
    _, err, _ = _call(user, "play_music", query="anything")
    assert err  # nothing playable yet


def test_make_song_with_supplied_lyrics_starts_jobs(user, settings):
    from test_async_jobs import _service_model

    settings.ASYNC_ENABLED = True
    _service_model(user, "music", "ace")
    _service_model(user, "image", "flux")
    with patch("apps.inference.jobs.kick_dispatch"):
        out, err, text = _call(
            user, "make_song", title="First Snow", style="folk, soft",
            lyrics="[verse]\nSnow falls", duration_seconds=150,
            image_prompts=["a snowy field", "a window at dusk"], images=2)
    assert not err, text
    jobs = InferenceRequest.objects.filter(user=user, status="QUEUED")
    assert jobs.filter(inference_type="MUSIC").count() == 1
    assert jobs.filter(inference_type="IMAGE").count() == 2
    song = jobs.get(inference_type="MUSIC")
    assert song.payload["audio_duration"] == 150
    assert song.payload["title"] == "First Snow"
    assert out["song_job_id"] == str(song.id) and len(out["image_job_ids"]) == 2
    assert Collection.objects.get(user=user, name="First Snow").items.count() == 3
    assert out["written_by"] is None  # no LLM was needed


def test_assistant_runs_the_shared_tools(user):
    """POST /v1/agent with skill "assistant": the model's tool call is carried
    out by the same handler the MCP server uses, and the reply lists what was
    done."""
    s = _song(user, "Rain")
    turns = iter([
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "c1", "type": "function",
            "function": {"name": "update_item",
                         "arguments": '{"id": %d, "visibility": "PUBLIC", "title": "None"}' % s.id}}]},
        {"role": "assistant", "content": "Your song is public now."},
    ])
    seen = {}

    def fake_turn(user_, model, convo, tools):
        seen["tools"] = [t["function"]["name"] for t in (tools or [])]
        seen["system"] = convo[0]["content"]
        msg = next(turns)
        if msg.get("content"):
            yield {"type": "token", "delta": msg["content"]}
        yield {"type": "_result", "message": msg, "usage": {}, "error": None}

    with patch.object(agent_loop, "_model_turn", fake_turn):
        r = _client(user).post("/v1/agent", {
            "skill": "assistant", "model": "any", "stream": False,
            "context": {"path": "/dashboard/music", "item": str(s.id)},
            "messages": [{"role": "user", "content": "make it public"}]}, format="json")
    assert r.status_code == 200, r.content
    body = r.json()
    s.refresh_from_db()
    assert s.visibility == "PUBLIC" and s.title == "Rain"  # "None" was dropped, not applied
    assert body["actions"] == ["Song “Rain”: made it public."]
    assert body["content"] == "Your song is public now."
    assert {"search_library", "make_song", "update_settings"} <= set(seen["tools"])
    assert "chat" not in seen["tools"]
    assert f"id {s.id}" in seen["system"]  # the open page's item is in the prompt


def test_assistant_cannot_confirm_its_own_delete(user):
    s = _song(user)
    call = lambda cid: {"id": cid, "type": "function", "function": {  # noqa: E731
        "name": "delete_item", "arguments": '{"id": %d, "confirm": true}' % s.id}}
    turns = iter([
        {"role": "assistant", "content": None, "tool_calls": [call("a")]},
        {"role": "assistant", "content": None, "tool_calls": [call("b")]},
        {"role": "assistant", "content": "Shall I delete it?"},
    ])

    def fake_turn(user_, model, convo, tools):
        yield {"type": "_result", "message": next(turns), "usage": {}, "error": None}

    with patch.object(agent_loop, "_model_turn", fake_turn):
        r = _client(user).post("/v1/agent", {
            "skill": "assistant", "model": "any", "stream": False,
            "messages": [{"role": "user", "content": "delete my song"}]}, format="json")
    assert r.status_code == 200
    assert InferenceRequest.objects.filter(id=s.id).exists()  # two calls, one turn: kept
