---
title: Async jobs
description: Queue inference requests and poll for results with /v1/jobs.
category: API reference
order: 11
---

# Async jobs

Any JSON-bodied inference endpoint accepts an `"async": true` field. When present, the request is queued as a **job** rather than blocking until the upstream provider finishes. The response is `202 Accepted` with a job envelope.

```bash
curl https://api.inference.club/v1/images/generations \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "flux-dev",
    "prompt": "a lighthouse at dusk",
    "async": true
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
  "queued_at": "2026-06-13T12:00:00Z"
}
```

The `async` flag is stripped from the body before it reaches a provider — the provider never sees it.

## Supported modalities

The async path supports: `chat/completions`, `completions`, `images/generations`, `videos/generations`, `music/generations`, and `audio/speech`.

File-upload endpoints (`audio/transcriptions`, `images/edits`, `voice/generations`) are synchronous only.

## Job statuses

| Status | Meaning |
|---|---|
| `QUEUED` | Waiting for a free capacity slot on a provider. |
| `PROCESSING` | A provider has claimed and is running the job. |
| `PROCESSED` | Finished successfully. Result is available. |
| `FAILED` | The job failed (provider error, no provider, or max retries exhausted). |
| `CANCELED` | Canceled by the caller before it completed. |

## `GET /v1/jobs`

List your async jobs, newest first.

```bash
curl https://api.inference.club/v1/jobs \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

**Query parameters:**

| Parameter | Description |
|---|---|
| `status` | Filter by status (e.g. `QUEUED`, `FAILED`). |
| `active=1` | Only return `QUEUED` or `PROCESSING` jobs. |
| `limit` | Max results, default 50. |

**Response:**

```json
{
  "data": [
    {
      "id": "42",
      "object": "inference.job",
      "status": "PROCESSED",
      "inference_type": "IMAGE",
      "model": "flux-dev",
      "created": 1718312400,
      "result_url": "https://api.inference.club/api/inference/assets/99/"
    }
  ]
}
```

## `GET /v1/jobs/<id>`

Get a single job's current status, result, and any media assets.

```bash
curl https://api.inference.club/v1/jobs/42 \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

A completed image job returns a `result_url`; a completed LLM job returns the `choices` array inside `result`.

## `POST /v1/jobs/<id>/cancel`

Cancel a `QUEUED` or `PROCESSING` job. Has no effect if the job has already completed.

```bash
curl -X POST https://api.inference.club/v1/jobs/42/cancel \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

```json
{ "id": "42", "status": "CANCELED", "canceled": true }
```

## `POST /v1/jobs/<id>/retry`

Re-queue a `FAILED` or `CANCELED` job with the same payload. The job goes back to `QUEUED` and gets a fresh attempt.

```bash
curl -X POST https://api.inference.club/v1/jobs/42/retry \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

Returns the updated job envelope (`202 Accepted`) or `409 Conflict` if the job is in a non-retryable state.

## Idempotency

Pass an `Idempotency-Key: <uuid>` header when submitting a job to deduplicate retries from your client. A second submission with the same key returns the existing job instead of creating a new one.

## Dashboard

Live job state is visible at **Dashboard → Queue**. The queue page shows a summary badge for active work and renders each workflow run as an SVG DAG.

## Worker availability

If async is not enabled on the server, all async endpoints return `503 Service Unavailable` with `"type": "async_disabled"`. The queue summary endpoint (`GET /api/inference/queue/summary`) exposes an `async_enabled` flag and a `worker_stalled` indicator — if jobs are queued but the dispatcher hasn't ticked in the last 60 seconds, the frontend shows a warning.
