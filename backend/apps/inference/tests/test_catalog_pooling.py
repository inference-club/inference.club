"""Phase 0 — model identity & pooling: HF-id slugs, CatalogModel linking,
`hf:` manifest parsing, cross-provider pooling in /v1/models, and slug-based
routing that preserves each deployment's real served name."""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.inference.models import (
    CatalogModel,
    Provider,
    ProviderModel,
    ProviderService,
    link_catalog_model,
    slugify_model_id,
)
from apps.inference.openai_views import _find_provider_for_model, _model_slug
from apps.inference.views import sync_provider_models_from_manifest

User = get_user_model()


@pytest.fixture
def owner(db):
    return User.objects.create_user(email="owner@example.com", password="x")


def _online_provider(owner, name="node", host="node-1"):
    return Provider.objects.create(
        user=owner,
        name=name,
        tailnet_hostname=host,
        is_active=True,
        accepting_requests=True,
        last_seen_at=timezone.now(),
    )


class TestSlugify:
    def test_lowercases_and_strips(self):
        assert slugify_model_id("  Qwen/Qwen3-30B-A3B ") == "qwen/qwen3-30b-a3b"
        assert slugify_model_id("") == ""
        assert slugify_model_id(None) == ""


@pytest.mark.django_db
class TestLinkCatalog:
    def test_slug_from_hf_id(self, owner):
        p = _online_provider(owner)
        pm = ProviderModel(provider=p, name="Qwen/Qwen3-30B-A3B", hf_repo_id="Qwen/Qwen3-30B-A3B")
        link_catalog_model(pm)
        pm.save()
        assert pm.catalog_model.slug == "qwen/qwen3-30b-a3b"
        assert pm.catalog_model.is_custom is False

    def test_slug_from_served_name_when_no_hf(self, owner):
        p = _online_provider(owner)
        pm = ProviderModel(provider=p, name="My-Local-FT")
        link_catalog_model(pm)
        pm.save()
        assert pm.catalog_model.slug == "my-local-ft"
        assert pm.catalog_model.is_custom is True

    def test_custom_entry_upgraded_when_hf_learned(self, owner):
        # A custom catalog row exists (slug derived from a served name)…
        CatalogModel.objects.create(slug="org/model", is_custom=True)
        p = _online_provider(owner)
        # …and a later deployment declares the HF id that maps to the same slug.
        pm = ProviderModel(provider=p, name="whatever", hf_repo_id="Org/Model")
        link_catalog_model(pm)
        pm.save()
        cat = pm.catalog_model
        assert cat.slug == "org/model"
        assert cat.is_custom is False
        assert cat.hf_repo_id == "Org/Model"

    def test_two_deployments_share_one_catalog(self, owner):
        p1 = _online_provider(owner, "n1", "n1-host")
        p2 = _online_provider(owner, "n2", "n2-host")
        # Same model, different served-name casing across providers.
        for prov, served in ((p1, "Org/Model"), (p2, "org/model")):
            pm = ProviderModel(provider=prov, name=served, hf_repo_id="Org/Model")
            link_catalog_model(pm)
            pm.save()
        assert CatalogModel.objects.filter(slug="org/model").count() == 1
        assert ProviderModel.objects.filter(catalog_model__slug="org/model").count() == 2


@pytest.mark.django_db
class TestManifestHf:
    def _manifest(self, model_entry):
        return {
            "schema_version": 1,
            "hosts": [
                {
                    "id": "h1",
                    "services": [
                        {
                            "name": "vllm-main",
                            "engine": "vllm",
                            "url": "http://x/v1",
                            "models": [model_entry],
                        }
                    ],
                }
            ],
        }

    def test_hf_entry_sets_identity_and_slug(self, owner):
        p = _online_provider(owner)
        sync_provider_models_from_manifest(p, self._manifest({"hf": "Qwen/Qwen3-30B-A3B"}))
        pm = p.models.get(name="Qwen/Qwen3-30B-A3B")  # served defaults to the HF id
        assert pm.hf_repo_id == "Qwen/Qwen3-30B-A3B"
        assert pm.catalog_model.slug == "qwen/qwen3-30b-a3b"

    def test_id_override_keeps_hf_for_slug(self, owner):
        p = _online_provider(owner)
        sync_provider_models_from_manifest(
            p, self._manifest({"id": "q3", "hf": "Qwen/Qwen3-30B-A3B"})
        )
        pm = p.models.get(name="q3")  # served name is the explicit id
        assert pm.hf_repo_id == "Qwen/Qwen3-30B-A3B"
        # …but the public slug still comes from the HF id, so it pools.
        assert pm.catalog_model.slug == "qwen/qwen3-30b-a3b"

    def test_bare_id_still_works(self, owner):
        p = _online_provider(owner)
        sync_provider_models_from_manifest(p, self._manifest({"id": "legacy-model"}))
        pm = p.models.get(name="legacy-model")
        assert pm.hf_repo_id == ""
        assert pm.catalog_model.slug == "legacy-model"


@pytest.mark.django_db
class TestModelsPooling:
    def test_v1_models_pools_by_slug(self, owner):
        p1 = _online_provider(owner, "n1", "n1-host")
        p2 = _online_provider(owner, "n2", "n2-host")
        for prov, served in ((p1, "Org/Model"), (p2, "org/model")):
            pm = ProviderModel(provider=prov, name=served, hf_repo_id="Org/Model", is_active=True)
            link_catalog_model(pm)
            pm.save()

        client = APIClient()
        client.force_authenticate(user=owner)
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        ids = [m["id"] for m in resp.data["data"]]
        assert ids.count("org/model") == 1  # two deployments → one catalog entry
        assert ids == ["org/model"]


@pytest.mark.django_db
class TestRoutingBySlug:
    def test_routes_by_slug_and_preserves_served_name(self, owner):
        p = _online_provider(owner)
        svc = ProviderService.objects.create(
            provider=p, name="vllm", access_policy=ProviderService.ACCESS_PRIVATE
        )
        pm = ProviderModel(
            provider=p, name="Org/Model-FP8", hf_repo_id="Org/Model-FP8",
            service=svc, is_active=True,
        )
        link_catalog_model(pm)
        pm.save()

        # Caller addresses the public (lowercased) slug…
        found = _find_provider_for_model(owner, "org/model-fp8")
        assert found is not None
        # …but routing yields the deployment with its exact served name, which
        # is what the proxy forwards upstream.
        assert found.name == "Org/Model-FP8"
        assert _model_slug(found) == "org/model-fp8"

        # Calling by the exact served name resolves to the same deployment.
        assert _find_provider_for_model(owner, "Org/Model-FP8").id == found.id
