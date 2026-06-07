"""Unit tests for the OpenRouter-style model catalog schema builder. Pure
function — no DB (uses lightweight stubs for ProviderModel + CatalogModel).

Capabilities are sourced from the linked CatalogModel (declared in the operator
manifest); per-deployment overrides on ProviderModel.metadata win."""
from datetime import datetime, timezone
from types import SimpleNamespace

from apps.inference.views import _parse_throttle_rate, openrouter_model_schema


def _stub_catalog(**kw):
    return SimpleNamespace(
        display_name=kw.get("display_name", ""),
        hf_repo_id=kw.get("hf_repo_id", ""),
        input_modalities=kw.get("input_modalities", []),
        output_modalities=kw.get("output_modalities", []),
        supported_features=kw.get("supported_features", []),
        native_context_length=kw.get("native_context_length"),
    )


def _stub_model(name, metadata=None, context_window=None, served_context_len=None, catalog=None):
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return SimpleNamespace(
        name=name,
        metadata=metadata or {},
        context_window=context_window,
        served_context_len=served_context_len,
        catalog_model=catalog,
        catalog_model_id=(1 if catalog is not None else None),
        created_on=created,
        provider=SimpleNamespace(created_on=created),
    )


class TestParseThrottleRate:
    def test_parse_throttle_rate(self):
        assert _parse_throttle_rate("60/min") == (60, 60)
        assert _parse_throttle_rate("120/hour") == (120, 3600)
        assert _parse_throttle_rate("") == (None, None)
        assert _parse_throttle_rate("bogus") == (None, None)


class TestOpenRouterSchema:
    def test_sources_capabilities_from_catalog(self):
        cat = _stub_catalog(
            display_name="Qwen3 30B A3B",
            hf_repo_id="Qwen/Qwen3-30B-A3B",
            input_modalities=["text", "image"],
            output_modalities=["text"],
            supported_features=["reasoning", "tools"],
            native_context_length=32768,
        )
        pm = _stub_model("qwen3-30b-a3b", metadata={"quantization": "fp8"}, catalog=cat)
        s = openrouter_model_schema(pm)
        assert s["id"] == "qwen3-30b-a3b"
        assert s["name"] == "Qwen3 30B A3B"
        assert s["input_modalities"] == ["text", "image"]
        assert s["output_modalities"] == ["text"]
        assert s["supported_features"] == ["reasoning", "tools"]
        assert s["context_length"] == 32768
        assert s["quantization"] == "fp8"
        assert s["hugging_face_id"] == "Qwen/Qwen3-30B-A3B"
        # No economic model yet → pricing present but zeroed.
        assert s["pricing"]["prompt"] == "0"
        assert s["is_ready"] is True

    def test_live_served_window_beats_declared_ceiling(self):
        cat = _stub_catalog(native_context_length=32768)
        pm = _stub_model("m", served_context_len=8192, catalog=cat)
        assert openrouter_model_schema(pm)["context_length"] == 8192

    def test_metadata_overrides_catalog(self):
        cat = _stub_catalog(
            input_modalities=["text"],
            supported_features=["reasoning"],
            native_context_length=4096,
        )
        pm = _stub_model(
            "m",
            metadata={
                "name": "Custom Name",
                "context_length": 8192,
                "max_output_length": 4096,
                "supported_features": ["tools", "json_mode"],
                "input_modalities": ["text", "image"],
            },
            catalog=cat,
        )
        s = openrouter_model_schema(pm)
        assert s["name"] == "Custom Name"
        assert s["context_length"] == 8192
        assert s["max_output_length"] == 4096
        assert s["supported_features"] == ["tools", "json_mode"]
        assert s["input_modalities"] == ["text", "image"]

    def test_no_catalog_defaults_to_text(self):
        pm = _stub_model("live-discovered-model", context_window=16384)
        s = openrouter_model_schema(pm)
        assert s["input_modalities"] == ["text"]
        assert s["output_modalities"] == ["text"]
        assert s["supported_features"] == []
        assert s["context_length"] == 16384
        assert "quantization" not in s
