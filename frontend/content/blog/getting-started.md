---
title: "Getting started with inference.club in five minutes"
description: "From GitHub sign-in to your first chat completion: a step-by-step quickstart for inference.club's OpenAI-compatible API, plus how to wire it into Open WebUI and the OpenAI SDK."
publishedAt: "2026-05-30"
author: Brian Caffey
tags: [quickstart, guide, llm-inference]
image: /images/blog/getting-started.png
image_prompt: "Wide cinematic abstract technology illustration: a single glowing API key dissolving into flowing streams of cyan and violet light that connect a small cluster of softly glowing home computer and server icons across a dark background, minimal clean futuristic aesthetic, soft bokeh depth, no text, no words, no letters"
---

inference.club gives you one API key and one OpenAI-compatible endpoint. Anything that already speaks the OpenAI protocol — the Python SDK, Open WebUI, Cursor, your own agent loop — works against it with a base-URL change and nothing else. This post takes you from zero to your first streamed response, then shows how to point real tools at it.

If you'd rather read the terse reference version, it lives in the [docs quickstart](/docs/quickstart). This is the walk-through.

## Step 1 — Sign in and create a key

Go to [inference.club/login](https://inference.club/login) and sign in with GitHub. (GitHub is the only sign-in for now — it's how the network attributes nodes and usage to people.)

Once you're in, open **Dashboard → Settings → Token** and click **Create token**. You'll see the value exactly once, so copy it somewhere safe:

```bash
export INFERENCE_CLUB_KEY=<your-key>
```

Treat it like a password. Anyone holding it can use the network as you, and your usage counts against your rate limits.

## Step 2 — See which models you can call

```bash
curl https://api.inference.club/v1/models \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

You get back an OpenAI-format list of every model you're allowed to route to right now — your own nodes if you run any, plus any shared services on the network you've been granted access to:

```json
{
  "object": "list",
  "data": [
    {
      "id": "nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4",
      "object": "model",
      "created": 1780000000,
      "owned_by": "club-host"
    }
  ]
}
```

Grab a `model` id from that list for the next step. If it comes back empty, no node you can reach is advertising a model yet — either register your own agent (Step 6) or ask a provider to share one with you.

## Step 3 — Your first chat completion

```bash
curl https://api.inference.club/v1/chat/completions \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4",
    "messages": [
      { "role": "user", "content": "Say hello in one short sentence." }
    ]
  }'
```

The response is a standard OpenAI chat completion — the same shape you'd get from `api.openai.com`. Behind the scenes, inference.club routed your request to an online node serving that model and streamed the answer back.

## Step 4 — Use it from the OpenAI SDK

Point the base URL at inference.club and everything else is normal OpenAI code:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.inference.club/v1",
    api_key="<your-key>",
)

resp = client.chat.completions.create(
    model="nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4",
    messages=[{"role": "user", "content": "Say hello in one short sentence."}],
)
print(resp.choices[0].message.content)
```

Streaming works the same way it does with OpenAI:

```python
stream = client.chat.completions.create(
    model="nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4",
    messages=[{"role": "user", "content": "Count to ten."}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

Any OpenAI-compatible field your underlying server understands — `temperature`, `top_p`, `max_tokens`, `tools`, `response_format` — is forwarded straight through.

## Step 5 — Point Open WebUI (or any client) at it

In Open WebUI: **Settings → Connections → OpenAI API**, set the base URL to `https://api.inference.club/v1`, paste your key, and the model dropdown fills with whatever you can reach. The same one-line base-URL swap works for Cursor, LibreChat, LangChain, or anything else that takes an OpenAI base URL.

> One gotcha if your client runs in Docker: `localhost` inside a container is the container itself. Use the published host address (or `host.docker.internal`) so the client can actually reach the API.

## Step 6 (optional) — Put your own GPU on the network

If you've got a workstation or homelab box running an OpenAI-compatible server (vLLM, LM Studio, Ollama, llama.cpp), you can serve too. Run the `inference-club-agent` next to your LLM server with your API key; it joins the network and registers what you're serving. Your own requests route back to your own hardware, and you decide who else can use it under **Settings → Access** — only you, any member, or a specific allowlist of GitHub users.

Full walkthrough: [Run an agent](/docs/providers/run-an-agent).

## Where to look next

- **Settings → Usage** shows your live rate-limit headroom.
- **Leaderboard** tracks token usage across the network.
- Your public profile at `inference.club/<your-github-handle>` shows the compute you provide and the inference you've run.

That's the whole loop: one key, one endpoint, every OpenAI-speaking tool you already use. Bring your own GPU or borrow someone else's — same API either way.
