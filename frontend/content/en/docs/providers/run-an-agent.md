---
title: Run an agent
description: Install inference-club-agent, point it at your local LLM server, and watch it register.
category: Providers
order: 2
---

# Run an agent

This guide walks through bringing up an `inference-club-agent` on a machine that's already running an OpenAI-compatible LLM server (vLLM, LM Studio, Ollama, llama.cpp, etc.).

## 1. Confirm your local LLM server is reachable

Before plugging anything into inference.club, make sure your local server responds. If you're running LM Studio with its OpenAI-compatible server enabled on port 1234, this should work:

```bash
curl http://localhost:1234/v1/models
```

You should get back a list. If you don't, fix that first — the agent is a thin proxy and can't make a broken upstream work.

Note its base URL — for the rest of this guide we'll assume `http://localhost:1234/v1`.

## 2. Get an inference.club API key

Sign in at <https://inference.club/login>. Go to **Dashboard → Settings → Token** and create one. Copy it once.

## 3. Run the agent

The agent ships as a Docker container. With your LLM server running on the host:

```bash
docker run -d --name inference-club-agent \
  --restart unless-stopped \
  --network host \
  -e INFERENCE_CLUB_URL=https://api.inference.club \
  -e INFERENCE_CLUB_API_KEY=<your-key> \
  -e AGENT_NAME=home-rig \
  -e AGENT_CALLBACK_URL=http://<this-machine-ip>:8002/v1 \
  -e LLM_BASE_URL=http://localhost:1234/v1 \
  -e LLM_MODELS=qwen3-8b \
  ghcr.io/inference-club/inference-club-agent:latest
```

A few pieces to get right:

- `AGENT_NAME` — pick something memorable; this is what shows up in the dashboard and in `owned_by` on `/v1/models`. Must be unique within your account.
- `AGENT_CALLBACK_URL` — what inference.club hits when it proxies a request to you. On a home LAN where inference.club can't reach you, see "Networking" below.
- `LLM_BASE_URL` — your local server's OpenAI-compatible base URL.
- `LLM_MODELS` — comma-separated list of model names to advertise. Must match what your local server actually serves.

## 4. Check it registered

Open the dashboard at <https://inference.club/providers/my-nodes>. You should see your agent with a green **online** badge within 30 seconds. The model list reflects what you reported.

If it doesn't show up, check the agent's logs:

```bash
docker logs -f inference-club-agent
```

The most common failures: wrong API key (look for `401`), unreachable inference.club URL, malformed `LLM_MODELS`.

## 5. Make a request through the network

```bash
curl https://api.inference.club/v1/chat/completions \
  -H "Authorization: Bearer <your-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-8b",
    "messages": [{"role": "user", "content": "hi"}]
  }'
```

The request goes inference.club → your agent → your local LLM server → back. Latency is what your local server takes plus a small overhead.

## Networking

For inference.club (running in the cloud) to reach your agent, **your agent's `AGENT_CALLBACK_URL` has to be reachable from the public internet**. Three common options:

| Option | Setup | Trade-off |
|---|---|---|
| Direct exposure | Open a port on your router, set `AGENT_CALLBACK_URL` to your public IP | Simple; exposes your home network |
| [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) | Zero-config tunnel; CF gives you a stable hostname | Recommended; no port forward needed |
| [Tailscale Funnel](https://tailscale.com/kb/1223/funnel) | Same idea on Tailscale | Recommended if you already use Tailscale |

For local-only development where both inference.club and the agent run on your laptop, you can use `http://localhost:8002/v1` and skip all of this.

## Updating

```bash
docker pull ghcr.io/inference-club/inference-club-agent:latest
docker stop inference-club-agent && docker rm inference-club-agent
# then re-run the `docker run` command from step 3
```

The agent will heartbeat in within 30 seconds of restarting and your provider record will pick up where it left off.
