---
title: Batches
description: Submit up to 256 inference requests in one atomic batch with /v1/batches.
category: API reference
order: 12
---

# Batches

A batch lets you submit up to **256 async inference requests** in a single API call. All items are validated up front — if any item is malformed, the entire batch is rejected before anything is created. Once accepted, each item becomes an independent async job that runs as providers have capacity.

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

**Response:** `202 Accepted`

```json
{
  "id": "7",
  "label": "Q2 product shots",
  "status": "PENDING",
  "total": 3,
  "queued": 3,
  "processing": 0,
  "processed": 0,
  "failed": 0,
  "created": 1718312400
}
```

### Request body

| Field | Type | Notes |
|---|---|---|
| `requests` | array | **Required.** 1–256 items. |
| `requests[].endpoint` | string | **Required.** One of the supported endpoints (see below). |
| `requests[].body` | object | **Required.** The inference body for that endpoint (same shape as a direct call, minus `async`). |
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

File-upload endpoints are not batch-submittable.

## `GET /v1/batches`

List your batches, newest first (up to 50).

```bash
curl https://api.inference.club/v1/batches \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

## `GET /v1/batches/<id>`

Get batch status, per-status job counts, and a link to each job.

```bash
curl https://api.inference.club/v1/batches/7 \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

```json
{
  "id": "7",
  "label": "Q2 product shots",
  "status": "PROCESSING",
  "total": 3,
  "queued": 0,
  "processing": 1,
  "processed": 2,
  "failed": 0,
  "jobs": [
    { "id": "43", "status": "PROCESSED", "inference_type": "IMAGE" },
    { "id": "44", "status": "PROCESSING", "inference_type": "IMAGE" },
    { "id": "45", "status": "PROCESSED", "inference_type": "LLM" }
  ]
}
```

Batch `status` reflects the aggregate:

| Batch status | Meaning |
|---|---|
| `PENDING` | All jobs still queued. |
| `PROCESSING` | At least one job is running or queued. |
| `DONE` | All jobs have finished (some may have failed). |

## Cancel a batch

`POST /v1/batches/<id>/cancel` cancels every `QUEUED` or `PROCESSING` job in the batch.

```bash
curl -X POST https://api.inference.club/v1/batches/7/cancel \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

Returns the updated batch object.

## Individual jobs

Each item in a batch is a regular async job accessible via [`GET /v1/jobs/<id>`](/docs/api/jobs). Results (including media URLs) are on the individual job objects, not the batch.

## Errors

| `type` | When | HTTP |
|---|---|---|
| `invalid_request` | `requests` is missing, empty, or an item is malformed | 400 |
| `too_large` | More than 256 items | 400 |
| `async_disabled` | Async processing is not enabled on this server | 503 |
