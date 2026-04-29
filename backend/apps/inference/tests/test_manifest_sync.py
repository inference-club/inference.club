"""Tests for manifest-driven ProviderModel sync.

Covers the bug where the dashboard's Registered Compute panel and the
``/v1/models`` proxy only saw a subset of the models declared in the
operator's manifest, because both read paths trusted the agent's live
``/v1/models`` over the operator's declared YAML.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.inference.models import Provider, ProviderModel, ServiceManifest
from apps.inference.views import (
    RefreshError,
    refresh_provider_models,
    sync_provider_models_from_manifest,
)

User = get_user_model()


def _manifest(*model_ids):
    """Build a parsed manifest declaring the given model ids on one host/service."""
    return {
        "schema_version": 1,
        "agent": {"name": "club-host"},
        "hosts": [
            {
                "id": "rig-01",
                "services": [
                    {
                        "name": "vllm-main",
                        "engine": "vllm",
                        "url": "http://localhost:8000/v1",
                        "models": [{"id": mid} for mid in model_ids],
                    }
                ],
            }
        ],
    }


@pytest.fixture
def user():
    return User.objects.create_user(email="op@example.com", password="x")


@pytest.fixture
def provider(user):
    return Provider.objects.create(
        user=user,
        name="club-host",
        tailnet_hostname="club-host-1",
        is_active=True,
    )


@pytest.fixture
def api_client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.mark.django_db
class TestSyncFromManifest:
    def test_creates_rows_for_all_declared_models(self, provider):
        n = sync_provider_models_from_manifest(
            provider, _manifest("qwen3-27b", "nemotron-3-nano")
        )
        assert n == 2
        names = set(provider.models.values_list("name", flat=True))
        assert names == {"qwen3-27b", "nemotron-3-nano"}
        assert all(provider.models.values_list("is_active", flat=True))

    def test_reactivates_previously_deactivated_model(self, provider):
        ProviderModel.objects.create(
            provider=provider, name="nemotron-3-nano", is_active=False
        )
        sync_provider_models_from_manifest(
            provider, _manifest("qwen3-27b", "nemotron-3-nano")
        )
        nemo = provider.models.get(name="nemotron-3-nano")
        assert nemo.is_active is True

    def test_deactivates_models_no_longer_in_manifest(self, provider):
        ProviderModel.objects.create(provider=provider, name="old-model", is_active=True)
        sync_provider_models_from_manifest(provider, _manifest("qwen3-27b"))
        old = provider.models.get(name="old-model")
        assert old.is_active is False
        assert provider.models.get(name="qwen3-27b").is_active is True

    def test_handles_manifest_with_no_services(self, provider):
        n = sync_provider_models_from_manifest(provider, {"hosts": []})
        assert n == 0
        assert provider.models.count() == 0


@pytest.mark.django_db
class TestManifestUploadSync:
    def test_upload_mirrors_models_into_provider_model_rows(self, provider, api_client):
        url = reverse("inference:agent-manifest")
        resp = api_client.put(
            url,
            {
                "raw_yaml": "schema_version: 1\nagent: {name: club-host}\n",
                "parsed": _manifest("qwen3-27b", "nemotron-3-nano"),
            },
            format="json",
        )
        assert resp.status_code == 200, resp.data
        names = set(provider.models.values_list("name", flat=True))
        assert names == {"qwen3-27b", "nemotron-3-nano"}

    def test_invalid_manifest_does_not_wipe_existing_rows(self, provider, api_client):
        ProviderModel.objects.create(provider=provider, name="qwen3-27b")
        ProviderModel.objects.create(provider=provider, name="nemotron-3-nano")

        # Missing engine ⇒ validation error.
        bad = _manifest("qwen3-27b")
        bad["hosts"][0]["services"][0].pop("engine")

        url = reverse("inference:agent-manifest")
        resp = api_client.put(
            url,
            {"raw_yaml": "broken", "parsed": bad},
            format="json",
        )
        assert resp.status_code == 400
        # Both rows stay active because the sync was skipped.
        assert provider.models.filter(is_active=True).count() == 2


@pytest.mark.django_db
class TestRefreshDoesNotDropManifestModels:
    def _make_manifest(self, provider, *model_ids):
        return ServiceManifest.objects.create(
            provider=provider,
            schema_version=1,
            raw_yaml="",
            parsed=_manifest(*model_ids),
            is_valid=True,
        )

    def test_agent_subset_does_not_deactivate_manifest_model(self, provider):
        self._make_manifest(provider, "qwen3-27b", "nemotron-3-nano")
        ProviderModel.objects.create(provider=provider, name="qwen3-27b")
        ProviderModel.objects.create(provider=provider, name="nemotron-3-nano")

        # Agent only reports one of the two declared models — typical when
        # vLLM has just one currently loaded.
        fake = type(
            "Resp",
            (),
            {"ok": True, "json": staticmethod(lambda: {"data": [{"id": "qwen3-27b"}]})},
        )()
        with patch("apps.inference.views.requests.get", return_value=fake):
            refresh_provider_models(provider)

        active = set(
            provider.models.filter(is_active=True).values_list("name", flat=True)
        )
        assert active == {"qwen3-27b", "nemotron-3-nano"}

    def test_refresh_view_resyncs_manifest_when_agent_offline(self, provider, api_client):
        self._make_manifest(provider, "qwen3-27b", "nemotron-3-nano")
        # Stale row from a previous sync — only one model active.
        ProviderModel.objects.create(provider=provider, name="qwen3-27b")

        url = reverse("inference:provider-refresh-models", args=[provider.id])
        with patch(
            "apps.inference.views.refresh_provider_models",
            side_effect=RefreshError("agent unreachable"),
        ):
            resp = api_client.post(url)

        assert resp.status_code == 200
        assert resp.data["error"] == "agent unreachable"
        names = set(
            provider.models.filter(is_active=True).values_list("name", flat=True)
        )
        # Manifest sync ran even though the agent call failed.
        assert names == {"qwen3-27b", "nemotron-3-nano"}
