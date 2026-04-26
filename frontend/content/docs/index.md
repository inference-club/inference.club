---
title: Welcome to inference.club
description: A community-run inference network. Bring your own hardware, or use someone else's.
order: 1
---

# Welcome to inference.club

inference.club is a community-run inference network. Members run **agents** on their own hardware (a workstation with a GPU, a homelab, a rented box) that expose local LLM servers — vLLM, LM Studio, Ollama, anything OpenAI-compatible. Other members do inference against those agents through a single OpenAI-compatible API.

If you have an OpenAI client (the official SDK, Open WebUI, your own scripts, an agent harness), pointing it at `https://api.inference.club/v1` with your API key is all you need to start.

## Where to go from here

- **[Quickstart](/docs/quickstart)** — get an API key, point a client at the API, run your first request. Five minutes.
- **[Concepts](/docs/concepts)** — the model in your head: users, providers, agents, models, API keys.
- **[API reference](/docs/api/overview)** — the OpenAI-compatible endpoints, request shapes, error codes.
- **[Run an agent](/docs/providers/run-an-agent)** — install `inference-club-agent`, point it at your local LLM server, register it with inference.club.
- **[FAQ](/docs/faq)** — common questions and gotchas.

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
