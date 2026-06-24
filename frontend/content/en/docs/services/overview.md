---
title: Services & modalities
description: Every kind of inference the network can serve — the endpoint it answers, and the kind of model behind it.
category: Services
order: 1
---

# Services & modalities

inference.club is not just chat. A provider can expose many **services**, each declaring a **type** that decides which endpoints it answers and how requests are routed to it. A transcription request only ever lands on a speech-to-text service, even if two services happen to share a model name.

Which modalities are live at any moment depends on what the providers are running. The reference cluster (the project's own home GPU fleet) serves all of them; the model names below are what *it* runs — on the open network, call [`GET /v1/models`](/docs/api/models) to see what's actually reachable for you.

## The catalog

| Service | Endpoint(s) | In → out | Reference model |
|---|---|---|---|
| **Chat / LLM** | `/v1/chat/completions`, `/v1/completions` | text → text | Qwen3, Nemotron |
| **Speech-to-text** | `/v1/audio/transcriptions` | audio → text | Nemotron ASR |
| **Text-to-speech** | `/v1/audio/speech` | text → audio | Magpie TTS |
| **Voice cloning** | `/v1/voice/generations` | script + samples → audio | Dia |
| **Image** | `/v1/images/generations`, `/v1/images/edits` | text/image → image | FLUX.2 Klein |
| **Video** | `/v1/videos/generations` | text/image → video | LTX-2 |
| **Music** | `/v1/music/generations` | text + lyrics → audio | ACE-Step |
| **3D mesh** | `/v1/3d/generations` | image → 3D (GLB) | TRELLIS |
| **Audio enhance** | `/v1/audio/enhance` | audio → audio | Maxine Studio Voice |
| **Scrape** | `/v1/scrape` | URL → markdown | Firecrawl |

## Text & language

The `llm` services speak the full OpenAI chat surface — streaming, multimodal messages (image inputs on vision models), tool calling, and JSON-mode extraction on models that declare those features. The legacy `/v1/completions` endpoint is there for older clients; new work should use chat completions.

::callout{type="tip" title="Capabilities are declared, never guessed"}
Each model advertises its `input_modalities`, `output_modalities`, `supported_features` (`reasoning`, `tools`, `vision`, `timestamps`, `voice-cloning`…) and `context_length`. A programmatic caller should read these from `/v1/models` and pick a model by capability rather than hard-coding a name.
::

## Audio

Three distinct audio services. **Speech-to-text** transcribes uploaded audio and, when the model advertises the `timestamps` feature, returns word- and segment-level timings. **Text-to-speech** synthesizes speech from text with a selectable voice ([`GET /v1/audio/voices`](/docs/api/speech) lists them). **Voice cloning** is a richer TTS path: you supply a `[S1]`/`[S2]` dialogue script and optionally map each speaker to a short audio sample from your library, and the engine generates a multi-speaker performance. **Audio enhance** takes a noisy recording and returns a cleaned one.

## Vision & 3D

**Image** services generate and edit stills. **Video** generates clips from a text prompt or an initial image (image-to-video). **3D mesh** turns a single image into a downloadable GLB model you can drop into a `<model-viewer>` or a game engine.

## Music

**Music** generation takes a text description plus optional lyrics and structure hints (duration, BPM, key) and returns a finished track. It pairs naturally with image generation for cover art — the `song-and-cover` [workflow template](/docs/api/workflows) does exactly that.

## Utility: scrape

Not every service is a GPU model. **Scrape** fetches a URL and returns clean Markdown — useful as the first step of a research workflow or as a tool the [playground agent](/docs/playground/overview) can call.

## How a request finds a service

Every endpoint resolves a provider the same way: find the first **online** provider that serves the requested model **and** the matching service type, then proxy the call over the tailnet. See [Routing](/docs/concepts#routing) for the selection rules and [Architecture](/docs/architecture/overview) for the full path a request takes.

Most of these endpoints can run **synchronously** (you wait for the result) or **asynchronously** (you get a job id and poll). See [Direct vs async](/docs/services/direct-vs-async).
