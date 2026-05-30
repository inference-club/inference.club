---
title: "Idle GPUs, growing bills, and the case for a community LLM network"
description: "Why we're building inference.club — a self-hosted, OpenAI-compatible LLM inference network where you bring your own GPU or use someone else's, all behind one API key."
publishedAt: 2026-04-26
author: Brian Caffey
tags: [announcements, vision, llm-inference]
image: /images/blog/introducing-inference-club.png
image_prompt: "Wide cinematic abstract technology illustration: a high-end graphics card GPU under a desk glowing back to life, streams of cyan and violet light flowing out of it and connecting to a constellation of small glowing nodes representing a community network, dark background, idle hardware awakening, clean futuristic minimal, soft bokeh, no text, no words, no letters"
---

There's a 4090 sitting in a tower under my desk that does real work for maybe two hours a day. The rest of the time it's drawing 30 watts at idle. Multiply that by everyone reading this who has a workstation with a real GPU in it — homelabs, gaming rigs, dual-purpose machines from when the crypto thing happened — and there's a meaningful amount of LLM inference capacity scattered across the internet that nobody is using.

Meanwhile the OpenAI bill keeps growing. Anthropic, Google, the rest. The hyperscalers got there first, the developer experience is genuinely great, and for a lot of work they're still the right answer. But for the cases where they aren't — privacy-sensitive workloads, dev-time iteration, hobby projects, anything where the per-token cost makes you think twice before clicking run — there should be a third option that isn't "spin up a vLLM container yourself every time."

That third option is what we're building. **inference.club** is a community-run network for LLM inference. You sign up, get one API key, and you immediately have an OpenAI-compatible endpoint that any client speaking the OpenAI protocol can use. If you also have hardware you want to put on the network, you run a small agent next to your local LLM server and your own requests get routed back to your own machine. If you don't, you use someone else's.

That's the whole pitch. The rest of this post is the longer version: what's actually built, what's *not* built yet, and how to try it.

## The shape of the problem

Three things are true at the same time:

**LLM inference is expensive at the API layer and cheap at the silicon layer.** A single H100 hour costs less than 1M GPT-4-class tokens at retail API prices. The arbitrage is real, and it's not going away even as model providers compete on price — the hyperscaler margin pays for the abstraction, the SLA, the safety review, and a lot of GPU procurement risk you don't have when you already own the GPU.

**Modern GPUs spend most of their life idle.** A workstation 4090, a homelab 3090, a Mac Studio with 192 GB of unified memory, a leftover dual-A6000 box from a project that wrapped — these machines exist, they're individually capable of running 8B–70B models comfortably, and they're collectively a meaningful fraction of the world's available consumer LLM inference capacity. Nothing on the market today makes that capacity easy to use.

**OpenAI is the protocol, not the only provider.** Almost every interesting open-source LLM serving layer — vLLM, LM Studio, Ollama, llama.cpp's server, TGI — exposes the OpenAI HTTP shape. Almost every interesting client app — Open WebUI, Cursor, every Python notebook with a `from openai import OpenAI`, every agent framework worth using — speaks it. Once you have an authenticated OpenAI-compatible endpoint, the rest of the ecosystem snaps into place for free.

These three facts have been true for a while. inference.club is the small bridge that makes them work together.

## What we're building

The architecture in one paragraph: a Django backend behind `api.inference.club` does authentication, routing, and proxying. Each user has one API key. Each user can register one or more **providers** — a provider is just a record pointing at an `inference-club-agent` running on hardware you control. The agent heartbeats into the platform every 30 seconds with the list of models it's currently serving. When a consumer calls `POST /v1/chat/completions`, the platform looks up the first online provider on that user's account that serves the requested model, proxies the request to the provider's callback URL, and streams the response back. Nothing fancy.

A diagram, since text walls are bad on phones:

```
Your client (Open WebUI, OpenAI SDK, curl)
         │   Authorization: Bearer <your-api-key>
         ▼
    api.inference.club  ──┐
                          │  proxies to the callback_url
                          │  the agent registered
                          ▼
   inference-club-agent on your hardware
                          │
                          ▼
   vLLM / LM Studio / Ollama / llama.cpp / ...
```

Three things to note:

**One key, two roles.** The same API key authenticates your client when it does inference *and* authenticates your agent when it heartbeats in. We don't make you manage two credentials for one account. Some users will only consume; some will only provide; most will do both.

**Your hardware serves your inference.** In the MVP, the platform only routes a user's requests to that user's own providers. Your 4090 isn't serving a stranger's prompts, and your prompts aren't going to a stranger's 4090. That model will evolve as the network grows — the whole point eventually is shared compute — but locking it down per-user for v1 keeps the trust story simple and gives us time to figure out fair routing before we have to.

**Streaming is real, not faked.** SSE responses pass through the proxy untouched. The bytes leave your local LLM server and arrive at the client as fast as the wire allows, which means it feels exactly like talking to OpenAI directly when the upstream is fast.

## How a request actually flows

Here's a real one. You have an inference.club key. You have LM Studio running on your laptop, serving `qwen3-8b` on `localhost:1234/v1`. You have `inference-club-agent` running on the same machine, configured with your key and a callback URL the platform can reach.

```bash
curl https://api.inference.club/v1/chat/completions \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-8b",
    "messages": [{"role": "user", "content": "say hi"}]
  }'
```

What happens:

1. The platform validates your bearer token and resolves it to your user account.
2. It looks up an online provider on your account that has `qwen3-8b` in its current model list. (Online means a heartbeat in the last 60 seconds.) It finds your agent.
3. It POSTs the request body to your agent's callback URL plus `/chat/completions`.
4. Your agent forwards the body to LM Studio at `localhost:1234/v1/chat/completions`.
5. LM Studio runs the model and returns the response.
6. The response streams back agent → platform → your curl. Total platform overhead: a few milliseconds plus one TCP round-trip.

The platform records a row for the request — user, provider, model, latency — but it doesn't see or store the prompt or response content beyond the fact that a request happened. The data path goes provider-to-consumer; the platform is in the middle for routing only.

## What you can do today

The MVP is online and the infrastructure is published. Concretely:

- **Use the API as a consumer.** Get a key, point any OpenAI client at `https://api.inference.club/v1`, and call `/v1/models` and `/v1/chat/completions` exactly as you would with OpenAI. The [quickstart](/docs/quickstart) walks the whole thing in five minutes.
- **Run a provider.** If you have a machine with a GPU and a local LLM server you already use, drop in `inference-club-agent` (one Docker container) and your hardware is part of the network. The [run-an-agent guide](/docs/providers/run-an-agent) covers the install, the env vars, and the networking question (how the platform reaches your home LAN — short answer: Cloudflare Tunnel or Tailscale Funnel).
- **Read the code.** Both repos are open source: the platform is at `github.com/inference-club/inference.club`; the agent at `github.com/inference-club/inference-club-agent`. The whole thing deploys to a single Hetzner VPS with `docker compose` orchestrated by Pulumi — there's a runbook in `infra/README.md` if you want to self-host the platform itself.

## What's *not* in the MVP

Being honest about this matters. A community network that hand-waves about "coming soon" loses trust fast.

- **No cross-user routing.** Your requests only hit your providers. Real shared compute requires a fair routing layer, a basic accounting model, and a story for trust between strangers — all of which are coming, in that order, but none of which exist today.
- **No billing, no rate limits, no quotas.** The MVP doesn't meter anything beyond recording that requests happened. Don't be a jerk about it; this is a gentleman's-agreement period.
- **No automatic failover.** If your selected provider's agent goes offline mid-request, the request fails. There's no "retry on the next provider that serves this model" yet.
- **No inbound auth on the agent.** The agent currently trusts that requests reaching its callback URL came from the platform. For local-network agents this is fine; for publicly-exposed agents we'll be shipping a shared-secret/HMAC scheme before encouraging anyone to expose theirs to the internet without a tunnel.
- **No model marketplace.** You discover what's available by calling `/v1/models`, which currently shows only your own providers. A real "what models are available across the network" view comes when cross-user routing does.

These aren't surprises — they're the natural shape of the v0. Each will get its own blog post when we ship it.

## What's coming next

The next three things on the roadmap, in order:

1. **Inbound auth on the agent.** Shared secret per provider, signed by the platform, verified by the agent. Unlocks safely exposing agents to the public internet without trusting every IP that knocks.
2. **Push-mode agents.** For homelab providers who can't or don't want to expose a public callback URL, the agent will be able to hold a websocket open *outbound* to the platform, and inference requests come back over it. Removes the NAT/tunnel requirement entirely.
3. **Cross-user routing, with consent.** Opt-in flag per provider that says "you may route other users' requests to me." Combined with the basic accounting we'll add at the same time, this is the bridge to the network actually being a network.

After those three, the interesting questions get interesting: pricing, reputation, model standards, what "fair" routing means when GPUs are wildly heterogeneous. Plenty to figure out.

## Try it

If you've read this far you're probably the target audience. The fastest path:

1. **[Quickstart](/docs/quickstart)** — get a key, run a curl, see it work.
2. **[Run an agent](/docs/providers/run-an-agent)** — put your hardware on the network.
3. **[The code on GitHub](https://github.com/inference-club)** — read it, file issues, open PRs.

If you have a GPU sitting idle and a few hours to spare, you can be a provider on the network by the end of this afternoon. That's the goal — small, sharp, and useful before it's big.

More writing soon, including the technical posts on each of the deferred items above as we ship them. Subscribe to the [blog](/blog) — RSS coming with the next post.
