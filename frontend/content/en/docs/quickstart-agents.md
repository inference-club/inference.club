---
title: Quickstart for AI agents
description: Everything an AI agent or automated system needs to call inference.club — model discovery, routing, error handling, async, and workflows.
category: Getting started
order: 3
---

# Quickstart for AI agents

This page is written for **AI agents and automated systems** that call inference.club programmatically — not for humans clicking through a dashboard. Skip anything that isn't API-relevant.

If you're a human developer: see [Quickstart](/docs/quickstart).

---

## Credentials

```
Base URL:  https://api.inference.club/v1
Auth:      Authorization: Bearer <api-key>
```

One API key covers all modalities and all directions (inference + provider heartbeats). Get one at `https://inference.club/dashboard/settings/token`.

---

## Step 1: discover available models

Before making any inference call, list what's reachable. Models are per-user — you only see models served by providers on your account (or shared providers your account can access).

```bash
curl https://api.inference.club/v1/models \
  -H "Authorization: Bearer $KEY"
```

Each entry includes capability fields beyond the OpenAI baseline:

```json
{
  "id": "qwen3-8b",
  "object": "model",
  "owned_by": "home-rig",
  "service_type": "llm",
  "input_modalities": ["text"],
  "output_modalities": ["text"],
  "supported_features": ["streaming"],
  "context_length": 32768
}
```

### Select a model by task

Use `service_type` to match a model to the task you want to run:

| `service_type` | Use for | Endpoint |
|---|---|---|
| `llm` | Text generation, reasoning, JSON extraction | `/v1/chat/completions` |
| `stt` | Transcription, audio understanding | `/v1/audio/transcriptions` |
| `tts` | Speech synthesis | `/v1/audio/speech` |
| `image` | Image generation, editing | `/v1/images/generations` |
| `music` | Music generation | `/v1/music/generations` |
| `video` | Video generation | `/v1/videos/generations` |
| `mesh` | 3D generation | `/v1/3d/generations` |
| `audio-enhance` | Denoise / clean speech audio | `/v1/audio/enhance` |
| `scrape` | URL → clean markdown | `/v1/scrape` |

Check `supported_features` for capability-gated behaviors:

| Feature | Meaning |
|---|---|
| `streaming` | Model supports `stream: true` on chat/completions |
| `timestamps` | STT model returns word/segment timings with `verbose_json` |
| `voice-cloning` | TTS model supports `/v1/voice/generations` with audio prompt cloning |
| `tool-use` | LLM supports tool/function calling |
| `vision` | LLM accepts image inputs in messages |

---

## Step 2: make a request

Requests are identical to OpenAI. Swap the base URL and key — nothing else changes.

### Chat (LLM)

```python
from openai import OpenAI

client = OpenAI(base_url="https://api.inference.club/v1", api_key=KEY)

resp = client.chat.completions.create(
    model="qwen3-8b",
    messages=[{"role": "user", "content": "Summarize this in one sentence: ..."}],
)
text = resp.choices[0].message.content
```

### Image generation

```python
img = client.images.generate(model="flux-dev", prompt="a glowing crystal cave")
url = img.data[0].url
```

### Speech-to-text

```python
with open("audio.wav", "rb") as f:
    result = client.audio.transcriptions.create(model="qwen3-asr", file=f)
text = result.text
```

### Text-to-speech

```python
with client.audio.speech.with_streaming_response.create(
    model="kokoro", input="Hello world", voice="af_heart"
) as r:
    r.stream_to_file("out.wav")
```

---

## Step 3: handle errors

All errors use OpenAI's envelope shape:

```json
{ "error": { "message": "...", "type": "no_provider" } }
```

| HTTP | `type` | What to do |
|---|---|---|
| 404 | `no_provider` | No online provider serves that model. Check `/v1/models` and pick a different one, or wait and retry. |
| 502 | `upstream_error` | The provider's local server failed. Retry with backoff; or pick a different model. |
| 401 | — | Invalid or missing API key. |
| 429 | — | Rate limited. Back off. |
| 503 | `async_disabled` | Async is not enabled on this server. Fall back to synchronous. |

**Retry pattern for `no_provider`:**
```python
import time

for attempt in range(3):
    resp = requests.post(url, json=body, headers=auth)
    if resp.status_code == 404 and resp.json().get("error", {}).get("type") == "no_provider":
        time.sleep(5 * (attempt + 1))
        continue
    break
```

---

## Step 4: async for long-running work

Add `"async": true` to any JSON-bodied request to get a `202` with a job id instead of waiting:

```python
import requests, time

resp = requests.post(
    "https://api.inference.club/v1/videos/generations",
    headers={"Authorization": f"Bearer {KEY}"},
    json={"model": "ltx-2", "prompt": "a timelapse sunrise", "async": True},
)
job_id = resp.json()["id"]

# Poll until done
while True:
    job = requests.get(
        f"https://api.inference.club/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {KEY}"},
    ).json()
    if job["status"] in ("PROCESSED", "FAILED", "CANCELED"):
        break
    time.sleep(3)

print(job.get("result_url"))
```

Use idempotency keys to deduplicate retries:

```python
headers = {
    "Authorization": f"Bearer {KEY}",
    "Idempotency-Key": "my-unique-request-id-abc123",
}
```

Supported async modalities: `chat/completions`, `completions`, `images/generations`, `videos/generations`, `music/generations`, `audio/speech`.

---

## Step 5: workflows (multi-step pipelines)

Workflows let an agent define a DAG of inference steps — fan out, transform data, chain modalities. Start from a curated template or write an inline spec.

### Use a template

```python
resp = requests.post(
    "https://api.inference.club/v1/workflows/runs",
    headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    json={
        "template": "illustrated-story",
        "inputs": {
            "topic": "a robot learning to paint",
            "scenes": 3,
            "style": "oil painting, warm light",
        },
    },
)
run_id = resp.json()["id"]
```

### Write an inline spec

```python
spec = {
    "steps": [
        {
            "id": "plan",
            "kind": "inference",
            "type": "chat",          # modality: llm
            "extract": "json",        # parse LLM output as JSON
            "title": "Plan sections",
            "body": {
                "messages": [{
                    "role": "user",
                    "content": (
                        "List 4 blog section titles about {{inputs.topic}}. "
                        "Return JSON: {\"titles\":[\"...\"]}"
                    ),
                }],
            },
        },
        {
            "id": "images",
            "kind": "map",            # fan-out: one job per item
            "type": "image",
            "title": "Illustrate each section",
            "over": "{{steps.plan.output.titles}}",
            "body": {"prompt": "Blog illustration for: {{item}}"},
        },
    ]
}

resp = requests.post(
    "https://api.inference.club/v1/workflows/runs",
    headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    json={"spec": spec, "inputs": {"topic": "distributed AI"}},
)
run_id = resp.json()["id"]
```

### Poll a workflow run

```python
while True:
    run = requests.get(
        f"https://api.inference.club/v1/workflows/runs/{run_id}",
        headers={"Authorization": f"Bearer {KEY}"},
    ).json()
    if run["status"] in ("DONE", "FAILED", "CANCELED"):
        break
    if run["status"] == "AWAITING":
        # A gate step is waiting for human approval — handle in your UI
        break
    time.sleep(5)

# Collect outputs
for step in run["steps"]:
    if step["status"] == "DONE":
        print(step["step_id"], step.get("output"))
```

### Available templates

List with `GET /v1/workflows/templates`. Current templates:

| `key` | What it does | Required inputs |
|---|---|---|
| `illustrated-story` | Write story → split into scenes → illustrate each (gate) | `topic`, `scenes`, `style` |
| `image-variations` | Brainstorm N prompts → render them all | `subject`, `count`, `vibe` |
| `storyboard-to-video` | Plan shots → first frames (gate) → animate to video | `concept`, `shots` |
| `song-and-cover` | Write lyrics+brief → track + cover art in parallel | `theme`, `genre` |
| `narrated-explainer` | Write script → TTS narrate each line | `topic`, `lines` |

---

## Reference

### Full endpoint table

| Method | Path | Notes |
|---|---|---|
| `GET` | `/v1/models` | List available models + capabilities |
| `POST` | `/v1/chat/completions` | LLM chat. Supports `stream: true`, `async: true`. |
| `POST` | `/v1/completions` | Legacy completion. Supports `async: true`. |
| `POST` | `/v1/audio/transcriptions` | STT. `multipart/form-data`. Synchronous only. |
| `POST` | `/v1/audio/speech` | TTS. Returns raw audio bytes. Supports `async: true`. |
| `GET` | `/v1/audio/voices` | `?model=<id>` — list voices for a TTS model |
| `POST` | `/v1/images/generations` | Text-to-image. Supports `async: true`. |
| `POST` | `/v1/images/edits` | Image edit. `multipart/form-data`. Synchronous only. |
| `POST` | `/v1/music/generations` | Music gen. Returns raw audio bytes. Supports `async: true`. |
| `POST` | `/v1/videos/generations` | Video gen. Returns raw MP4. Supports `async: true`. |
| `POST` | `/v1/voice/generations` | Dia voice cloning. Synchronous only. |
| `POST` | `/v1/3d/generations` | 3D mesh gen. |
| `POST` | `/v1/audio/enhance` | Denoise / clean audio. `multipart/form-data`. Synchronous only. |
| `POST` | `/v1/scrape` | URL → clean markdown. |
| `GET` | `/v1/jobs` | List async jobs (`?status=`, `?active=1`, `?limit=`) |
| `GET` | `/v1/jobs/<id>` | Job status + result |
| `POST` | `/v1/jobs/<id>/cancel` | Cancel a queued/processing job |
| `POST` | `/v1/jobs/<id>/retry` | Re-queue a failed/canceled job |
| `POST` | `/v1/batches` | Submit up to 256 requests as one batch |
| `GET` | `/v1/batches` | List batches |
| `GET` | `/v1/batches/<id>` | Batch status |
| `POST` | `/v1/batches/<id>/cancel` | Cancel all jobs in a batch |
| `GET` | `/v1/workflows/templates` | List curated templates |
| `POST` | `/v1/workflows/runs` | Start a workflow run |
| `GET` | `/v1/workflows/runs` | List runs |
| `GET` | `/v1/workflows/runs/<id>` | Run state + step outputs |
| `POST` | `/v1/workflows/runs/<id>/steps/<step_id>/approve` | Approve a gate step |
| `POST` | `/v1/workflows/runs/<id>/steps/<step_id>/reject` | Reject a gate step |

### Sharing fields

Any JSON-bodied inference call accepts these extra fields (stripped before reaching a provider):

```json
{ "visibility": "PUBLIC", "collection": "my-album" }
```

Visibility values: `PUBLIC`, `UNLISTED` (default), `PRIVATE`, `SECRET`.

### Voice cloning request shape

```json
{
  "input": "[S1] Hello!\n[S2] Hey there.",
  "speakers": { "S1": 12, "S2": 17 },
  "cfg_scale": 3.0,
  "temperature": 1.8,
  "seed": 42
}
```

Speaker IDs come from `GET /api/inference/voice-samples/` (your voice library).
