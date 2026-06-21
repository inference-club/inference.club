"""Tests for the agent liveness beacon — POST /api/inference/agent/heartbeat/.

Phase 1 of the push-based liveness model: the agent calls this on an interval
over its existing outbound connection, so a healthy provider stays "online"
without the backend having to reach back into it. See AgentHeartbeatView.
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.inference.models import PROVIDER_LAST_SEEN_WINDOW, Provider

User = get_user_model()

HEARTBEAT = reverse("inference:agent-heartbeat")


@pytest.fixture
def user():
    return User.objects.create_user(email="op@example.com", password="x")


@pytest.fixture
def provider(user):
    # Registered a while ago and gone stale → currently offline.
    stale = timezone.now() - PROVIDER_LAST_SEEN_WINDOW - timedelta(seconds=60)
    return Provider.objects.create(
        user=user,
        name="club-host-k8s",
        tailnet_hostname="club-host-1",
        is_active=True,
        last_seen_at=stale,
    )


@pytest.fixture
def api_client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.mark.django_db
class TestAgentHeartbeat:
    def test_beacon_marks_provider_online(self, api_client, provider):
        assert provider.is_online is False  # stale to start

        resp = api_client.post(HEARTBEAT, {"name": "club-host-k8s"}, format="json")

        assert resp.status_code == 200
        assert resp.data["online"] is True
        assert resp.data["provider_id"] == provider.id
        provider.refresh_from_db()
        assert provider.is_online is True
        # stamped with server time, within the freshness window
        assert timezone.now() - provider.last_seen_at < PROVIDER_LAST_SEEN_WINDOW

    def test_defaults_to_club_host_when_name_omitted(self, api_client, user):
        p = Provider.objects.create(user=user, name="club-host", is_active=True)
        resp = api_client.post(HEARTBEAT, {}, format="json")
        assert resp.status_code == 200
        assert resp.data["provider_id"] == p.id

    def test_unknown_provider_name_404s(self, api_client, provider):
        resp = api_client.post(HEARTBEAT, {"name": "nope"}, format="json")
        assert resp.status_code == 404

    def test_only_bumps_own_provider(self, api_client, provider):
        """A user's beacon can't warm another user's provider of the same name."""
        other = User.objects.create_user(email="other@example.com", password="x")
        stale = timezone.now() - PROVIDER_LAST_SEEN_WINDOW - timedelta(seconds=60)
        theirs = Provider.objects.create(
            user=other, name="club-host-k8s", is_active=True, last_seen_at=stale
        )
        api_client.post(HEARTBEAT, {"name": "club-host-k8s"}, format="json")
        theirs.refresh_from_db()
        assert theirs.is_online is False  # untouched

    def test_requires_auth(self, provider):
        resp = APIClient().post(HEARTBEAT, {"name": "club-host-k8s"}, format="json")
        assert resp.status_code in (401, 403)
