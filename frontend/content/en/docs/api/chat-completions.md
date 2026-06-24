---
title: POST /v1/chat/completions
description: OpenAI-compatible chat completions, with streaming.
category: API reference
order: 3
---

# `POST /v1/chat/completions`

::api-endpoint{method="POST" path="/v1/chat/completions" async="true"}

The main inference endpoint. Same request and response shape as OpenAI; inference.club proxies the request to one of your online providers and streams the response back.

::callout{type="tip"}
This endpoint can also be run asynchronously — add `"async": true` to queue it as a job instead of blocking. See [Direct vs async](/docs/services/direct-vs-async).
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

`model` is required and must match a model name advertised by one of your online providers. Lookup is exact-match.

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
| `404` | No online provider on your account serves the requested model. |
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
