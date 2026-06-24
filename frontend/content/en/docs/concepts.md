---
title: Concepts
description: The model in your head — users, API keys, providers, agents, models, routing.
category: Getting started
order: 2
---

# Concepts

A small vocabulary. Everything else in these docs is built on top of these seven ideas.

## User

A person with an inference.club account. Sign-up is GitHub OAuth (guests and passcodes exist for playground-only access — see [Auth & access](/docs/architecture/platform#auth)). A user can be a **consumer** (calls the API), a **provider** (runs an agent that serves models), or both. The same account and the same API key cover every role — there's no separate registration.

## API key

A bearer token that authenticates a request. One key identifies one user, and it works in both directions:

- Your **OpenAI client** sends it when calling `https://api.inference.club/v1/...`
- Your **agent** sends it once, on first registration, to join the network

Treat it like a password; rotate it from **Dashboard → Settings → Token** if it leaks.

::callout{type="note" title="External keys are different"}
The key above is your inference.club identity. Separately, the playground agent can use **your own** third-party keys (Brave, ElevenLabs, OpenAI…) stored encrypted under **Settings → API keys**. Those never leave your account.
::

## Provider

A user-owned record representing one piece of your compute. A provider has a **name** you pick (`club-host`, `office-rig`), the **services** it currently serves, and a **last-seen** timestamp. A provider is considered **online** if its agent checked in within the last two minutes.

Providers reach the platform over a private [Tailscale](https://tailscale.com) tunnel — the agent dials *out* to join, so there's no port forwarding and nothing of yours is exposed to the public internet.

## Agent

The program (`inference-club-agent`) that runs on your hardware and bridges it to the network. It runs on **Kubernetes** in discovery mode: instead of a hand-written config file, it watches the cluster, finds the services you've labeled, and reports them — including which GPU each one runs on, read live from node labels.

It does two things continuously:

1. **Heartbeats** every ~30 seconds so the platform knows it's online.
2. **Serves** proxied `/v1/*` requests, forwarding each to the right in-cluster model server and streaming the response back over the tunnel.

::callout{type="note" title="The agent setup changed"}
Earlier versions ran as a single Docker container with an `agent.yaml` manifest. That path is retired — the agent now reads everything from the live cluster. See [Run an agent](/docs/providers/run-an-agent).
::

## Model

A name a service advertises — `qwen3-30b-a3b`, `flux-2-klein`, whatever the local server calls it. When you call an endpoint with `"model": "..."`, the platform finds an online provider serving that model **and** the right service type, and proxies the request there.

Models also carry **capabilities** — declared by the operator, never guessed: input/output modalities, features like `reasoning` or `tools`, and a context window. `GET /v1/models` returns all of them so a caller can pick the right model programmatically.

## Service type (modality)

A model isn't always a chat model. Each service declares a **type** that decides which endpoints it answers. Routing respects it — a transcription request only ever lands on an `stt` service, even if two services share a model name.

| Type | Endpoint(s) | In → out |
|---|---|---|
| `llm` | `/v1/chat/completions`, `/v1/completions` | text → text |
| `stt` | `/v1/audio/transcriptions` | audio → text |
| `tts` | `/v1/audio/speech`, `/v1/voice/generations` | text → audio |
| `image` | `/v1/images/generations`, `/v1/images/edits` | text/image → image |
| `music` | `/v1/music/generations` | text/lyrics → audio |
| `video` | `/v1/videos/generations` | text/image → video |
| `mesh` | `/v1/3d/generations` | image → 3D mesh |
| `audio-enhance` | `/v1/audio/enhance` | audio → audio |
| `scrape` | `/v1/scrape` | URL → markdown |

The type comes from a Kubernetes label (`inference-club.com/type`) on the service — see [Run an agent](/docs/providers/run-an-agent). [Voice cloning](/docs/api/voice-generations) is a `tts` service that also advertises the `voice-cloning` feature, unlocking `/v1/voice/generations`.

## Routing

The rule today is simple: **the first online provider that serves the requested model and service type wins.** Each user has a routing preference — use only your own nodes, prefer your own then fall back to the network, or use any accessible node (the default).

::callout{type="construction" title="No load balancing yet"}
There's no load balancing or automatic failover *within* a tier. If the chosen provider errors, a synchronous request fails; an [async job](/docs/services/direct-vs-async) retries up to its limit. Smarter routing is on the roadmap — see [Status & limitations](/docs/reference/status).
::

## Async jobs, batches & workflows

Every JSON generation endpoint accepts `"async": true`, which queues the request as a **job** and returns immediately. A **batch** submits up to 256 jobs atomically. A **workflow** wires steps into a DAG — fan out, transform, collect, and pause for human approval. See [Direct vs async](/docs/services/direct-vs-async).
