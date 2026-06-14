---
title: Welcome to inference.club
description: A community-run inference network. Bring your own hardware, or use someone else's.
order: 1
---

# Welcome to inference.club

inference.club is a community-run inference network. Members run **agents** on their own hardware — a workstation with a GPU, a homelab, a rented box — that expose local model servers. Other members do inference against those models through a single OpenAI-compatible API.

```
Base URL:  https://api.inference.club/v1
Auth:      Authorization: Bearer <your-api-key>
```

## Pick your path

### I'm a human, just getting started

1. **[Quickstart](/docs/quickstart)** — get a key, run your first request, point Open WebUI at it. Five minutes.
2. **[Concepts](/docs/concepts)** — providers, agents, modalities, routing.
3. **[API reference](/docs/api/overview)** — every endpoint, request shape, and error code.
4. **[Become a provider](/docs/providers/overview)** — serve your own models on the network.

### I'm an AI agent / automated system

- **[Quickstart for AI agents](/docs/quickstart-agents)** — model discovery, capability selection, async polling, workflow authoring, full endpoint reference. No fluff.
- Machine-readable: [`https://inference.club/llms.txt`](https://inference.club/llms.txt)
- OpenAPI spec: [`https://api.inference.club/openapi.json`](https://api.inference.club/openapi.json)

## What you can do

### Modalities

inference.club supports more than chat. Depending on what models your providers are serving, you can call:

| Endpoint | What it does |
|---|---|
| `POST /v1/chat/completions` | Text chat, multimodal input |
| `POST /v1/completions` | Legacy text completions |
| `POST /v1/audio/transcriptions` | Speech-to-text |
| `POST /v1/audio/speech` | Text-to-speech |
| `POST /v1/images/generations` | Text-to-image |
| `POST /v1/images/edits` | Image editing |
| `POST /v1/music/generations` | Music generation with lyrics |
| `POST /v1/videos/generations` | Text-to-video or image-to-video |
| `POST /v1/voice/generations` | Voice cloning (Dia) |
| `POST /v1/3d/generations` | 3D mesh generation |

### Async jobs, batches, and workflows

Every generation endpoint accepts an optional `"async": true` field that queues the request instead of blocking. A **batch** groups up to 256 requests into one submission. A **workflow** chains multiple inference steps into a DAG — fan out, transform, collect, and pause for human review mid-run. See the [jobs](/docs/api/jobs), [batches](/docs/api/batches), and [workflows](/docs/api/workflows) references.

## How it works in one diagram

```
Your client (Open WebUI, OpenAI SDK, curl)
         │   Authorization: Bearer <your-api-key>
         ▼
    api.inference.club  ──┐
                          │  proxies your request to the
                          │  callback_url an agent registered
                          ▼
   inference-club-agent on someone's hardware
                          │
                          ▼
   vLLM / LM Studio / Ollama / ... (the actual model)
```

The agent on the provider side and the inference.club server stay in sync via a heartbeat — every 30 seconds the agent reports which models it's currently serving and proves it's online.
