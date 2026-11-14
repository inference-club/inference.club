---
title: Quickstart for AI agents
description: The recommended call pattern for AI agents and automated systems — discover models, submit with async:"auto", poll, read media URLs, and respect GPU capacity.
category: Getting started
order: 3
---

# Quickstart for AI agents

This page is written for **AI agents and automated systems** that call inference.club programmatically. It describes one call pattern that works for every modality and degrades gracefully when GPUs are busy or a provider blips offline. If you're a human developer, start with the [Quickstart](/docs/quickstart). If you're wiring inference.club into an agent framework, see [Agent integrations](/docs/agents/overview).

```
Base URL:  https://api.inference.club/v1
Auth:      Authorization: Bearer <api-key>
OpenAPI:   https://api.inference.club/openapi.json
```

One API key covers every modality. Get one at `https://inference.club/dashboard/settings/token`.

::callout{type="warning" title="These are real, single-GPU devices"}
Models run on members' own hardware. Most media services accept **one request at a time** per device. Don't fan out dozens of parallel requests — keep **at most 2 media requests in flight per model** and let the queue do the rest.
::

---

## The pattern

1. `GET /v1/models` → pick a model by `service_type`.
2. `POST` the request with `"async": "auto"` and (for audio/video endpoints) `"delivery": "url"`.
3. **200** → you have the result. **202** → it was queued; poll `poll_url` with backoff (3s → 15s).
4. Read `output_text` (text results) or `media[].url` (media) from the finished job.
5. On **429 `at_capacity`**, wait `Retry-After` seconds and resubmit. Send an `Idempotency-Key` so retries never double-queue.

### 1. Discover models

```bash
curl https://api.inference.club/v1/models -H "Authorization: Bearer $KEY"
```

```json
{
  "object": "list",
  "data": [{
    "id": "qwen3-8b",
    "object": "model",
    "owned_by": "home-rig",
    "service_type": "llm",
    "input_modalities": ["text"],
    "output_modalities": ["text"],
    "supported_features": ["streaming", "tools"],
    "context_length": 32768
  }]
}
```

The list contains every model you can reach right now: your own nodes plus other members' services shared with you. Only models with an online provider appear, so re-list rather than caching ids for long.

| `service_type` | Endpoint | Body | Sync response |
|---|---|---|---|
| `llm` | `POST /v1/chat/completions`, `/v1/completions` | JSON | JSON (or SSE with `stream: true`) |
| `image` | `POST /v1/images/generations` | JSON | JSON `data[].url` |
| `image` | `POST /v1/images/edits` | multipart | JSON `data[].url` |
| `tts` | `POST /v1/audio/speech` | JSON | audio bytes, or JSON with `delivery: "url"` |
| `tts` + `voice-cloning` feature | `POST /v1/voice/generations` | JSON | audio bytes, or JSON with `delivery: "url"` |
| `music` | `POST /v1/music/generations` | JSON | audio bytes, or JSON with `delivery: "url"` |
| `video` | `POST /v1/videos/generations` | JSON | MP4 bytes, or JSON with `delivery: "url"` |
| `stt` | `POST /v1/audio/transcriptions` | multipart | JSON `text` |
| `audio-enhance` | `POST /v1/audio/enhance` | multipart | audio bytes, or JSON with `delivery: "url"` |
| `mesh` | `POST /v1/3d/generations` | multipart (`image`) | JSON `data[].url` (GLB) |
| `scrape` | `POST /v1/scrape` | JSON `{model, url}` | JSON `markdown` |

`supported_features` gates optional behavior: `streaming`, `tools`, `timestamps` (STT word/segment timings), `voice-cloning`, and the image knobs (`seed`, `steps`, `negative-prompt`, `transparent-background`, `custom-size`, `image-edit`, `multi-reference`). Features are declared by the operator; unknown fields are ignored by models that don't support them.

### 2. Submit with `async: "auto"`

`async` takes three values:

| Value | Behavior |
|---|---|
| omitted / `false` | **Sync.** Run now and wait. Media requests that find the device busy wait up to ~20s for a slot, then return `429 at_capacity`. |
| `true` | **Always queue.** Returns `202` with a job immediately. |
| `"auto"` | **Recommended.** Run now if a GPU slot is free (normal `200`); otherwise queue it and return `202`. Also queues — instead of `404` — when the model is known but its provider is momentarily offline (the job waits up to an hour for it to return). |

`async` works on `chat/completions`, `completions`, `images/generations`, `videos/generations`, `music/generations`, `audio/speech`, and `scrape`. Multipart endpoints (`audio/transcriptions`, `audio/enhance`, `images/edits`, `3d/generations`) and `voice/generations` are sync-only.

```python
import time, uuid, requests

BASE = "https://api.inference.club/v1"
H = {"Authorization": f"Bearer {KEY}"}

def submit(path, body):
    headers = {**H, "Idempotency-Key": str(uuid.uuid4())}   # reuse the same key on retries
    for _ in range(5):
        r = requests.post(f"{BASE}{path}", headers=headers, timeout=330,
                          json={**body, "async": "auto", "delivery": "url"})
        if r.status_code == 429 and r.json().get("error", {}).get("type") == "at_capacity":
            time.sleep(int(r.headers.get("Retry-After", 15)))
            continue
        r.raise_for_status()
        return r
    raise RuntimeError("device stayed busy")

r = submit("/videos/generations", {"model": "ltx-2", "prompt": "a paper boat in the rain"})
```

`delivery: "url"` only matters on endpoints that would otherwise return raw bytes (`audio/speech`, `audio/enhance`, `music/generations`, `videos/generations`, `voice/generations`); other endpoints ignore it.

### 3. Handle 200 vs 202

**200** — the request ran inline. With `delivery: "url"` a media endpoint returns:

```json
{
  "object": "inference.result",
  "id": "8812",
  "public_id": "kQ3v9xZp1aE",
  "inference_type": "VIDEO",
  "model": "ltx-2",
  "status": "PROCESSED",
  "created": 1780266332,
  "data": [
    { "id": 551, "kind": "video", "url": "https://…/video.mp4", "content_type": "video/mp4", "duration_seconds": 6.0 }
  ]
}
```

Chat returns the normal OpenAI `chat.completion`; images return `{"data": [{"url": …}]}`; scrape returns `{"markdown": …}`.

**202** — it was queued. The body is a job envelope:

```json
{
  "id": "8813",
  "object": "inference.job",
  "status": "QUEUED",
  "inference_type": "VIDEO",
  "model": "ltx-2",
  "created": 1780266332,
  "queued_at": "2026-11-08T12:00:00Z",
  "poll_url": "/v1/jobs/8813",
  "queued_reason": "at_capacity"
}
```

`queued_reason` is `requested` (you sent `async: true`), `at_capacity` (auto, device busy), or `no_provider` (auto, provider briefly offline).

### 4. Poll and read the result

```python
def wait(job_id, timeout=3600):
    delay, deadline = 3, time.time() + timeout
    while time.time() < deadline:
        job = requests.get(f"{BASE}/jobs/{job_id}", headers=H, timeout=30).json()
        if job["status"] in ("PROCESSED", "FAILED", "CANCELED"):
            return job
        time.sleep(delay)
        delay = min(delay * 1.5, 15)          # 3s → 15s
    raise TimeoutError(job_id)

if r.status_code == 202:
    job = wait(r.json()["id"])
    if job["status"] != "PROCESSED":
        raise RuntimeError(job.get("error"))
    urls = [m["url"] for m in job["media"]]   # media jobs
    text = job.get("output_text")             # LLM / scrape jobs
else:
    urls = [m["url"] for m in r.json().get("data", [])]
```

A finished job carries:

- `output_text` — the full text result: the LLM response, a transcript, or scraped markdown. (`response_preview` is only a truncated preview.) `null` until the job is `PROCESSED`.
- `media` — `[{id, kind, url, content_type, duration_seconds}]` with `kind` one of `image`, `audio`, `video`, `model`, `document`. Empty until `PROCESSED`.
- `error` — `{message, kind, attempt}` when `FAILED`. Transient failures are retried automatically (up to 3 attempts with backoff) before a job fails.

Job statuses: `QUEUED` → `PROCESSING` → `PROCESSED` | `FAILED` | `CANCELED`.

Media URLs for public outputs point straight at object storage. Non-public outputs use an owner-gated URL on `api.inference.club` — send your `Authorization` header when downloading those.

### 5. Errors that matter

All `/v1` errors use the OpenAI envelope `{"error": {"message": "...", "type": "..."}}`.

| HTTP | `type` | What to do |
|---|---|---|
| 429 | `at_capacity` | The GPU is busy. Sleep `Retry-After` (also in `error.retry_after`), then resubmit — or use `async: "auto"` so it queues instead. |
| 429 | *(none — `{"detail": …}`)* | Your per-account **rate limit** (default 60 inference req/min). Sleep `Retry-After`. Different from `at_capacity`: slow down overall, not just on this model. |
| 404 | `no_provider` | No online provider serves that model for you. Re-list `/v1/models` and pick another, or use `async: "auto"` to wait for it. |
| 502 | `upstream_error` | The provider's model server failed. Retry with backoff, or pick another model. |
| 413 | `request_too_large` / `file_too_large` | Input over a limit (see [limits](/docs/api/overview#limits)). |
| 503 | `async_disabled` | This deployment has no job queue. Drop `async` and call synchronously. |
| 401 | *(`{"detail": …}`)* | Missing or invalid API key. |

### Concurrency etiquette

- Keep **≤ 2 media requests in flight per device**. More just waits in the queue (or gets 429s) and ties up your connections.
- LLM chat isn't capacity-gated on the sync path (LLM servers batch internally), so modest parallel chat is fine.
- [`GET /v1/capacity`](/docs/api/overview#capacity) shows live `in_flight` / `max_concurrent` / `queued` per model if you want to schedule around busy devices.
- Reuse one `Idempotency-Key` per logical request across retries: a resubmit that gets queued returns the existing job instead of creating a duplicate.

---

## Recipes

### Chat (OpenAI SDK)

The OpenAI SDK works unchanged. For quick interactive chat, plain sync is fine:

```python
from openai import OpenAI

client = OpenAI(base_url="https://api.inference.club/v1", api_key=KEY)
resp = client.chat.completions.create(
    model="qwen3-8b",
    messages=[{"role": "user", "content": "Summarize this in one sentence: ..."}],
)
text = resp.choices[0].message.content
```

### Text-to-speech as a URL

```python
r = submit("/audio/speech", {"model": "<tts-model>", "input": "Hello world"})
audio_url = (r.json()["data"][0]["url"] if r.status_code == 200
             else wait(r.json()["id"])["media"][0]["url"])
```

Without `delivery: "url"`, the response body is the raw audio and the stored copy is named by headers: `X-Inference-Request-Id`, `X-Asset-Id`, `X-Asset-Url`.

### Transcription (sync, multipart)

```python
with open("audio.wav", "rb") as f:
    text = client.audio.transcriptions.create(model="qwen3-asr", file=f).text
```

---

## Workflows (multi-step pipelines)

Workflows run a DAG of steps — fan out, transform, chain modalities — entirely in the job queue. Start from a template or post an inline spec. Every workflow is async: `POST` returns `202` with the run.

```python
run = requests.post(f"{BASE}/workflows/runs", headers=H, json={
    "template": "illustrated-story",
    "inputs": {"topic": "a robot learning to paint", "scenes": 3},
}).json()

while run["status"] in ("PENDING", "RUNNING"):
    time.sleep(5)
    run = requests.get(f"{BASE}/workflows/runs/{run['id']}", headers=H).json()

if run["status"] == "AWAITING":
    # a gate step is waiting: POST /v1/workflows/runs/<id>/steps/<step_id>/approve
    ...
for step in run["steps"]:
    print(step["step_id"], step["status"], step["output"])
```

Run statuses: `PENDING`, `RUNNING`, `AWAITING` (a gate needs approval), `DONE`, `FAILED`. Launch fails fast with `409 services_unavailable` (listing `missing` modalities) if you can't reach a provider for a step's modality.

| Template `key` | What it does | Inputs (required in **bold**) |
|---|---|---|
| `illustrated-story` | Story → scenes → illustrate each → review gate | **`topic`**, `scenes` (1–8), `style` |
| `image-variations` | Brainstorm N prompts → render them all | **`subject`**, `count` (1–8), `vibe` |
| `storyboard-to-video` | Plan shots → first frames → gate → animate | **`concept`**, `shots` (1–5), `size` |
| `miniature-construction-timelapse` | Art-direct a tilt-shift scene → frame → animate | **`subject`**, `size`, `seconds` (2–12) |
| `image-to-video` | Direct a shot → frame → animate | `subject`, `size`, `seconds` |
| `song-and-cover` | Lyrics + brief → track and cover art in parallel | **`theme`**, `genre` |
| `narrated-explainer` | Script → TTS each line | **`topic`**, `lines` (1–8) |
| `url-to-video` | Scrape → 2-host dialog → Dia voices → clean → illustrate → gate → compose | **`url`**, `style`, `voice_seed` |

`GET /v1/workflows/templates` returns the live list with full input schemas. For inline specs, step kinds, and templating, see the [workflows reference](/docs/api/workflows).

---

## Endpoint reference

| Method | Path | Notes |
|---|---|---|
| `GET` | `/v1/models` | Models you can reach + capabilities |
| `GET` | `/v1/capacity` | Live per-model slots: `in_flight`, `max_concurrent`, `queued`, `available` |
| `POST` | `/v1/chat/completions` | LLM chat. `stream`, `async` |
| `POST` | `/v1/completions` | Legacy completions. `stream`, `async` |
| `POST` | `/v1/images/generations` | JSON → image URLs. `async` |
| `POST` | `/v1/images/edits` | Multipart. Sync only |
| `POST` | `/v1/audio/speech` | Audio bytes / `delivery`. `async` |
| `GET` | `/v1/audio/voices?model=<id>` | Voices for a TTS model |
| `POST` | `/v1/voice/generations` | Dia voice cloning. Bytes / `delivery`. Sync only |
| `POST` | `/v1/music/generations` | Audio bytes / `delivery`. `async` |
| `POST` | `/v1/videos/generations` | MP4 bytes / `delivery`. `async` |
| `POST` | `/v1/audio/transcriptions` | Multipart. Sync only |
| `POST` | `/v1/audio/enhance` | Multipart. Bytes / `delivery`. Sync only |
| `POST` | `/v1/3d/generations` | Multipart image → GLB URL. Sync only |
| `POST` | `/v1/scrape` | URL → markdown. `async` |
| `GET` | `/v1/jobs` | Your async jobs (`?status=`, `?active=1`, `?limit=`) |
| `GET` | `/v1/jobs/<id>` | Job status, `output_text`, `media` |
| `POST` | `/v1/jobs/<id>/cancel` | Cancel a queued job |
| `POST` | `/v1/jobs/<id>/retry` | Re-queue a failed/canceled job |
| `POST` | `/v1/batches` | Up to 256 async requests at once |
| `GET` | `/v1/batches/<id>` | Batch status + its jobs |
| `POST` | `/v1/batches/<id>` | Cancel the batch's unfinished jobs |
| `GET` | `/v1/workflows/templates` | Curated templates + input schemas |
| `POST` | `/v1/workflows/runs` | Start a run (`template` or `spec`) |
| `GET` | `/v1/workflows/runs/<id>` | Run state, steps, outputs |
| `POST` | `/v1/workflows/runs/<id>/steps/<step_id>/approve` · `/reject` | Resolve a gate |

### Sharing fields

Every JSON generation body also accepts `visibility` (`PUBLIC`, `UNLISTED` — the default, `PRIVATE`, `SECRET`) and `collection` (a collection name to file the result into). Both are stripped before the request reaches a provider. See [Sharing](/docs/sharing).
