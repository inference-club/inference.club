---
title: API overview
description: Base URL, authentication, error format.
category: API reference
order: 1
---

# API overview

## Base URL

```
https://api.inference.club/v1
```

The `/v1` namespace mirrors the OpenAI API surface. Anything that speaks OpenAI — the official SDKs, Open WebUI, OpenRouter-style routers — can use this base URL with no other changes.

## Authentication

All `/v1/*` requests require a Bearer token:

```
Authorization: Bearer <your-api-key>
```

Get a key from **Dashboard → Settings → Token**. The same key authenticates both inference (`/v1/...`) and your agent's heartbeats (`/api/inference/agent/heartbeat/`).

Requests without a valid token return `401 Unauthorized`.

## Error format

Errors come back in OpenAI's error envelope:

```json
{
  "error": {
    "message": "No online provider serving model 'qwen3-8b' for this user.",
    "type": "no_provider"
  }
}
```

Common types:

| `type` | When | HTTP |
|---|---|---|
| `no_provider` | The model you asked for isn't being served by any of your online providers right now | 404 |
| `upstream_error` | The agent's local LLM server returned an error or didn't respond | 502 |

Most other failures (auth, malformed JSON) come from Django REST Framework's defaults and use the standard `{"detail": "..."}` shape.

## Streaming

`/v1/chat/completions` and `/v1/completions` honor the `stream: true` flag in the request body. The response is a Server-Sent Events stream of OpenAI-format delta chunks ending with `data: [DONE]`. Streaming passes through inference.club untouched, so the chunk shape is whatever your provider's local LLM server emits.

## Rate limits

There aren't any yet. There will be before this is publicly open.
