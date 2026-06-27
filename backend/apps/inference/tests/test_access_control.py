"""Tests for per-service access control: the grants_access_to policy logic and
the access-aware routing in _find_provider_for_model, plus a couple of
API-level auth/guardrail checks."""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from social_django.models import UserSocialAuth

from apps.inference.models import Host, Provider, ProviderModel, ProviderService
from apps.inference.openai_views import _find_provider_for_model

User = get_user_model()
MODEL = "m1"


@pytest.fixture
def owner(db):
    return User.objects.create_user(email="owner@example.com", password="x")


@pytest.fixture
def consumer(db):
    u = User.objects.create_user(email="consumer@example.com", password="x")
    UserSocialAuth.objects.create(
        user=u, provider="github", uid="42", extra_data={"login": "bob"}
    )
    return u


@pytest.fixture
def provider(owner):
    return Provider.objects.create(
        user=owner,
        name="club-host",
        tailnet_hostname="club-host-1",
        is_active=True,
        accepting_requests=True,
        last_seen_at=timezone.now(),  # online
    )


@pytest.fixture
def service(provider):
    svc = ProviderService.objects.create(
        provider=provider,
        name="vllm-main",
        access_policy=ProviderService.ACCESS_PRIVATE,
    )
    ProviderModel.objects.create(provider=provider, name=MODEL, service=svc, is_active=True)
    return svc


@pytest.mark.django_db
class TestGrantsAccessTo:
    def test_owner_always(self, service, owner):
        service.access_policy = ProviderService.ACCESS_PRIVATE
        assert service.grants_access_to(owner, None) is True

    def test_private_blocks_others(self, service, consumer):
        service.access_policy = ProviderService.ACCESS_PRIVATE
        assert service.grants_access_to(consumer, "bob") is False

    def test_authenticated_allows_any(self, service, consumer):
        service.access_policy = ProviderService.ACCESS_AUTHENTICATED
        assert service.grants_access_to(consumer, "bob") is True

    def test_restricted_allowlist(self, service, consumer):
        service.access_policy = ProviderService.ACCESS_RESTRICTED
        service.allowed_github_users = ["bob"]
        assert service.grants_access_to(consumer, "bob") is True
        service.allowed_github_users = ["alice"]
        assert service.grants_access_to(consumer, "bob") is False

    def test_restricted_is_case_insensitive(self, service, consumer):
        service.access_policy = ProviderService.ACCESS_RESTRICTED
        service.allowed_github_users = ["BOB"]
        assert service.grants_access_to(consumer, "bob") is True


@pytest.mark.django_db
class TestMachineGate:
    """Machine-level (Provider) gating combines with the service policy: a
    non-owner must clear BOTH. Provider defaults to AUTHENTICATED so the
    service policy stays the effective gate until the machine is tightened."""

    def test_provider_grants_access_to_owner_always(self, provider, owner):
        provider.access_policy = Provider.ACCESS_PRIVATE
        assert provider.grants_access_to(owner, None) is True

    def test_default_provider_defers_to_service(self, service, consumer):
        # Provider AUTHENTICATED (default) + service AUTHENTICATED → allowed.
        assert service.provider.access_policy == Provider.ACCESS_AUTHENTICATED
        service.access_policy = ProviderService.ACCESS_AUTHENTICATED
        assert service.grants_access_to(consumer, "bob") is True

    def test_private_machine_blocks_even_open_service(self, service, consumer):
        service.provider.access_policy = Provider.ACCESS_PRIVATE
        service.access_policy = ProviderService.ACCESS_AUTHENTICATED
        assert service.grants_access_to(consumer, "bob") is False

    def test_private_machine_still_allows_owner(self, service, owner):
        service.provider.access_policy = Provider.ACCESS_PRIVATE
        service.access_policy = ProviderService.ACCESS_PRIVATE
        assert service.grants_access_to(owner, None) is True

    def test_restricted_machine_allowlist_gates_open_service(self, service, consumer):
        service.provider.access_policy = Provider.ACCESS_RESTRICTED
        service.provider.allowed_github_users = ["bob"]
        service.access_policy = ProviderService.ACCESS_AUTHENTICATED
        assert service.grants_access_to(consumer, "bob") is True
        service.provider.allowed_github_users = ["alice"]
        assert service.grants_access_to(consumer, "bob") is False

    def test_open_machine_restricted_service(self, service, consumer):
        # Machine allows everyone, but the service narrows to an allowlist.
        service.provider.access_policy = Provider.ACCESS_AUTHENTICATED
        service.access_policy = ProviderService.ACCESS_RESTRICTED
        service.allowed_github_users = ["alice"]
        assert service.grants_access_to(consumer, "bob") is False


@pytest.fixture
def hosted_service(provider):
    """A service pinned to a physical node (Host) — exercises the node gate."""
    host = Host.objects.create(provider=provider, host_id="spark", hostname="spark-d2ce")
    svc = ProviderService.objects.create(
        provider=provider,
        name="acestep",
        host=host,
        manifest_host_id="spark",
        access_policy=ProviderService.ACCESS_AUTHENTICATED,
    )
    ProviderModel.objects.create(provider=provider, name="m2", service=svc, is_active=True)
    return svc


@pytest.mark.django_db
class TestNodeGate:
    """Node-level (Host) gating is a third gate between cluster and service: a
    non-owner must clear it too. Defaults to AUTHENTICATED."""

    def test_default_node_defers_to_service(self, hosted_service, consumer):
        assert hosted_service.host.access_policy == Host.ACCESS_AUTHENTICATED
        assert hosted_service.grants_access_to(consumer, "bob") is True

    def test_private_node_blocks_even_open_service(self, hosted_service, consumer):
        hosted_service.host.access_policy = Host.ACCESS_PRIVATE
        hosted_service.access_policy = ProviderService.ACCESS_AUTHENTICATED
        assert hosted_service.grants_access_to(consumer, "bob") is False

    def test_private_node_still_allows_owner(self, hosted_service, owner):
        hosted_service.host.access_policy = Host.ACCESS_PRIVATE
        assert hosted_service.grants_access_to(owner, None) is True

    def test_restricted_node_allowlist(self, hosted_service, consumer):
        hosted_service.host.access_policy = Host.ACCESS_RESTRICTED
        hosted_service.host.allowed_github_users = ["bob"]
        assert hosted_service.grants_access_to(consumer, "bob") is True
        hosted_service.host.allowed_github_users = ["alice"]
        assert hosted_service.grants_access_to(consumer, "bob") is False

    def test_service_without_host_skips_node_gate(self, service, consumer):
        # `service` has no linked host → node gate is a no-op, service decides.
        assert service.host_id is None
        service.access_policy = ProviderService.ACCESS_AUTHENTICATED
        assert service.grants_access_to(consumer, "bob") is True


@pytest.mark.django_db
class TestRouting:
    def test_owner_can_route_even_when_private(self, service, owner):
        service.access_policy = ProviderService.ACCESS_PRIVATE
        service.save()
        assert _find_provider_for_model(owner, MODEL) is not None

    def test_consumer_blocked_when_private(self, service, consumer):
        service.access_policy = ProviderService.ACCESS_PRIVATE
        service.save()
        assert _find_provider_for_model(consumer, MODEL) is None

    def test_consumer_allowed_when_authenticated(self, service, consumer):
        service.access_policy = ProviderService.ACCESS_AUTHENTICATED
        service.save()
        assert _find_provider_for_model(consumer, MODEL) is not None

    def test_consumer_restricted_allowlist(self, service, consumer):
        service.access_policy = ProviderService.ACCESS_RESTRICTED
        service.allowed_github_users = ["bob"]
        service.save()
        assert _find_provider_for_model(consumer, MODEL) is not None
        service.allowed_github_users = ["someone-else"]
        service.save()
        assert _find_provider_for_model(consumer, MODEL) is None

    def test_paused_provider_excluded_even_for_owner(self, service, provider, owner):
        service.access_policy = ProviderService.ACCESS_AUTHENTICATED
        service.save()
        provider.accepting_requests = False
        provider.save()
        assert _find_provider_for_model(owner, MODEL) is None

    def test_unmapped_model_is_owner_only(self, provider, owner, consumer):
        # A model with no service (e.g. discovered live) stays owner-only.
        ProviderModel.objects.create(provider=provider, name="m2", service=None, is_active=True)
        assert _find_provider_for_model(owner, "m2") is not None
        assert _find_provider_for_model(consumer, "m2") is None


@pytest.mark.django_db
class TestApiGuards:
    def test_models_unauthenticated_returns_401(self):
        resp = APIClient().get("/v1/models")
        assert resp.status_code == 401

    def test_oversized_request_returns_413(self, settings, owner):
        settings.INFERENCE_MAX_INPUT_CHARS = 10
        client = APIClient()
        client.force_authenticate(user=owner)
        resp = client.post(
            "/v1/chat/completions",
            {"model": MODEL, "messages": [{"role": "user", "content": "way too long to allow"}]},
            format="json",
        )
        assert resp.status_code == 413
