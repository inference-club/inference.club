---
title: POST /v1/chat/completions
description: OpenAI-compatible chat completions, with streaming.
category: API reference
order: 3
---

# `POST /v1/chat/completions`

::api-endpoint{method="POST" path="/v1/chat/completions" async="true"}

The main inference endpoint. Same request and response shape as OpenAI; inference.club proxies the request to an online provider you can reach (your own nodes, or services other members share with you) and streams the response back.

::callout{type="tip"}
This endpoint can also be run asynchronously — add `"async": true` (always queue) or `"async": "auto"` to get a job back instead of blocking; the finished job's `output_text` holds the full response. See [Async jobs](/docs/api/jobs). Direct chat calls aren't capacity-gated — LLM servers batch concurrent requests themselves.
::

## Request

```bash
curl https://api.inference.club/v1/chat/completions \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-8b",
    "messages": [
      {"role": "system", "content": "You are concise."},
      {"role": "user", "content": "Say hello."}
    ],
    "temperature": 0.2
  }'
```

The body is forwarded to the provider's LLM server unchanged, so any OpenAI-compatible field your local server understands (`temperature`, `top_p`, `max_tokens`, `tools`, `response_format`, …) just works.

`model` is required and must be an `id` from [`GET /v1/models`](/docs/api/models). Requests are bounded: at most 200 messages and 100,000 input characters (`413 request_too_large` beyond that), and an explicit `max_tokens` above 8,192 is clamped.

## Buffered response

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1729960000,
  "model": "qwen3-8b",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "Hello."},
      "finish_reason": "stop"
    }
  ]
}
```

## Streaming

Add `"stream": true` to the request body. The response becomes a Server-Sent Events stream of OpenAI-format delta chunks:

```
data: {"choices":[{"index":0,"delta":{"role":"assistant"}}]}

data: {"choices":[{"index":0,"delta":{"content":"Hello"}}]}

data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

inference.club passes the upstream stream through with no buffering, so chunks arrive as fast as your provider's local server can produce them.

## Error responses

| HTTP | Meaning |
|---|---|
| `401` | Missing or invalid Bearer token. |
| `404` | No online provider you can reach serves the requested model (`no_provider`). |
| `413` | Too many messages or input characters (`request_too_large`). |
| `429` | Your account's rate limit (`{"detail": …}` body, honor `Retry-After`). |
| `502` | The provider was reachable but its local LLM server errored or timed out. |

The 404 response uses inference.club's error envelope:

```json
{
  "error": {
    "message": "No online provider serving model 'foo' for this user.",
    "type": "no_provider"
  }
}
```
