"""Phase 2 — HuggingFace enrichment + the human model catalog view.
HF network calls are monkeypatched, so these never touch the network."""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.inference import hf_enrich
from apps.inference.models import CatalogModel, Provider, ProviderModel

User = get_user_model()


class TestInference:
    def test_modalities_from_config_vision(self):
        inp, out = hf_enrich.infer_modalities({}, {"vision_config": {}}, "org/m")
        assert inp == ["text", "image"]
        assert out == ["text"]

    def test_modalities_from_keywords(self):
        inp, _ = hf_enrich.infer_modalities(
            {"pipeline_tag": "image-text-to-text", "tags": ["audio"]}, {}, "x/omni"
        )
        assert "image" in inp and "audio" in inp

    def test_modalities_text_only_default(self):
        inp, out = hf_enrich.infer_modalities({}, {}, "meta/llama-3-8b")
        assert inp == ["text"] and out == ["text"]

    def test_features_reasoning_and_tools(self):
        feats = hf_enrich.infer_features({"tags": ["tool-use"]}, {}, "x/QwQ-32B")
        assert "reasoning" in feats and "tools" in feats

    def test_architecture_from_config(self):
        assert hf_enrich._architecture({}, {"architectures": ["Qwen2VLForCausalLM"]}) == "Qwen2VLForCausalLM"


@pytest.mark.django_db
class TestEnrich:
    def test_enrich_populates_from_hub(self, monkeypatch):
        monkeypatch.setattr(
            hf_enrich,
            "_fetch",
            lambda repo: (
                {"pipeline_tag": "image-text-to-text", "tags": ["vision"], "downloads": 99, "likes": 5},
                {"architectures": ["Qwen2VLForCausalLM"], "model_type": "qwen2_vl", "max_position_embeddings": 32768},
            ),
        )
        c = CatalogModel.objects.create(slug="qwen/qwen2-vl", hf_repo_id="Qwen/Qwen2-VL")
        assert hf_enrich.enrich_catalog_model(c) is True
        c.refresh_from_db()
        assert c.architecture == "Qwen2VLForCausalLM"
        assert c.native_context_length == 32768
        assert c.input_modalities == ["text", "image"]
        assert c.display_name == "Qwen2-VL"
        assert c.hf_synced_at is not None
        assert c.metadata["downloads"] == 99

    def test_skips_custom_no_hf(self):
        c = CatalogModel(slug="my-ft", hf_repo_id="", is_custom=True)
        c.save()
        assert hf_enrich.enrich_catalog_model(c) is False

    def test_respects_ttl(self, monkeypatch):
        called = {"n": 0}

        def _fake(repo):
            called["n"] += 1
            return {}, {}

        monkeypatch.setattr(hf_enrich, "_fetch", _fake)
        c = CatalogModel.objects.create(
            slug="org/m", hf_repo_id="Org/M", hf_synced_at=timezone.now()
        )
        assert hf_enrich.enrich_catalog_model(c) is False  # fresh → skipped
        assert called["n"] == 0
        assert hf_enrich.enrich_catalog_model(c, force=True) is True  # forced → fetched
        assert called["n"] == 1

    def test_falls_back_when_hub_unreachable(self, monkeypatch):
        monkeypatch.setattr(hf_enrich, "_fetch", lambda repo: (None, None))
        c = CatalogModel.objects.create(slug="x/qwq-32b", hf_repo_id="x/QwQ-32B")
        assert hf_enrich.enrich_catalog_model(c) is True
        c.refresh_from_db()
        # keyword fallback on the slug still classifies it as a reasoning model
        assert "reasoning" in c.supported_features
        assert c.metadata["hf_ok"] is False


@pytest.mark.django_db
class TestCatalogView:
    def test_lists_models_with_active_deployments(self, monkeypatch):
        # No network: pre-stamp hf_synced_at so the view's lazy enrich is a no-op.
        user = User.objects.create_user(email="u@example.com", password="x")
        p = Provider.objects.create(
            user=user, name="club-host", tailnet_hostname="h1",
            is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
        )
        c = CatalogModel.objects.create(
            slug="org/model", hf_repo_id="Org/Model", display_name="Model",
            input_modalities=["text", "image"], supported_features=["reasoning"],
            native_context_length=32768, hf_synced_at=timezone.now(),
        )
        ProviderModel.objects.create(provider=p, name="Org/Model", catalog_model=c, is_active=True)
        # An inactive-deployment-only catalog model must NOT appear.
        c2 = CatalogModel.objects.create(slug="ghost/model", hf_synced_at=timezone.now())
        ProviderModel.objects.create(provider=p, name="ghost", catalog_model=c2, is_active=False)

        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.get("/api/inference/models/")
        assert resp.status_code == 200
        models = resp.data["models"]
        slugs = [m["slug"] for m in models]
        assert "org/model" in slugs
        assert "ghost/model" not in slugs
        entry = next(m for m in models if m["slug"] == "org/model")
        assert entry["context_length"] == 32768
        assert entry["input_modalities"] == ["text", "image"]
        assert entry["provider_count"] == 1
        assert entry["online_provider_count"] == 1
        assert entry["hf_url"] == "https://huggingface.co/Org/Model"
