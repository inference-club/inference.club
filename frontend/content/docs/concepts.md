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

- `llm` (default) — text in, text out: `/v1/chat/completions`, `/v1/completions`.
- `stt` — speech-to-text: audio in, text out: [`/v1/audio/transcriptions`](/docs/api/audio-transcriptions).
- `image` — image generation: text in, image out: [`/v1/images/generations`](/docs/api/images) and `/v1/images/edits`.
- `tts` — text-to-speech (reserved; not serving yet).

The type is set in the agent's manifest. Omit it and it defaults to `llm`, so existing setups are unaffected:

```yaml
hosts:
  - id: rig-01
    services:
      - name: vllm-qwen          # an LLM service (type defaults to llm)
        engine: vllm
        url: http://localhost:8000/v1
        models:
          - hf: Qwen/Qwen3-30B-A3B
      - name: asr-qwen           # a speech-to-text service
        type: stt
        engine: vllm
        url: http://localhost:8001/v1
        # Declare per-deployment capabilities. Add `timestamps` only if the
        # server actually returns word/segment timings (e.g. Qwen3-ASR served
        # with its ForcedAligner, or a Whisper server). inference.club then
        # requests verbose_json and shows an interactive transcript; without
        # it, verbose_json is downgraded to plain text.
        features: [timestamps]
        models:
          - id: Qwen/Qwen3-ASR-1.7B
```

Routing respects the type: a transcription request only ever lands on an `stt` service, and a chat request only on an `llm` service — even if they share a model name.

## Routing

The MVP rule is simple: **first online provider that serves the requested model wins**. There's no load balancing, no fallback to a second provider on failure, no health-weighted scoring. If the chosen provider's agent doesn't answer or returns an error, the request fails.

This is fine for the MVP because most users have one or two agents. As the network grows we'll layer real routing on top of the same data model.
