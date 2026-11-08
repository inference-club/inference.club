---
title: POST /v1/completions
description: Legacy text-completion endpoint.
category: API reference
order: 4
---

# `POST /v1/completions`

::api-endpoint{method="POST" path="/v1/completions" async="true"}

The legacy text-completion endpoint. Same shape as OpenAI's `/v1/completions`. Most clients use [chat completions](/docs/api/chat-completions) instead, but completion-style models (older base models, code-completion models) still use this surface.

## Request

```bash
curl https://api.inference.club/v1/completions \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "code-llama-7b",
    "prompt": "def fizzbuzz(n):",
    "max_tokens": 100
  }'
```

Routing, limits, authentication, and `async` behave exactly as for chat completions. The body is forwarded to the provider's `/completions` endpoint unchanged, and streaming works the same way (`"stream": true`).

If you don't have a clear reason to use this endpoint, use [chat completions](/docs/api/chat-completions) — modern instruct-tuned models are trained for that format.
