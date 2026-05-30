"""Unit tests for the OpenAI proxy's streaming assembly, token capture, and
request guardrails. Pure functions — no DB, fast."""
import json

from apps.inference.openai_views import (
    _assemble_streamed_results,
    _clamp_max_tokens,
    _ensure_stream_usage,
    _request_too_large,
    _usage_tokens,
)


def _sse(*objs) -> list:
    """Render objects as SSE `data:` byte chunks, ending with [DONE]."""
    lines = [f"data: {json.dumps(o)}\n\n".encode() for o in objs]
    lines.append(b"data: [DONE]\n\n")
    return lines


class TestAssembleStreamedResults:
    def test_chat_stream_assembles_content_reasoning_usage(self):
        chunks = _sse(
            {"model": "m1", "choices": [{"delta": {"role": "assistant"}}]},
            {"choices": [{"delta": {"reasoning": "let me think"}}]},
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}, ]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            {"usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}, "choices": []},
        )
        r = _assemble_streamed_results(chunks, "fallback")
        assert r["streamed"] is True
        assert r["object"] == "chat.completion"
        assert r["model"] == "m1"
        msg = r["choices"][0]["message"]
        assert msg["content"] == "Hello"
        assert msg["reasoning"] == "let me think"
        assert r["choices"][0]["finish_reason"] == "stop"
        assert r["usage"]["total_tokens"] == 5

    def test_chat_stream_without_usage_has_no_usage(self):
        chunks = _sse({"choices": [{"delta": {"content": "hi"}}]})
        r = _assemble_streamed_results(chunks, "m")
        assert r["choices"][0]["message"]["content"] == "hi"
        assert "usage" not in r
        assert r["model"] == "m"  # falls back to provided model name

    def test_reasoning_content_alias(self):
        chunks = _sse({"choices": [{"delta": {"reasoning_content": "rc"}}]})
        r = _assemble_streamed_results(chunks, "m")
        assert r["choices"][0]["message"]["reasoning"] == "rc"

    def test_legacy_completions_stream(self):
        chunks = _sse(
            {"choices": [{"text": "foo"}]},
            {"choices": [{"text": "bar"}]},
        )
        r = _assemble_streamed_results(chunks, "m")
        assert r["object"] == "text_completion"
        assert r["choices"][0]["text"] == "foobar"

    def test_ignores_malformed_lines(self):
        chunks = [b"data: not-json\n\n", *_sse({"choices": [{"delta": {"content": "ok"}}]})]
        r = _assemble_streamed_results(chunks, "m")
        assert r["choices"][0]["message"]["content"] == "ok"


class TestUsageTokens:
    def test_extracts_all_three(self):
        assert _usage_tokens(
            {"usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}
        ) == (1, 2, 3)

    def test_computes_total_when_missing(self):
        assert _usage_tokens({"usage": {"prompt_tokens": 4, "completion_tokens": 6}}) == (4, 6, 10)

    def test_none_when_absent(self):
        assert _usage_tokens({}) == (None, None, None)
        assert _usage_tokens({"usage": {}}) == (None, None, None)
        assert _usage_tokens(None) == (None, None, None)


class TestEnsureStreamUsage:
    def test_injects_when_absent(self):
        body = {"model": "m", "stream": True}
        _ensure_stream_usage(body)
        assert body["stream_options"] == {"include_usage": True}

    def test_preserves_explicit_choice(self):
        body = {"stream_options": {"include_usage": False}}
        _ensure_stream_usage(body)
        assert body["stream_options"]["include_usage"] is False

    def test_adds_to_existing_options(self):
        body = {"stream_options": {"continuous_usage_stats": True}}
        _ensure_stream_usage(body)
        assert body["stream_options"]["include_usage"] is True
        assert body["stream_options"]["continuous_usage_stats"] is True


class TestRequestGuardrails:
    def test_too_many_messages(self, settings):
        settings.INFERENCE_MAX_MESSAGES = 2
        assert _request_too_large({"messages": [{}, {}, {}]}) is not None
        assert _request_too_large({"messages": [{}, {}]}) is None

    def test_input_too_large(self, settings):
        settings.INFERENCE_MAX_INPUT_CHARS = 10
        assert _request_too_large(
            {"messages": [{"role": "user", "content": "way too long"}]}
        ) is not None
        assert _request_too_large({"messages": [{"role": "user", "content": "hi"}]}) is None

    def test_prompt_field_counts(self, settings):
        settings.INFERENCE_MAX_INPUT_CHARS = 5
        assert _request_too_large({"prompt": "0123456789"}) is not None

    def test_clamp_max_tokens(self, settings):
        settings.INFERENCE_MAX_OUTPUT_TOKENS = 100
        body = {"max_tokens": 999}
        _clamp_max_tokens(body)
        assert body["max_tokens"] == 100

    def test_clamp_leaves_small_and_absent_alone(self, settings):
        settings.INFERENCE_MAX_OUTPUT_TOKENS = 100
        body = {"max_tokens": 50}
        _clamp_max_tokens(body)
        assert body["max_tokens"] == 50
        body2 = {}
        _clamp_max_tokens(body2)
        assert "max_tokens" not in body2
