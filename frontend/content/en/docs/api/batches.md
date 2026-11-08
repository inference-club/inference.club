---
title: Batches
description: Submit up to 256 inference requests in one atomic batch with /v1/batches.
category: API reference
order: 12
---

# Batches

A batch lets you submit up to **256 async inference requests** in a single API call. All items are validated up front — if any item is malformed, the entire batch is rejected before anything is created. Once accepted, each item becomes an independent async job that runs as providers have capacity — batch jobs share the same per-device [capacity budget](/docs/services/direct-vs-async#capacity) as everything else, so a 256-image batch on a single-slot GPU runs one image at a time.

## `POST /v1/batches`

```bash
curl -X POST https://api.inference.club/v1/batches \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "label": "Q2 product shots",
    "requests": [
      {
        "endpoint": "/v1/images/generations",
        "body": { "model": "flux-dev", "prompt": "a minimalist desk lamp" }
      },
      {
        "endpoint": "/v1/images/generations",
        "body": { "model": "flux-dev", "prompt": "a wooden bookshelf with plants" }
      },
      {
        "endpoint": "/v1/chat/completions",
        "body": {
          "model": "qwen3-8b",
          "messages": [{ "role": "user", "content": "Write a product description for a lamp." }]
        }
      }
    ]
  }'
```

**Response:** `202 Accepted` with the batch object (shape below).

### Request body

| Field | Type | Notes |
|---|---|---|
| `requests` | array | **Required.** 1–256 items. |
| `requests[].endpoint` | string | **Required.** One of the supported endpoints (see below). |
| `requests[].body` | object | **Required.** The inference body for that endpoint (same shape as a direct call; any `async` field is ignored). |
| `label` | string | Optional. A human-readable name for the batch. |

### Supported endpoints

| Endpoint | Inference type |
|---|---|
| `/v1/chat/completions` | LLM |
| `/v1/completions` | LLM |
| `/v1/images/generations` | IMAGE |
| `/v1/videos/generations` | VIDEO |
| `/v1/music/generations` | MUSIC |
| `/v1/audio/speech` | TTS |

File-upload endpoints, `/v1/voice/generations`, and `/v1/scrape` are not batch-submittable.

## `GET /v1/batches`

List your batches, newest first (up to 50).

```bash
curl https://api.inference.club/v1/batches \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

## `GET /v1/batches/<id>`

Batch status, per-status job counts, and every job (each in the full [job shape](/docs/api/jobs), including `output_text` and `media`).

```bash
curl https://api.inference.club/v1/batches/7 \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

```json
{
  "id": 7,
  "label": "Q2 product shots",
  "status": "RUNNING",
  "counts": { "PROCESSED": 2, "PROCESSING": 1 },
  "created_on": "2026-06-13T12:00:00Z",
  "jobs": [
    { "id": 43, "status": "PROCESSED", "inference_type": "IMAGE", "media": [ … ] },
    { "id": 44, "status": "PROCESSING", "inference_type": "IMAGE", "media": [] },
    { "id": 45, "status": "PROCESSED", "inference_type": "LLM", "output_text": "…" }
  ]
}
```

Batch `status` is rolled up from its jobs:

| Batch status | Meaning |
|---|---|
| `RUNNING` | At least one job is still `QUEUED` or `PROCESSING`. |
| `DONE` | Every job `PROCESSED`. |
| `PARTIAL` | All jobs finished; some succeeded, some failed or were canceled. |
| `FAILED` | All jobs finished and none succeeded. |
| `EMPTY` | The batch has no jobs. |

Poll it like a job (3s → 15s backoff) until the status is no longer `RUNNING`.

## Cancel a batch

`POST /v1/batches/<id>` (the same path, no suffix) cancels every `QUEUED` or `PROCESSING` job in the batch and returns the updated batch object.

```bash
curl -X POST https://api.inference.club/v1/batches/7 \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

## Individual jobs

Each item in a batch is a regular async job accessible via [`GET /v1/jobs/<id>`](/docs/api/jobs). Results (including media URLs) are on the individual job objects, not the batch.

## Errors

| `type` | When | HTTP |
|---|---|---|
| `invalid_request` | `requests` is missing, empty, or an item is malformed | 400 |
| `too_large` | More than 256 items | 400 |
| `async_disabled` | Async processing is not enabled on this server | 503 |
