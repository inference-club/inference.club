"""Per-user global routing preference: ANY / PREFER_OWN / ONLY_OWN affecting
which provider _find_provider_for_model picks when several serve the model."""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from social_django.models import UserSocialAuth

from apps.inference.models import Provider, ProviderModel, ProviderService
from apps.inference.openai_views import _find_provider_for_model

User = get_user_model()
MODEL = "shared-model"


@pytest.fixture
def alice(db):
    return User.objects.create_user(email="alice@example.com", password="x")


@pytest.fixture
def bob(db):
    u = User.objects.create_user(email="bob@example.com", password="x")
    UserSocialAuth.objects.create(
        user=u, provider="github", uid="7", extra_data={"login": "bob"}
    )
    return u


def _online_provider(user, hostname):
    return Provider.objects.create(
        user=user,
        name=f"node-{hostname}",
        tailnet_hostname=hostname,
        is_active=True,
        accepting_requests=True,
        last_seen_at=timezone.now(),
    )


@pytest.fixture
def alice_shared(alice):
    """Alice serves MODEL, shared to any authenticated member."""
    p = _online_provider(alice, "alice-1")
    svc = ProviderService.objects.create(
        provider=p, name="svc", access_policy=ProviderService.ACCESS_AUTHENTICATED
    )
    ProviderModel.objects.create(provider=p, name=MODEL, service=svc, is_active=True)
    return p


@pytest.fixture
def bob_own(bob):
    """Bob also serves MODEL on his own node."""
    p = _online_provider(bob, "bob-1")
    ProviderModel.objects.create(provider=p, name=MODEL, service=None, is_active=True)
    return p


@pytest.mark.django_db
class TestRoutingPreference:
    def test_any_routes_to_network_when_only_other_serves(self, bob, alice_shared):
        bob.routing_preference = User.ROUTING_ANY
        pm = _find_provider_for_model(bob, MODEL)
        assert pm is not None
        assert pm.provider.user_id != bob.id  # alice's node

    def test_only_own_blocks_when_user_has_no_node(self, bob, alice_shared):
        bob.routing_preference = User.ROUTING_ONLY_OWN
        assert _find_provider_for_model(bob, MODEL) is None

    def test_only_own_routes_to_own(self, bob, alice_shared, bob_own):
        bob.routing_preference = User.ROUTING_ONLY_OWN
        pm = _find_provider_for_model(bob, MODEL)
        assert pm is not None
        assert pm.provider.user_id == bob.id

    def test_prefer_own_uses_own_when_available(self, bob, alice_shared, bob_own):
        bob.routing_preference = User.ROUTING_PREFER_OWN
        pm = _find_provider_for_model(bob, MODEL)
        assert pm is not None
        assert pm.provider.user_id == bob.id

    def test_prefer_own_falls_back_to_network(self, bob, alice_shared):
        bob.routing_preference = User.ROUTING_PREFER_OWN
        pm = _find_provider_for_model(bob, MODEL)
        assert pm is not None
        assert pm.provider.user_id != bob.id


@pytest.mark.django_db
def test_account_patch_updates_routing_preference(bob):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=bob)
    resp = client.patch(
        "/api/account/", {"routing_preference": "ONLY_OWN"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["routing_preference"] == "ONLY_OWN"
    bob.refresh_from_db()
    assert bob.routing_preference == "ONLY_OWN"


@pytest.mark.django_db
def test_account_patch_rejects_invalid_preference(bob):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=bob)
    resp = client.patch(
        "/api/account/", {"routing_preference": "NONSENSE"}, format="json"
    )
    assert resp.status_code == 400
