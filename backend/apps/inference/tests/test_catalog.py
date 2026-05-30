"""Unit tests for the OpenRouter-style model catalog heuristics + schema
builder. Pure functions — no DB (uses a lightweight stub for ProviderModel)."""
from datetime import datetime, timezone
from types import SimpleNamespace

from apps.inference.views import (
    _guess_features,
    _guess_modalities,
    _guess_quantization,
    _parse_throttle_rate,
    openrouter_model_schema,
)


class TestHeuristics:
    def test_quantization(self):
        assert _guess_quantization("nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4") == "fp4"
        assert _guess_quantization("org/model-AWQ-INT4") == "int4"
        assert _guess_quantization("org/model-FP8") == "fp8"
        assert _guess_quantization("meta/llama-3-8b") is None

    def test_features_reasoning(self):
        assert "reasoning" in _guess_features("x/QwQ-32B")
        assert "reasoning" in _guess_features("nvidia/Nemotron-Reasoning")
        assert _guess_features("meta/llama-3-8b") == []

    def test_modalities(self):
        inp, out = _guess_modalities("nvidia/Nemotron-3-Nano-Omni-30B")
        assert inp == ["text", "image"]
        assert out == ["text"]
        assert _guess_modalities("meta/llama-3-8b") == (["text"], ["text"])

    def test_parse_throttle_rate(self):
        assert _parse_throttle_rate("60/min") == (60, 60)
        assert _parse_throttle_rate("120/hour") == (120, 3600)
        assert _parse_throttle_rate("") == (None, None)
        assert _parse_throttle_rate("bogus") == (None, None)


def _stub_model(name, metadata=None, context_window=None):
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return SimpleNamespace(
        name=name,
        metadata=metadata or {},
        context_window=context_window,
        created_on=created,
        provider=SimpleNamespace(created_on=created),
    )


class TestOpenRouterSchema:
    def test_derives_from_id_heuristics(self):
        pm = _stub_model("nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4", context_window=32768)
        s = openrouter_model_schema(pm)
        assert s["id"] == pm.name
        assert s["quantization"] == "fp4"
        assert "reasoning" in s["supported_features"]
        assert s["input_modalities"] == ["text", "image"]
        assert s["context_length"] == 32768
        # No economic model yet → pricing present but zeroed.
        assert s["pricing"]["prompt"] == "0"
        assert s["is_ready"] is True

    def test_metadata_overrides_heuristics(self):
        pm = _stub_model(
            "meta/llama-3-8b",
            metadata={
                "name": "Llama 3 8B",
                "quantization": "fp16",
                "context_length": 8192,
                "max_output_length": 4096,
                "supported_features": ["tools", "json_mode"],
            },
        )
        s = openrouter_model_schema(pm)
        assert s["name"] == "Llama 3 8B"
        assert s["quantization"] == "fp16"
        assert s["context_length"] == 8192
        assert s["max_output_length"] == 4096
        assert s["supported_features"] == ["tools", "json_mode"]
