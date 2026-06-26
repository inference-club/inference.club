"""Unit tests for the inference-request serializer helpers that normalize the
heterogeneous OpenAI request/response shapes. Pure functions — no DB."""
from types import SimpleNamespace

from apps.inference.serializers import (
    _extract_messages,
    _extract_reasoning,
    _extract_response_text,
    _extract_usage,
    _gpus_for_host,
    _stringify_content,
    _truncate,
    request_host_info,
)


def _provider(*hosts):
    """A stand-in provider whose manifest declares ``hosts`` — enough for
    _gpus_for_host, which only reads ``provider.manifest.parsed['hosts']``."""
    return SimpleNamespace(
        id=1, manifest=SimpleNamespace(parsed={"hosts": list(hosts)})
    )


class TestGpusForHost:
    A = {"id": "a1", "gpus": [{"model": "RTX 4090"}]}
    B = {"id": "a2", "gpus": [{"model": "RTX 3090"}, {"model": "RTX 3090"}]}

    def test_matched_host_returns_only_its_gpus(self):
        assert _gpus_for_host(_provider(self.A, self.B), "a1") == ["RTX 4090"]

    def test_unknown_host_on_multi_host_returns_empty(self):
        # The bug: a request that named a host the manifest no longer lists must
        # NOT fall back to every GPU on the provider.
        assert _gpus_for_host(_provider(self.A, self.B), "gone") == []

    def test_no_host_on_multi_host_returns_empty(self):
        assert _gpus_for_host(_provider(self.A, self.B), None) == []

    def test_no_host_on_single_host_attributes_unambiguously(self):
        assert _gpus_for_host(_provider(self.A), None) == ["RTX 4090"]

    def test_dedupes_within_a_host(self):
        assert _gpus_for_host(_provider(self.B), "a2") == ["RTX 3090"]

    def test_supports_singular_gpu_string(self):
        host = {"id": "h", "gpu": "A100"}
        assert _gpus_for_host(_provider(host), "h") == ["A100"]

    def test_no_manifest_returns_empty(self):
        assert _gpus_for_host(SimpleNamespace(manifest=None), "a1") == []


class TestRequestHostInfo:
    """request_host_info prefers the durable ``host`` FK; when it's absent
    (un-backfilled legacy rows, mocked here with ``host=None``) it falls back to
    the dispatch_meta host_id + manifest-JSON walk. We lock in that pure fallback
    branch; the FK fast path is covered by the API tests."""

    def test_legacy_fallback_uses_stored_host_id(self):
        req = SimpleNamespace(
            host=None, host_id=None,
            gpu=None,
            dispatch_meta={"provider_model_id": 7, "host_id": "a1"},
            provider=_provider(TestGpusForHost.A, TestGpusForHost.B),
        )
        assert request_host_info(req) == {
            "host_id": "a1",
            "hostname": "",
            "provider_id": 1,
            "gpus": [{"index": 0, "model": "RTX 4090", "vram_gb": None}],
            "gpu": None,
        }

    def test_blank_stored_host_with_no_pm_is_unknown(self):
        # Sync request whose service had no host_id, multi-host provider →
        # "unknown", never a union of every GPU.
        req = SimpleNamespace(
            host=None, host_id=None,
            gpu=None,
            dispatch_meta={"provider_model_id": None, "host_id": ""},
            provider=_provider(TestGpusForHost.A, TestGpusForHost.B),
        )
        assert request_host_info(req) == {
            "host_id": None,
            "hostname": "",
            "provider_id": 1,
            "gpus": [],
            "gpu": None,
        }


class TestExtractMessages:
    def test_chat_messages(self):
        payload = {"messages": [{"role": "user", "content": "hi"}]}
        assert _extract_messages(payload) == [{"role": "user", "content": "hi", "media": []}]

    def test_legacy_completions_prompt(self):
        assert _extract_messages({"prompt": "hey"}) == [
            {"role": "user", "content": "hey", "media": []}
        ]

    def test_empty_or_bad(self):
        assert _extract_messages({}) == []
        assert _extract_messages(None) == []


class TestStringifyContent:
    def test_plain_string(self):
        assert _stringify_content("hello") == "hello"

    def test_multimodal_parts(self):
        # Media parts are rendered separately now (see _message_media), so they
        # no longer pollute the flattened text; genuinely-unknown types still do.
        content = [
            {"type": "text", "text": "describe this"},
            {"type": "image_url", "image_url": {"url": "x"}},
            {"type": "mystery"},
        ]
        out = _stringify_content(content)
        assert "describe this" in out
        assert "[image_url]" not in out
        assert "[mystery]" in out


class TestResponseText:
    def test_buffered_message(self):
        results = {"choices": [{"message": {"content": "answer"}}]}
        assert _extract_response_text(results) == "answer"

    def test_legacy_text(self):
        assert _extract_response_text({"choices": [{"text": "foo"}]}) == "foo"

    def test_strips_inline_think_block(self):
        results = {"choices": [{"message": {"content": "<think>hidden</think>real answer"}}]}
        out = _extract_response_text(results)
        assert "hidden" not in out
        assert out == "real answer"

    def test_empty(self):
        assert _extract_response_text({}) == ""


class TestReasoning:
    def test_reasoning_field(self):
        results = {"choices": [{"message": {"reasoning": "because"}}]}
        assert _extract_reasoning(results) == "because"

    def test_reasoning_content_alias(self):
        results = {"choices": [{"message": {"reasoning_content": "rc"}}]}
        assert _extract_reasoning(results) == "rc"

    def test_inline_think_fallback(self):
        results = {"choices": [{"message": {"content": "<think>my chain</think>done"}}]}
        assert _extract_reasoning(results) == "my chain"

    def test_none_when_absent(self):
        assert _extract_reasoning({"choices": [{"message": {"content": "no reasoning"}}]}) == ""


class TestUsageAndTruncate:
    def test_extract_usage(self):
        assert _extract_usage(
            {"usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}
        ) == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}

    def test_extract_usage_none(self):
        assert _extract_usage({}) is None

    def test_truncate(self):
        assert _truncate("short") == "short"
        long = "x" * 500
        out = _truncate(long, 280)
        assert len(out) <= 281  # 280 chars + ellipsis
        assert out.endswith("…")
