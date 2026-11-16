---
title: Async jobs
description: Queue inference requests with async true or "auto", then poll /v1/jobs for output_text and media.
category: API reference
order: 11
---

# Async jobs

Async-capable endpoints accept an `async` field. With `true` the request is always queued as a **job**; with `"auto"` it runs immediately when a GPU slot is free and is queued only when the device is busy (or its provider is briefly offline). A queued request returns `202 Accepted` with a job envelope instead of the result.

```bash
curl https://api.inference.club/v1/images/generations \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 5d1c0e6a-poster-v1" \
  -d '{
    "model": "flux-dev",
    "prompt": "a lighthouse at dusk",
    "async": "auto"
  }'
```

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
  "queued_reason": "at_capacity"
}
```

| `queued_reason` | Why you got a job |
|---|---|
| `requested` | You sent `async: true`. |
| `at_capacity` | `async: "auto"` and every slot on the device was busy. |
| `no_provider` | `async: "auto"` and the model's provider was momentarily offline. The job waits up to an hour for it to come back, then fails. |

The `async` flag is stripped from the body before it reaches a provider. With `"auto"`, a request that found a free slot returns the endpoint's normal sync response (`200`) — handle both.

## Supported endpoints

`chat/completions`, `completions`, `images/generations`, `videos/generations`, `music/generations`, `audio/speech`, and `scrape`.

Multipart endpoints (`audio/transcriptions`, `audio/enhance`, `images/edits`, `3d/generations`) and `voice/generations` are synchronous only. Models from external providers (`provider:model` ids) always run inline.

## Job statuses

| Status | Meaning |
|---|---|
| `QUEUED` | Waiting for a free capacity slot on a provider (or for a retry backoff to elapse). |
| `PROCESSING` | A provider is running the job. |
| `PROCESSED` | Finished successfully. `output_text` / `media` are populated. |
| `FAILED` | Failed permanently — a non-retryable upstream rejection, or all attempts used up. |
| `CANCELED` | Canceled before it ran. |

Transient failures (connection errors, 5xx, timeouts, upstream 429) are retried automatically with backoff, up to `max_attempts` (3). A deterministic upstream 4xx fails immediately.

## Polling

Poll `GET /v1/jobs/<id>` (the envelope's `poll_url`) with backoff — start around 3 seconds and grow to ~15 seconds. Video can take minutes; don't poll faster than every few seconds.

## `GET /v1/jobs/<id>`

A job's current status, result, and media. Owner only.

```bash
curl https://api.inference.club/v1/jobs/42 \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

```json
{
  "id": 42,
  "public_id": "Hn2pX7wQe0c",
  "inference_type": "IMAGE",
  "status": "PROCESSED",
  "model_name": "flux-dev",
  "latency_ms": 8120,
  "image_urls": ["https://…/image.png"],
  "output_text": null,
  "media": [
    { "id": 99, "kind": "image", "url": "https://…/image.png", "content_type": "image/png", "duration_seconds": null }
  ],
  "is_async": true,
  "queued_at": "2026-06-13T12:00:00Z",
  "started_at": "2026-06-13T12:00:04Z",
  "finished_at": "2026-06-13T12:00:12Z",
  "attempts": 1,
  "max_attempts": 3,
  "error": null,
  "batch_id": null,
  "step_run_id": null
}
```

The fields to read:

| Field | Contents |
|---|---|
| `status` | See [Job statuses](#job-statuses). |
| `output_text` | The full text result — the LLM response, a transcript, or scraped markdown. `null` until `PROCESSED` and for media jobs. |
| `media` | Every output asset: `[{id, kind, url, content_type, duration_seconds}]`, `kind` ∈ `image`, `audio`, `video`, `model`, `document`. Empty until `PROCESSED`. |
| `error` | `{message, kind, attempt}` when the last attempt failed, else `null`. |

The job also carries the per-modality convenience fields used by the dashboard — `image_urls`, `video_url`, `output_audio_url` (generated audio), `model_url` (3D), and `audio_url` (the *input* audio of a transcription) — plus `response_preview`, which is truncated; prefer `output_text` and `media`.

Note that the envelope's `id` is a string while the job object's `id` is an integer; both address the same job. `GET /v1/jobs/<id>` also works for a synchronous request's id (the `X-Inference-Request-Id` header on byte responses, or `id` in a `delivery: "url"` result).

Non-public media URLs are owner-gated on `api.inference.club`; include your `Authorization` header when downloading them.

## `GET /v1/jobs`

Your async jobs, newest first. Each item has the same shape as the detail endpoint.

| Query parameter | Description |
|---|---|
| `status` | Filter by status (e.g. `QUEUED`, `FAILED`). |
| `active=1` | Only `QUEUED` or `PROCESSING` jobs. |
| `limit` | Max results, default 50. |

```json
{ "data": [ { "id": 42, "status": "PROCESSED", "inference_type": "IMAGE", "media": [ … ] } ] }
```

## `POST /v1/jobs/<id>/cancel`

```bash
curl -X POST https://api.inference.club/v1/jobs/42/cancel \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

```json
{ "id": "42", "status": "CANCELED", "canceled": true }
```

A `QUEUED` job is canceled immediately. A `PROCESSING` job can't be interrupted mid-generation: it's flagged (`canceled: true`, `status` still `PROCESSING`), finishes its current attempt, and isn't retried. A finished job is left alone (`canceled: false`).

## `POST /v1/jobs/<id>/retry`

Re-queue a `FAILED` or `CANCELED` job with the same payload and a fresh attempt counter. Returns the job envelope (`202`), or `409` with `type: "conflict"` for any other status.

## Idempotency

Send an `Idempotency-Key: <unique string>` header on submission. If a job already exists for your account with that key, you get that job back instead of a new one — so a client retry after a dropped connection never enqueues the same work twice. Reuse the key only for the *same* logical request.

## Errors

| `type` | When | HTTP |
|---|---|---|
| `not_found` | No job with that id | 404 |
| `forbidden` | The job belongs to someone else | 403 |
| `conflict` | Retry on a job that isn't `FAILED`/`CANCELED` | 409 |
| `async_disabled` | This deployment has no job queue (no broker) | 503 |

If async is not enabled, async submissions return `503 async_disabled` — drop the `async` field and call synchronously. The dashboard's queue summary (`GET /api/inference/queue/summary`) exposes `async_enabled` and a `worker_stalled` flag (jobs queued but the dispatcher hasn't ticked in 60 seconds).

## Dashboard

Live job state is visible at **Dashboard → Queue**, which also renders each workflow run as an SVG DAG.
