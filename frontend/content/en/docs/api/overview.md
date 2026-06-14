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

> Prefer an interactive reference? The **[API explorer](/api-reference)** renders the full OpenAPI spec with an "Authorize → Try it out" flow. The machine-readable spec is at [`api.inference.club/openapi.json`](https://api.inference.club/openapi.json).

## Endpoints

### Inference (synchronous or async)

| Endpoint | Modality |
|---|---|
| `GET /v1/models` | List models you can reach (with capabilities). |
| `POST /v1/chat/completions` | [Chat completions](/docs/api/chat-completions) — text chat, multimodal input. |
| `POST /v1/completions` | Legacy text completions. |
| `POST /v1/audio/transcriptions` | [Speech-to-text](/docs/api/audio-transcriptions) — audio in, text out. |
| `POST /v1/audio/speech` | [Text to speech](/docs/api/speech) — text in, audio out. |
| `POST /v1/images/generations` | [Image generation](/docs/api/images) — text in, image out. |
| `POST /v1/images/edits` | [Image edits](/docs/api/images) — image + prompt in, image out. |
| `POST /v1/music/generations` | [Music generation](/docs/api/music-generations) — text + optional lyrics in, audio out. |
| `POST /v1/videos/generations` | [Video generation](/docs/api/video-generations) — text (+ optional image) in, video out. |
| `POST /v1/voice/generations` | [Voice cloning](/docs/api/voice-generations) — Dia dialogue synthesis with speaker voice samples. |
| `POST /v1/3d/generations` | 3D mesh generation — text or image in, GLB/mesh out. |

### Async jobs, batches, and workflows

Add `"async": true` to any JSON-bodied inference body to queue the request instead of blocking. Manage queued work with these endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /v1/jobs` | List your async jobs. |
| `GET /v1/jobs/<id>` | Get a job's status and result. |
| `POST /v1/jobs/<id>/cancel` | Cancel a queued or processing job. |
| `POST /v1/jobs/<id>/retry` | Re-queue a failed or canceled job. |
| `POST /v1/batches` | Submit up to 256 requests as one batch. |
| `GET /v1/batches` | List your batches. |
| `GET /v1/batches/<id>` | Get batch status and job summary. |
| `GET /v1/workflows/templates` | List curated, ready-to-run workflow templates. |
| `POST /v1/workflows/runs` | Start a workflow run (from a template or an inline spec). |
| `GET /v1/workflows/runs` | List your workflow runs. |
| `GET /v1/workflows/runs/<id>` | Get the live DAG state, steps, and media. |
| `POST /v1/workflows/runs/<id>/steps/<step_id>/approve` | Approve a gate step. |
| `POST /v1/workflows/runs/<id>/steps/<step_id>/reject` | Reject a gate step. |

See the [jobs](/docs/api/jobs), [batches](/docs/api/batches), and [workflows](/docs/api/workflows) references.

Each model on `/v1/models` reports `input_modalities`, `output_modalities`, `supported_features`, and a `service_type` (`llm`/`stt`/`tts`/`image`/`music`/`video`/`mesh`), so a client can distinguish modalities. A request is only routed to a service whose provider declared the matching `type`.

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

## Async opt-in

Any JSON-bodied inference endpoint (`/v1/chat/completions`, `/v1/images/generations`, `/v1/videos/generations`, `/v1/music/generations`, `/v1/audio/speech`) accepts an extra `"async": true` field. When present, the server queues the request as a job and returns `202 Accepted` with a job envelope instead of waiting for the upstream provider to finish. The `async` flag is stripped before the body reaches a provider.

File-upload endpoints (`/v1/audio/transcriptions`, `/v1/images/edits`, `/v1/voice/generations`) are synchronous only.

## Rate limits

There aren't any yet. There will be before this is publicly open.
