"""``GET /v1/catalog`` (issue #17): every node, service and model the caller
can reach, built from the stored manifest + heartbeat liveness."""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.inference.manifest_validator import validate
from apps.inference.models import Provider, ServiceManifest
from apps.inference.views import sync_provider_models_from_manifest

User = get_user_model()

# A trimmed copy of what the in-cluster agent publishes for the home cluster:
# per-service model annotations (id/name/modalities/features/context_length)
# land in hosts[].services[].models[].
MANIFEST = {
    "schema_version": 1,
    "agent": {"name": "club-host"},
    "hosts": [
        {
            "id": "a1",
            "gpu": {"vendor": "nvidia", "model": "NVIDIA GeForce RTX 4090", "vram_gb": 24},
            "services": [
                {
                    "name": "flux3-klein-a1", "engine": "other", "type": "image",
                    "url": "http://flux3-klein-a1:8000/v1",
                    "models": [{
                        "id": "flux3-klein-fp8", "name": "FLUX 3 Klein (fp8)",
                        "input_modalities": ["text", "image"],
                        "output_modalities": ["image"],
                    }],
                },
                {
                    "name": "qwen3-asr", "engine": "vllm", "type": "stt",
                    "url": "http://qwen3-asr:8000/v1",
                    "features": ["timestamps"],
                    "models": [{"id": "qwen3-asr-1.7b", "name": "Qwen3 ASR 1.7B"}],
                },
            ],
        },
        {
            "id": "spark",
            "gpu": {"vendor": "nvidia", "model": "NVIDIA GB10", "vram_gb": 128},
            "services": [
                {
                    "name": "vllm-spark", "engine": "vllm",
                    "url": "http://vllm-spark:8000/v1",
                    "models": [{
                        "id": "nemotron-3-super", "name": "Nemotron 3 Super",
                        "features": ["reasoning", "tools"],
                        "context_length": 131072,
                    }],
                },
                {
                    "name": "acestep", "engine": "other", "type": "music",
                    "url": "http://acestep:8015/v1",
                    "models": [{
                        "id": "acestep-v15-turbo", "name": "ACE-Step v1.5 Turbo",
                        "input_modalities": ["text"], "output_modalities": ["audio"],
                    }],
                },
                {
                    # No explicit type (manifest default is llm): the declared
                    # text->audio modalities say it's really a TTS service.
                    "name": "dia", "engine": "other",
                    "url": "http://dia:8000/v1",
                    "models": [{
                        "id": "dia-1.6b", "name": "Dia 1.6B",
                        "input_modalities": ["text"], "output_modalities": ["audio"],
                    }],
                },
            ],
        },
    ],
}


@pytest.fixture
def owner(db):
    return User.objects.create_user(email="op@example.com", password="x")


@pytest.fixture
def provider(owner):
    assert validate(MANIFEST) == []
    p = Provider.objects.create(
        user=owner, name="club-host", tailnet_hostname="club-host-1",
        is_active=True, last_seen_at=timezone.now(),
    )
    ServiceManifest.objects.create(provider=p, raw_yaml="", parsed=MANIFEST)
    sync_provider_models_from_manifest(p, MANIFEST)
    return p


def _client(user):
    c = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token.key}")
    return c


def _get(client):
    r = client.get(reverse("openai:catalog"))
    assert r.status_code == 200, r.content
    return r.json()


@pytest.mark.django_db
class TestCatalog:
    def test_requires_auth(self, provider):
        assert APIClient().get(reverse("openai:catalog")).status_code == 401

    def test_owner_sees_full_catalog(self, owner, provider):
        body = _get(_client(owner))
        assert body["generated_at"]

        nodes = {n["name"]: n for n in body["nodes"]}
        assert set(nodes) == {"a1", "spark"}
        assert nodes["a1"]["gpus"] == [{"name": "NVIDIA GeForce RTX 4090", "memory_gb": 24.0}]
        assert nodes["spark"]["online"] is True
        assert nodes["spark"]["last_seen"]

        svcs = {s["name"]: s for s in body["services"]}
        assert {n: s["type"] for n, s in svcs.items()} == {
            "flux3-klein-a1": "image",
            "qwen3-asr": "asr",
            "vllm-spark": "llm",
            "acestep": "music",
            "dia": "tts",  # untyped; text->audio inferred
        }
        assert all(s["ready"] for s in svcs.values())
        assert svcs["flux3-klein-a1"]["node"] == "a1"
        assert svcs["flux3-klein-a1"]["endpoint_kind"] == "/v1/images/generations"
        # endpoint_kind follows the stored routing type, not the inferred one.
        assert svcs["dia"]["endpoint_kind"] == "/v1/chat/completions"
        llm = svcs["vllm-spark"]["models"][0]
        assert llm == {
            "id": "nemotron-3-super",
            "name": "Nemotron 3 Super",
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "features": ["reasoning", "tools"],
            "context_length": 131072,
        }
        assert svcs["qwen3-asr"]["models"][0]["features"] == ["timestamps"]
        assert "context_length" not in svcs["flux3-klein-a1"]["models"][0]

        assert body["by_type"] == {
            "asr": ["qwen3-asr-1.7b"],
            "image": ["flux3-klein-fp8"],
            "llm": ["nemotron-3-super"],
            "music": ["acestep-v15-turbo"],
            "tts": ["dia-1.6b"],
        }

    def test_offline_provider_is_not_ready(self, owner, provider):
        Provider.objects.filter(id=provider.id).update(
            last_seen_at=timezone.now() - timedelta(hours=1)
        )
        body = _get(_client(owner))
        assert not any(n["online"] for n in body["nodes"])
        assert not any(s["ready"] for s in body["services"])

    def test_cached_cluster_state_refines_readiness(self, owner, provider):
        cache.set(f"cluster_state:{provider.id}", {
            "nodes": [{"host_id": "a1", "ready": True}, {"host_id": "spark", "ready": False}],
            "deployments": [{"service": "flux3-klein-a1", "desired_replicas": 0,
                             "ready_replicas": 0}],
        })
        body = _get(_client(owner))
        svcs = {s["name"]: s["ready"] for s in body["services"]}
        assert svcs["flux3-klein-a1"] is False  # parked
        assert svcs["qwen3-asr"] is True        # not in snapshot: liveness only
        nodes = {n["name"]: n["online"] for n in body["nodes"]}
        assert nodes == {"a1": True, "spark": False}

    def test_other_member_sees_only_shared_services(self, provider):
        provider.services.filter(name="vllm-spark").update(access_policy="AUTHENTICATED")
        member = User.objects.create_user(email="m@example.com", password="x")
        body = _get(_client(member))
        assert [s["name"] for s in body["services"]] == ["vllm-spark"]
        assert [n["name"] for n in body["nodes"]] == ["spark"]
        assert body["by_type"] == {"llm": ["nemotron-3-super"]}
