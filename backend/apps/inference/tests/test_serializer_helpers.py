"""Unit tests for the inference-request serializer helpers that normalize the
heterogeneous OpenAI request/response shapes. Pure functions — no DB."""
from apps.inference.serializers import (
    _extract_messages,
    _extract_reasoning,
    _extract_response_text,
    _extract_usage,
    _stringify_content,
    _truncate,
)


class TestExtractMessages:
    def test_chat_messages(self):
        payload = {"messages": [{"role": "user", "content": "hi"}]}
        assert _extract_messages(payload) == [{"role": "user", "content": "hi"}]

    def test_legacy_completions_prompt(self):
        assert _extract_messages({"prompt": "hey"}) == [{"role": "user", "content": "hey"}]

    def test_empty_or_bad(self):
        assert _extract_messages({}) == []
        assert _extract_messages(None) == []


class TestStringifyContent:
    def test_plain_string(self):
        assert _stringify_content("hello") == "hello"

    def test_multimodal_parts(self):
        content = [
            {"type": "text", "text": "describe this"},
            {"type": "image_url", "image_url": {"url": "x"}},
        ]
        out = _stringify_content(content)
        assert "describe this" in out
        assert "[image_url]" in out


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
