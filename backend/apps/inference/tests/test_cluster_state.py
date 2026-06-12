"""Tests for the cluster endpoints (PRD 07).

``GET /api/inference/providers/<id>/cluster/`` forwards the agent's
``GET /cluster/state`` — but only for providers whose latest manifest is
kubernetes-derived (``discovery: kubernetes``), and with a short cache so
a polling viz page doesn't hammer the agent. ``.../cluster/activity/``
buckets served requests per service (V1 sparkline + pulses), and
``.../cluster/history/`` exposes manifest revisions (V3 story mode).
"""
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.inference.manifest_validator import validate as validate_manifest
from apps.inference.models import (
    InferenceRequest,
    ManifestRevision,
    Provider,
    ProviderModel,
    ProviderService,
    ServiceManifest,
)

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


def _activity_url(provider):
    return reverse(
        "inference:provider-cluster-activity", kwargs={"id": provider.id}
    )


def _make_request(owner, provider, model_name, minutes_ago=0):
    req = InferenceRequest.objects.create(
        user=owner,
        provider=provider,
        model_name=model_name,
        inference_type="TTS",
        payload={},
    )
    if minutes_ago:
        InferenceRequest.objects.filter(id=req.id).update(
            created_on=timezone.now() - timedelta(minutes=minutes_ago)
        )
    return req


@pytest.mark.django_db
class TestClusterActivity:
    @pytest.fixture
    def service(self, provider):
        svc = ProviderService.objects.create(
            provider=provider, name="magpie-tts", service_type="tts"
        )
        ProviderModel.objects.create(
            provider=provider, service=svc, name="magpie-tts-multilingual"
        )
        return svc

    def test_buckets_requests_by_service(self, owner, provider, service):
        _attach_manifest(provider, _k8s_manifest())
        _make_request(owner, provider, "magpie-tts-multilingual")
        _make_request(owner, provider, "magpie-tts-multilingual", minutes_ago=10)
        _make_request(owner, provider, "magpie-tts-multilingual", minutes_ago=120)
        _make_request(owner, provider, "model-nobody-declared")

        r = APIClient().get(_activity_url(provider))
        assert r.status_code == 200
        body = r.json()
        assert body["window_minutes"] == 60
        assert len(body["services"]) == 1
        entry = body["services"][0]
        assert entry["service"] == "magpie-tts"
        assert entry["total"] == 2  # the 2h-old one is outside the window
        assert sum(entry["buckets"]) == 2
        assert entry["buckets"][-1] == 1  # the just-now request, newest bucket
        assert entry["last_request_at"] is not None

    def test_gated_like_cluster_state(self, owner, provider, service):
        _attach_manifest(provider, _k8s_manifest(discovery=None))
        assert APIClient().get(_activity_url(provider)).status_code == 404


def _history_url(provider):
    return reverse("inference:provider-cluster-history", kwargs={"id": provider.id})


@pytest.mark.django_db
class TestClusterHistory:
    def _upload(self, owner, parsed):
        c = APIClient()
        c.force_authenticate(user=owner)
        return c.put(
            reverse("inference:agent-manifest"),
            {"raw_yaml": "", "parsed": parsed},
            format="json",
        )

    def _manifest_with_host(self):
        parsed = _k8s_manifest()
        parsed["hosts"] = [
            {
                "id": "a1",
                "services": [
                    {
                        "name": "magpie-tts",
                        "engine": "other",
                        "url": "http://magpie:9000/v1",
                    }
                ],
            }
        ]
        return parsed

    def test_upload_records_and_dedupes_revisions(self, owner, provider):
        first = _k8s_manifest()
        assert self._upload(owner, first).status_code == 200
        assert self._upload(owner, first).status_code == 200  # agent restart
        assert ManifestRevision.objects.filter(provider=provider).count() == 1

        assert self._upload(owner, self._manifest_with_host()).status_code == 200
        assert ManifestRevision.objects.filter(provider=provider).count() == 2

    def test_invalid_manifest_not_recorded(self, owner, provider):
        bad = _k8s_manifest()
        bad["schema_version"] = 99
        assert self._upload(owner, bad).status_code == 400
        assert ManifestRevision.objects.filter(provider=provider).count() == 0

    def test_history_index_and_revision_detail(self, owner, provider):
        self._upload(owner, _k8s_manifest())
        self._upload(owner, self._manifest_with_host())

        r = APIClient().get(_history_url(provider))
        assert r.status_code == 200
        revs = r.json()["revisions"]
        assert len(revs) == 2
        assert revs[0]["uploaded_at"] <= revs[1]["uploaded_at"]  # chronological
        assert (revs[0]["host_count"], revs[0]["service_count"]) == (0, 0)
        assert (revs[1]["host_count"], revs[1]["service_count"]) == (1, 1)

        detail = APIClient().get(f"{_history_url(provider)}{revs[1]['id']}/")
        assert detail.status_code == 200
        assert detail.json()["parsed"]["hosts"][0]["id"] == "a1"

    def test_revision_of_other_provider_404(self, owner, provider):
        other_user = User.objects.create_user(email="x@example.com", password="x")
        other = Provider.objects.create(
            user=other_user, name="other", tailnet_hostname="other-1", is_active=True
        )
        _attach_manifest(other, _k8s_manifest())
        rev = ManifestRevision.record(other, _k8s_manifest())

        _attach_manifest(provider, _k8s_manifest())
        url = reverse(
            "inference:provider-cluster-revision",
            kwargs={"id": provider.id, "rev_id": rev.id},
        )
        assert APIClient().get(url).status_code == 404
