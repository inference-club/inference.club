---
title: Concepts
description: The model in your head — users, API keys, providers, agents, models.
order: 3
---

# Concepts

A small vocabulary; everything else is built on top of these.

## User

A person with an inference.club account. Sign-up is via GitHub OAuth. A user has zero or more API keys, zero or more providers, and a history of inference requests they've made.

A user can be a **consumer** (calls the API to do inference), a **provider** (runs an agent that serves models), or both. The same account and the same API key cover all three roles — there's no separate registration.

## API key

A bearer token that authenticates a request to inference.club. One key identifies one user. The key is used:

- by your **OpenAI client** when it calls `https://api.inference.club/v1/...` — `Authorization: Bearer <key>`
- by your **agent** when it heartbeats into inference.club to report which models it's serving

Both directions are the same key. Don't share it; rotate it from the dashboard if it leaks.

## Provider

A user-owned record on inference.club representing one agent. A provider has:

- a **name** (you pick it — `home-rig`, `office-3090`, etc.)
- a **callback URL** — where inference.club sends proxied requests (e.g. `http://192.168.5.173:8002/v1` on your LAN, or a public URL once you go to production)
- a **heartbeat timestamp** — last time the agent checked in
- a list of **models** the agent is currently advertising

Providers belong to one user. Inference.club only routes requests from a user to that user's own providers — your hardware serves your inferences.

## Agent

The actual program (`inference-club-agent`) running on the provider's hardware. The agent does two things:

1. **Heartbeats** to inference.club every 30 seconds with its current model list and a small health snapshot.
2. **Receives proxied requests** from inference.club at its callback URL, forwards them to the local LLM server (vLLM, LM Studio, Ollama, …), and streams the response back.

The agent is online from inference.club's perspective if a heartbeat arrived in the last 60 seconds. After that grace window, the provider is shown as offline and won't be selected for routing.

## Model

A name advertised by an agent — `qwen3-8b`, `llama-3.1-8b-instruct`, whatever the local LLM server calls it. inference.club doesn't validate model names; it just routes requests by exact match.

When you call `/v1/chat/completions` with `"model": "qwen3-8b"`, inference.club looks for an online provider belonging to you that has `qwen3-8b` in its model list, and proxies the request there. If multiple providers serve the same model, the first match wins (no load balancing yet).

## Service type (modality)

A model isn't always a chat model. Each service an agent exposes declares a **type** — what kind of inference it provides — alongside its engine:

| Type | Endpoints | Notes |
|---|---|---|
| `llm` (default) | `/v1/chat/completions`, `/v1/completions` | Text in, text out. |
| `stt` | `/v1/audio/transcriptions` | Audio in, text out. |
| `tts` | `/v1/audio/speech`, `/v1/voice/generations` | Text in, audio out. |
| `image` | `/v1/images/generations`, `/v1/images/edits` | Text (+ optional image) in, image out. |
| `music` | `/v1/music/generations` | Text + optional lyrics in, audio out. |
| `video` | `/v1/videos/generations` | Text (+ optional image) in, video out. |
| `mesh` | `/v1/3d/generations` | Text or image in, 3D mesh out. |

The type is set in the agent's manifest. Omit it and it defaults to `llm`:

```yaml
hosts:
  - id: rig-01
    services:
      - name: vllm-qwen          # LLM (default type)
        engine: vllm
        url: http://localhost:8000/v1
        models:
          - hf: Qwen/Qwen3-30B-A3B

      - name: asr-qwen           # speech-to-text
        type: stt
        engine: vllm
        url: http://localhost:8001/v1
        features: [timestamps]   # opt-in for word/segment timings
        models:
          - id: Qwen/Qwen3-ASR-1.7B

      - name: dia-tts            # voice-cloning TTS
        type: tts
        engine: dia
        url: http://localhost:7860/v1
        features: [voice-cloning]
        models:
          - id: nari-labs/Dia-1.6B
```

Routing respects the type: a transcription request only ever lands on an `stt` service, a chat request only on an `llm` service, and so on — even if two services share a model name.

## Voice cloning

When a `tts` service advertises the `voice-cloning` feature in its manifest, it unlocks the [`/v1/voice/generations`](/docs/api/voice-generations) endpoint. Callers supply a dialogue script using `[S1]`/`[S2]` speaker tags, optionally mapping each speaker to a **voice sample** (a short audio recording uploaded to their library). The engine transcodes the samples, assembles a cloning prompt, and forwards it to the Dia model running on the provider.

Voice samples are stored privately in your account (accessible at **Dashboard → Voice library**) and are never shared across users.

## Async jobs

Every JSON-bodied generation endpoint accepts an optional `"async": true` field. Adding it converts the request from a synchronous call into a queued **job** that returns immediately with a `202 Accepted` and a job envelope:

```json
{ "id": "42", "object": "inference.job", "status": "QUEUED", ... }
```

Poll `GET /v1/jobs/42` until `status` is `PROCESSED` or `FAILED`, then read `result_url` or `result` for the output. See the [jobs reference](/docs/api/jobs).

## Batches

A **batch** groups up to 256 async requests into a single submission (`POST /v1/batches`). All items are queued atomically — a malformed item fails the whole batch before anything is created. See the [batches reference](/docs/api/batches).

## Workflows

A **workflow** is a DAG of inference steps. Each step can be one of:

- `inference` — call one model.
- `map` — fan out over a list (one job per item).
- `transform` — pure data step (split, pluck, join).
- `collect` — gather a fan-out's outputs into one list.
- `gate` — pause and wait for human approval before continuing.

Steps pass data to each other via `{{ steps.<id>.output... }}` templates. The engine resolves the DAG, queues jobs as dependencies complete, and presents the live state as an SVG-rendered graph in **Dashboard → Queue**. See the [workflows reference](/docs/api/workflows).

## Routing

The current rule is: **first online provider that serves the requested model (and service type) wins**. There's no load balancing or automatic failover. If the chosen provider's agent doesn't answer or returns an error, the request fails (or, for async jobs, is retried up to the configured limit).
