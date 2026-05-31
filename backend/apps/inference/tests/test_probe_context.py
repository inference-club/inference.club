"""Phase 1 — agent probing: the backend stores the probed max_model_len and
surfaces it ahead of the catalog's HF-derived context length."""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.inference.models import CatalogModel, Provider, ProviderModel
from apps.inference.openai_views import _model_caps
from apps.inference.views import _apply_context_lengths

User = get_user_model()


@pytest.fixture
def provider(db):
    user = User.objects.create_user(email="o@example.com", password="x")
    return Provider.objects.create(
        user=user, name="club-host", tailnet_hostname="h1",
        is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
    )


@pytest.mark.django_db
class TestApplyContextLengths:
    def test_stores_probed_max_model_len(self, provider):
        pm = ProviderModel.objects.create(provider=provider, name="m1", is_active=True)
        _apply_context_lengths(provider, {"m1": {"id": "m1", "max_model_len": 10000}})
        pm.refresh_from_db()
        assert pm.served_context_len == 10000

    def test_missing_field_leaves_it_unset(self, provider):
        pm = ProviderModel.objects.create(provider=provider, name="m1", is_active=True)
        _apply_context_lengths(provider, {"m1": {"id": "m1"}})  # no max_model_len
        pm.refresh_from_db()
        assert pm.served_context_len is None

    def test_ignores_nonpositive(self, provider):
        pm = ProviderModel.objects.create(provider=provider, name="m1", is_active=True)
        _apply_context_lengths(provider, {"m1": {"max_model_len": 0}})
        pm.refresh_from_db()
        assert pm.served_context_len is None


@pytest.mark.django_db
class TestContextPrecedence:
    def test_probe_beats_catalog_native(self, provider):
        cat = CatalogModel.objects.create(slug="m1", native_context_length=131072)
        pm = ProviderModel.objects.create(
            provider=provider, name="m1", catalog_model=cat,
            served_context_len=10000, is_active=True,
        )
        assert _model_caps(pm)["context_length"] == 10000

    def test_falls_back_to_catalog_native(self, provider):
        cat = CatalogModel.objects.create(slug="m1", native_context_length=131072)
        pm = ProviderModel.objects.create(
            provider=provider, name="m1", catalog_model=cat, is_active=True,
        )
        assert _model_caps(pm)["context_length"] == 131072

    def test_none_when_neither_known(self, provider):
        cat = CatalogModel.objects.create(slug="m1")
        pm = ProviderModel.objects.create(provider=provider, name="m1", catalog_model=cat, is_active=True)
        assert _model_caps(pm)["context_length"] is None
