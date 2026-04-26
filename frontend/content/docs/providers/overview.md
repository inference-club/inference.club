---
title: Become a provider
description: How agents register, heartbeat, and serve requests.
category: Providers
order: 1
---

# Become a provider

A **provider** is your account on inference.club paired with one or more **agents** running on your hardware. The agent is a small program ([`inference-club-agent`](https://github.com/inference-club/inference-club-agent)) that:

1. Heartbeats into inference.club every 30 seconds, advertising which models it's currently serving.
2. Accepts proxied inference requests from inference.club and forwards them to your local LLM server.

You can be a provider on a workstation under your desk, a homelab box, a rented server — anywhere you can run Docker and reach the internet.

## What you need

- **Hardware that runs an LLM server.** Anything with an OpenAI-compatible HTTP API: vLLM, LM Studio, Ollama (with the OpenAI-compat endpoint enabled), llama.cpp's server, etc.
- **An inference.club account** and an API key (see [Quickstart](/docs/quickstart)).
- **Docker** on the machine that runs the agent.
- **Network reachability** between inference.club's servers and your agent. On localhost this is automatic. From the public internet you'll need either a publicly reachable hostname (Cloudflare Tunnel, Tailscale Funnel, or a VPS reverse proxy) or to wait for the upcoming push-mode option.

## How heartbeats work

Every 30 seconds the agent makes one request:

```
POST https://api.inference.club/api/inference/agent/heartbeat/
Authorization: Bearer <your-api-key>
Content-Type: application/json

{
  "name": "home-rig",
  "callback_url": "http://192.168.5.173:8002/v1",
  "models": [
    {"name": "qwen3-8b", "context_window": 32768}
  ],
  "health": {"up": true}
}
```

inference.club upserts a `Provider` record keyed by `(your_user, name)` and replaces its model set with what you reported. Inference.club considers the provider **online** if a heartbeat arrived in the last 60 seconds — one missed beat is fine, two starts to look like a problem.

## How proxied requests work

When a consumer calls `/v1/chat/completions` with `"model": "qwen3-8b"`, inference.club:

1. Authenticates the consumer's API key.
2. Looks up the **first online provider on that user's account** that serves `qwen3-8b`.
3. POSTs the request body to `<provider.callback_url>/chat/completions`.
4. Streams the response back to the consumer untouched.

Your agent is what's on the other end of step 3. It forwards the request to the local LLM server you configured (`http://localhost:1234/v1` or wherever).

## Next steps

- **[Run an agent](/docs/providers/run-an-agent)** — install the agent, configure it, see the heartbeat land.
