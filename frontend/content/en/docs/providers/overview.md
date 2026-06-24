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

You can be a provider on a workstation under your desk, a homelab box, a rented server — anywhere you can run a Kubernetes cluster (k3s counts, even a single node) and reach the internet.

## What you need

- **Hardware that runs an LLM server.** Anything with an OpenAI-compatible HTTP API: vLLM, LM Studio, Ollama (with the OpenAI-compat endpoint enabled), llama.cpp's server, etc., deployed as a Kubernetes Service.
- **An inference.club account** and an API key (see [Quickstart](/docs/quickstart)).
- **A Kubernetes cluster** (k3s or any other) with GPU nodes and the NVIDIA device plugin. The agent installs via a Helm chart in discovery mode — see [Run an agent](/docs/providers/run-an-agent).
- **Network reachability** between inference.club's servers and your agent. The agent joins inference.club's private Tailscale network from inside the cluster, so no port forwarding or public URL is required on your end.

## How heartbeats work

The agent runs inside your Kubernetes cluster in **discovery mode**: it watches the cluster for labeled model services, then joins inference.club's private Tailscale tailnet from inside the cluster. All connectivity is outbound — the agent dials out and keeps a beacon open, so you never expose a port, forward traffic, or publish a public URL.

Every ~30 seconds the agent sends a heartbeat over that outbound beacon, advertising which models it's currently serving and their capabilities. inference.club records the provider and the model set it reported, and learns the agent's MagicDNS hostname on the tailnet (something like `club-host-1`) — that's how the backend reaches it later, over WireGuard. A provider is considered **online** if a heartbeat arrived within the last ~2 minutes; miss that window and it's marked offline until the next beat.

## How proxied requests work

When a consumer calls `/v1/chat/completions` with a given `model`, inference.club:

1. Authenticates the consumer's API key.
2. Selects the **first online provider** serving that model for the requested service type.
3. Forwards the request over the tailnet to that provider's agent, addressing it by its MagicDNS hostname.
4. The agent routes the request to the right in-cluster model server, and the response is streamed back to the consumer.

::callout{type="note"}
For the full end-to-end request path — authentication, provider selection, the tailnet hop, and routing inside the cluster — see [Architecture overview](/docs/architecture/overview).
::

## Next steps

- **[Run an agent](/docs/providers/run-an-agent)** — install the agent, configure it, see the heartbeat land.
- **[Kubernetes agent](/docs/providers/kubernetes-agent)** — how discovery mode finds and labels your model services.
