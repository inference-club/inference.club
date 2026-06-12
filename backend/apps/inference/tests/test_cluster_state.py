"""Tests for the live cluster-state proxy (PRD 07).

``GET /api/inference/providers/<id>/cluster/`` forwards the agent's
``GET /cluster/state`` — but only for providers whose latest manifest is
kubernetes-derived (``discovery: kubernetes``), and with a short cache so
a polling viz page doesn't hammer the agent.
"""
from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.inference.manifest_validator import validate as validate_manifest
from apps.inference.models import Provider, ServiceManifest

User = get_user_model()

STATE = {
    "discovery": "kubernetes",
    "metrics_available": True,
    "nodes": [{"name": "a1", "host_id": "a1", "ready": True}],
    "pods": [{"name": "magpie-tts-abc", "service": "magpie-tts", "phase": "Running"}],
}


def _k8s_manifest(discovery="kubernetes"):
    parsed = {
        "schema_version": 1,
        "agent": {"name": "club-host"},
        "hosts": [],
    }
    if discovery is not None:
        parsed["discovery"] = discovery
    return parsed


@pytest.fixture
def owner():
    return User.objects.create_user(email="op@example.com", password="x")


@pytest.fixture
def provider(owner):
    return Provider.objects.create(
        user=owner,
        name="club-host",
        tailnet_hostname="club-host-1",
        agent_port=443,
        is_active=True,
    )


def _attach_manifest(provider, parsed, is_valid=True):
    return ServiceManifest.objects.create(
        provider=provider, raw_yaml="", parsed=parsed, is_valid=is_valid
    )


def _url(provider):
    return reverse("inference:provider-cluster-state", kwargs={"id": provider.id})


def _ok_upstream():
    resp = MagicMock()
    resp.json.return_value = STATE
    resp.raise_for_status.return_value = None
    return resp


class TestDiscoveryValidation:
    def test_kubernetes_and_static_accepted(self):
        assert validate_manifest(_k8s_manifest("kubernetes")) == []
        assert validate_manifest(_k8s_manifest("static")) == []
        assert validate_manifest(_k8s_manifest(None)) == []

    def test_unknown_discovery_rejected(self):
        errs = validate_manifest(_k8s_manifest("psychic"))
        assert any("discovery" in e for e in errs)


@pytest.mark.django_db
class TestClusterStateProxy:
    def test_proxies_agent_state(self, provider):
        _attach_manifest(provider, _k8s_manifest())
        with patch("apps.inference.views.requests.get", return_value=_ok_upstream()) as get:
            r = APIClient().get(_url(provider))
        assert r.status_code == 200
        assert r.json() == STATE
        assert get.call_args.args[0] == "http://club-host-1:443/cluster/state"

    def test_second_call_within_ttl_is_cached(self, provider):
        _attach_manifest(provider, _k8s_manifest())
        with patch("apps.inference.views.requests.get", return_value=_ok_upstream()) as get:
            APIClient().get(_url(provider))
            r = APIClient().get(_url(provider))
        assert r.status_code == 200
        assert get.call_count == 1

    def test_404_without_kubernetes_manifest(self, provider):
        _attach_manifest(provider, _k8s_manifest(discovery=None))
        assert APIClient().get(_url(provider)).status_code == 404

    def test_404_with_invalid_manifest(self, provider):
        _attach_manifest(provider, _k8s_manifest(), is_valid=False)
        assert APIClient().get(_url(provider)).status_code == 404

    def test_404_with_no_manifest(self, provider):
        assert APIClient().get(_url(provider)).status_code == 404

    def test_502_when_agent_unreachable(self, provider):
        _attach_manifest(provider, _k8s_manifest())
        with patch(
            "apps.inference.views.requests.get",
            side_effect=requests_lib.ConnectionError("down"),
        ):
            assert APIClient().get(_url(provider)).status_code == 502

    def test_private_profile_hidden_from_public_but_not_owner(self, owner, provider):
        owner.public_profile_enabled = False
        owner.save(update_fields=["public_profile_enabled"])
        _attach_manifest(provider, _k8s_manifest())

        assert APIClient().get(_url(provider)).status_code == 404

        c = APIClient()
        c.force_authenticate(user=owner)
        with patch("apps.inference.views.requests.get", return_value=_ok_upstream()):
            assert c.get(_url(provider)).status_code == 200
