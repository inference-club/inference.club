"""External LLM providers — OpenRouter / NVIDIA / Groq (PRD 19).

Covers the namespaced-id resolver, the chat proxy's external routing, /v1/models
injection of pinned models, and the browse/pin API. Upstream HTTP is mocked.
"""
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.inference.external_keys import set_user_api_key
from apps.inference.external_providers import (
    resolve_external_target,
    split_external_model,
)
from apps.inference.models import InferenceRequest, PinnedModel

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    return User.objects.create_user(email="u@ex.com", password="x")


def _client(u):
    c = APIClient()
    c.force_authenticate(u)
    return c


def _fake_resp(json_body, ok=True, status_code=200):
    m = MagicMock()
    m.ok = ok
    m.status_code = status_code
    m.headers = {"content-type": "application/json"}
    m.json.return_value = json_body
    m.raise_for_status.return_value = None
    return m


# --- resolver ---------------------------------------------------------------


def test_split_external_model():
    assert split_external_model("groq:llama-3.3-70b") == ("groq", "llama-3.3-70b")
    assert split_external_model("openrouter:anthropic/claude-3.7") == (
        "openrouter", "anthropic/claude-3.7",
    )
    assert split_external_model("llama-3.3") is None      # no prefix
    assert split_external_model("unknown:foo") is None     # not an llm provider
    assert split_external_model("groq:") is None           # empty upstream


def test_resolve_requires_a_key(user):
    assert resolve_external_target(user, "groq:llama-3.3") is None
    set_user_api_key(user, "groq", "gsk_test")
    t = resolve_external_target(user, "groq:llama-3.3")
    assert t.slug == "groq" and t.upstream_model == "llama-3.3"
    assert t.base_url == "https://api.groq.com/openai/v1"
    assert t.headers["Authorization"] == "Bearer gsk_test"


# --- chat proxy routes to the external cloud --------------------------------


def test_chat_routes_to_external_provider(user):
    set_user_api_key(user, "groq", "gsk_test")
    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["kw"] = kw
        return _fake_resp(
            {
                "choices": [{"message": {"content": "hi"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        )

    with patch("apps.inference.openai_views.requests.post", side_effect=fake_post):
        resp = _client(user).post(
            "/v1/chat/completions",
            {"model": "groq:llama-3.3-70b", "messages": [{"role": "user", "content": "hi"}]},
            format="json",
        )

    assert resp.status_code == 200
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["kw"]["headers"]["Authorization"] == "Bearer gsk_test"
    assert captured["kw"]["verify"] is True
    assert captured["kw"]["proxies"] is None
    # forwarded with the upstream id (namespace prefix stripped)
    assert captured["kw"]["json"]["model"] == "llama-3.3-70b"

    ir = InferenceRequest.objects.get(user=user)
    assert ir.model_name == "groq:llama-3.3-70b"   # stored namespaced
    assert ir.provider_id is None
    assert ir.dispatch_meta["external_provider"] == "groq"


def test_chat_external_model_without_key_is_a_clear_error(user):
    resp = _client(user).post(
        "/v1/chat/completions",
        {"model": "openrouter:foo/bar", "messages": [{"role": "user", "content": "hi"}]},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["type"] == "missing_api_key"
    assert not InferenceRequest.objects.exists()


# --- /v1/models injection ---------------------------------------------------


def test_models_lists_pinned_only_when_keyed(user):
    PinnedModel.objects.create(
        user=user, provider="groq", model_id="llama-3.3-70b",
        display_name="Llama 3.3 70B", context_length=8192, input_modalities=["text"],
    )
    c = _client(user)
    # no key → not usable → not listed
    ids = [m["id"] for m in c.get("/v1/models").json()["data"]]
    assert "groq:llama-3.3-70b" not in ids
    # key set → listed, badged external
    set_user_api_key(user, "groq", "gsk_test")
    entry = next(
        m for m in c.get("/v1/models").json()["data"] if m["id"] == "groq:llama-3.3-70b"
    )
    assert entry["external"] is True
    assert entry["provider"] == "groq"
    assert entry["service_type"] == "llm"
    assert entry["context_length"] == 8192


# --- browse + pin API -------------------------------------------------------


def test_browse_catalog_marks_pinned(user):
    set_user_api_key(user, "groq", "gsk_test")
    PinnedModel.objects.create(user=user, provider="groq", model_id="pinned-model")
    fake = _fake_resp({"data": [{"id": "llama-3.3-70b", "context_window": 8192}, {"id": "pinned-model"}]})
    with patch("apps.inference.external_providers.requests.get", return_value=fake):
        r = _client(user).get("/api/inference/providers/groq/models")
    assert r.status_code == 200
    by_id = {m["model_id"]: m for m in r.json()["data"]}
    assert by_id["pinned-model"]["pinned"] is True
    assert by_id["llama-3.3-70b"]["pinned"] is False
    assert by_id["llama-3.3-70b"]["context_length"] == 8192


def test_browse_requires_key(user):
    r = _client(user).get("/api/inference/providers/groq/models")
    assert r.status_code == 400
    assert r.json().get("type") == "missing_api_key"


def test_pin_and_unpin(user):
    c = _client(user)
    r = c.post(
        "/api/inference/providers/groq/pins",
        {"model_id": "llama-3.3-70b", "display_name": "L", "context_length": 8192},
        format="json",
    )
    assert r.status_code == 201
    assert PinnedModel.objects.filter(user=user, provider="groq", model_id="llama-3.3-70b").exists()
    # idempotent
    assert c.post("/api/inference/providers/groq/pins", {"model_id": "llama-3.3-70b"}, format="json").status_code == 201
    assert PinnedModel.objects.filter(user=user).count() == 1
    # unpin
    assert c.delete("/api/inference/providers/groq/pins", {"model_id": "llama-3.3-70b"}, format="json").status_code == 204
    assert not PinnedModel.objects.filter(user=user).exists()


def test_pin_unknown_provider_404(user):
    assert _client(user).post(
        "/api/inference/providers/notaprovider/pins", {"model_id": "x"}, format="json"
    ).status_code == 404
