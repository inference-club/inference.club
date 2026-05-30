"""The public, unauthenticated network status endpoint."""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.inference.models import (
    CatalogModel,
    InferenceRequest,
    Provider,
    ProviderModel,
)

User = get_user_model()


@pytest.mark.django_db
class TestNetworkStatus:
    def test_public_aggregates(self):
        user = User.objects.create_user(email="u@example.com", password="x")
        online = Provider.objects.create(
            user=user, name="club-host", tailnet_hostname="h1",
            is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
        )
        # An offline (stale) provider must not count as online.
        Provider.objects.create(
            user=user, name="old", tailnet_hostname="h2",
            is_active=True, last_seen_at=timezone.now() - timezone.timedelta(hours=1),
        )
        cat = CatalogModel.objects.create(slug="org/model", display_name="Model")
        ProviderModel.objects.create(provider=online, name="org/model", catalog_model=cat, is_active=True)
        InferenceRequest.objects.create(
            user=user, provider=online, inference_type="LLM", payload={},
            status="PROCESSED", total_tokens=100,
        )

        resp = APIClient().get("/api/inference/network/")  # no auth
        assert resp.status_code == 200
        d = resp.data
        assert d["providers"]["online"] == 1
        assert d["providers"]["total"] == 2
        assert d["models_available"] == 1
        assert d["tokens"]["total"] == 100
        assert d["requests"]["total"] == 1
        assert len(d["daily_tokens"]) == 30
        assert any(n["name"] == "club-host" for n in d["nodes"])
        assert any(m["slug"] == "org/model" for m in d["models"])

    def test_empty_network_ok(self):
        resp = APIClient().get("/api/inference/network/")
        assert resp.status_code == 200
        assert resp.data["providers"]["online"] == 0
        assert resp.data["tokens"]["total"] == 0
