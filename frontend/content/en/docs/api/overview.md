---
title: API overview
description: Base URL, authentication, error format, async modes, capacity, and limits.
category: API reference
order: 1
---

# API overview

## Base URL

```
https://api.inference.club/v1
```

The `/v1` namespace mirrors the OpenAI API surface. Anything that speaks OpenAI — the official SDKs, Open WebUI, OpenRouter-style routers — can use this base URL with no other changes.

> Prefer an interactive reference? The **[API explorer](/api-reference)** renders the full OpenAPI spec with an "Authorize → Try it out" flow. The machine-readable spec is at [`api.inference.club/openapi.json`](https://api.inference.club/openapi.json). Building an agent? Start with the [agent quickstart](/docs/quickstart-agents).

## Endpoints

### Inference

| Endpoint | Body | Response | `async` |
|---|---|---|---|
| `GET /v1/models` | — | List models you can reach (with capabilities). | — |
| `POST /v1/chat/completions` | JSON | [Chat completions](/docs/api/chat-completions) — JSON or SSE stream. | ✓ |
| `POST /v1/completions` | JSON | [Legacy text completions](/docs/api/completions). | ✓ |
| `POST /v1/images/generations` | JSON | [Image generation](/docs/api/images) — JSON with image URLs. | ✓ |
| `POST /v1/images/edits` | multipart | [Image edits](/docs/api/images#edits) — JSON with image URLs. | sync only |
| `POST /v1/audio/speech` | JSON | [Text to speech](/docs/api/speech) — raw audio bytes (or JSON with `delivery: "url"`). | ✓ |
| `GET /v1/audio/voices` | — | List the TTS voices a model offers (`?model=`). | — |
| `POST /v1/voice/generations` | JSON | [Voice cloning](/docs/api/voice-generations) — raw audio bytes (or `delivery: "url"`). | sync only |
| `POST /v1/music/generations` | JSON | [Music generation](/docs/api/music-generations) — raw audio bytes (or `delivery: "url"`). | ✓ |
| `POST /v1/videos/generations` | JSON | [Video generation](/docs/api/video-generations) — raw MP4 bytes (or `delivery: "url"`). | ✓ |
| `POST /v1/audio/transcriptions` | multipart | [Speech-to-text](/docs/api/audio-transcriptions) — JSON text. | sync only |
| `POST /v1/audio/enhance` | multipart | [Audio enhancement](/docs/api/audio-enhance) — raw audio bytes (or `delivery: "url"`). | sync only |
| `POST /v1/3d/generations` | multipart (`image` + optional `options`) | Image-to-3D — JSON `{"data": [{"url", "type": "model/gltf-binary"}]}`. | sync only |
| `POST /v1/scrape` | JSON `{model, url}` | URL → JSON `{request_id, markdown, title, source_url, chars}`. | ✓ |

### Async jobs, batches, workflows, capacity

| Endpoint | Purpose |
|---|---|
| `GET /v1/capacity` | Live GPU slot usage per model (see [Capacity](#capacity)). |
| `GET /v1/jobs` | List your async jobs. |
| `GET /v1/jobs/<id>` | A job's status and result (`output_text`, `media`). |
| `POST /v1/jobs/<id>/cancel` | Cancel a queued job. |
| `POST /v1/jobs/<id>/retry` | Re-queue a failed or canceled job. |
| `POST /v1/batches` | Submit up to 256 requests as one batch. |
| `GET /v1/batches` | List your batches. |
| `GET /v1/batches/<id>` | Batch status and its jobs. `POST` to the same path cancels it. |
| `GET /v1/workflows/templates` | Curated, ready-to-run workflow templates. |
| `POST /v1/workflows/runs` | Start a workflow run (template or inline spec). |
| `GET /v1/workflows/runs` | List your workflow runs. |
| `GET /v1/workflows/runs/<id>` | Live DAG state, steps, and outputs. |
| `POST /v1/workflows/runs/<id>/steps/<step_id>/approve` | Approve a gate step. |
| `POST /v1/workflows/runs/<id>/steps/<step_id>/reject` | Reject a gate step. |
| `POST /v1/workflows/runs/<id>/steps/<step_id>/rerun` | Re-run one step and everything downstream. |

See the [jobs](/docs/api/jobs), [batches](/docs/api/batches), and [workflows](/docs/api/workflows) references.

Each model on `/v1/models` reports `service_type` (`llm`, `stt`, `tts`, `image`, `music`, `video`, `mesh`, `scrape`, `audio-enhance`), `input_modalities`, `output_modalities`, `supported_features`, and `context_length`. A request is only routed to a service of the matching type — a transcription never lands on an LLM.

## Authentication

All `/v1/*` requests require a Bearer token:

```
Authorization: Bearer <your-api-key>
```

Get a key from **Dashboard → Settings → Token**. The same key authenticates both inference (`/v1/...`) and your agent's heartbeats. Requests without a valid token return `401` with DRF's `{"detail": "..."}` body.

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
| `invalid_request` / `missing_prompt` / `missing_input` / `missing_file` | Malformed or incomplete body | 400 |
| `missing_api_key` | A `provider:model` external model with no key saved for that provider | 400 |
| `no_provider` | No online provider you can reach serves that model right now | 404 |
| `request_too_large` / `file_too_large` | Input over a [limit](#limits) | 413 |
| `unsupported_media_type` | Uploaded file isn't an accepted type | 415 |
| `at_capacity` | Every GPU slot serving the model is busy (see [Capacity](#capacity)). Has `retry_after` and a `Retry-After` header. | 429 |
| `upstream_error` | The provider's model server returned an error or didn't respond | 502 |
| `async_disabled` | `async` / batches / workflows on a deployment without a job queue | 503 |

Auth failures and **rate-limit** 429s come from Django REST Framework and use `{"detail": "..."}` instead. Tell the two 429s apart by the body: `error.type == "at_capacity"` means *this model's device* is busy; a `detail` body means *your account* is over its request rate.

## Streaming

`/v1/chat/completions` and `/v1/completions` honor `stream: true`. The response is a Server-Sent Events stream of OpenAI-format delta chunks ending with `data: [DONE]`, passed through from the provider's server unbuffered.

## Async

Async-capable endpoints (✓ above) accept an `async` field, stripped before the body reaches a provider:

| `async` | Behavior |
|---|---|
| omitted / `false` | Synchronous. |
| `true` | Always queue as a job; returns `202 Accepted`. |
| `"auto"` | Run now if a GPU slot is free; otherwise queue and return `202`. A known model whose provider is momentarily offline is also queued (it waits up to an hour) instead of returning `404`. |

The `202` body is a job envelope:

```json
{
  "id": "42",
  "object": "inference.job",
  "status": "QUEUED",
  "inference_type": "IMAGE",
  "model": "flux-dev",
  "created": 1718312400,
  "queued_at": "2026-06-13T12:00:00Z",
  "poll_url": "/v1/jobs/42",
  "queued_reason": "requested"
}
```

`queued_reason` is `requested`, `at_capacity`, or `no_provider`. Poll `poll_url` until the status is terminal — see [Async jobs](/docs/api/jobs). Pass an `Idempotency-Key` header to deduplicate retried submissions.

## Media delivery

Endpoints that return raw media bytes — `/audio/speech`, `/audio/enhance`, `/music/generations`, `/videos/generations`, `/voice/generations` — accept `delivery`:

- `"bytes"` (default) — the raw file, as OpenAI does. Headers name the stored copy: `X-Inference-Request-Id`, `X-Asset-Id`, `X-Asset-Url`.
- `"url"` — JSON instead of bytes:

```json
{
  "object": "inference.result",
  "id": "8812",
  "public_id": "kQ3v9xZp1aE",
  "inference_type": "TTS",
  "model": "magpie-tts",
  "status": "PROCESSED",
  "created": 1780266332,
  "data": [{ "id": 551, "kind": "audio", "url": "https://…", "content_type": "audio/wav", "duration_seconds": 2.4 }]
}
```

For JSON bodies send `delivery` as a field; for multipart (`/audio/enhance`) send it as a form field. Every output is stored either way, so it shows up in your dashboard and can be shared.

## Capacity

Every provider service declares how many requests it can run at once (`max_concurrent`, default **1**), and services sharing a GPU can share one budget through a resource group (see [Providers → Capacity](/docs/providers/kubernetes-agent#capacity)). That budget is enforced across **every** path — sync `/v1` calls, async jobs, workflow steps, playground agent tools, and retries — so a device never receives more concurrent requests than its operator declared.

- **Sync media request, device busy:** the server waits briefly (about 20 seconds) for a slot. If none frees up it returns `429 at_capacity` with `Retry-After`.
- **`async: "auto"`, device busy:** queued immediately (`202`, `queued_reason: "at_capacity"`). If jobs for that model are already waiting, an auto request joins the back of the line rather than jumping it.
- **Queued jobs** are dispatched as slots free up.
- **LLM chat** isn't gated on the sync path — LLM servers batch concurrent requests internally. Async LLM jobs still respect `max_concurrent`.

`GET /v1/capacity` shows the live picture for models you can reach:

```json
{
  "object": "list",
  "data": [
    { "model": "ltx-2", "service_type": "video", "provider": "home-rig",
      "in_flight": 1, "max_concurrent": 1, "queued": 3, "resource_group": "gpu0", "available": false }
  ]
}
```

## Limits

| Limit | Default |
|---|---|
| Inference requests per account | 60 / minute (guest accounts: 15 / minute) |
| `GET /v1/models` | 120 / minute |
| Chat: messages per request | 200 |
| Chat/completions: input characters | 100,000 |
| `max_tokens` | Clamped to 8,192 |
| Image / video prompt | 4,000 characters |
| Images per generation (`n`) | 4 |
| TTS / voice input, music prompt + lyrics | 5,000 characters |
| Audio upload (transcriptions, enhance) | 25 MB |
| Image upload (edits, 3D) | 25 MB; up to 10 images per edit |
| Batch size | 256 requests |
| Upstream timeout | 300 seconds per sync request |

Rate-limited responses carry `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers on every call, and `Retry-After` on a 429. Deployments can override these defaults.
