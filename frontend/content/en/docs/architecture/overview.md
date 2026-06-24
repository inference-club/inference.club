---
title: Architecture overview
description: How a small cloud box, a home GPU cluster, and object storage combine into one inference network.
category: Architecture
order: 1
---

# Architecture overview

inference.club is built from three pieces that each do one thing well: a small always-on **cloud control plane**, a **home GPU cluster** that never touches the public internet, and **object storage** for generated media. A private network tunnel bridges the first two; the third keeps heavy bytes off the hot path.

::arch-diagram
::

## Three pillars

**The control plane** is a single small cloud VPS. It's cheap, stateless cattle — it can be rebuilt from scratch — and it runs everything that has to be public: the website, the OpenAI-compatible API, authentication, the model catalog and routing logic, async job orchestration, rate limiting, and the database. It holds *no* GPUs.

**The compute** is a cluster of GPU machines at home. It is never exposed to the internet — no inbound ports, no public IP. It runs the actual models across several boxes and describes itself to the control plane through the agent.

**The bridge** is [Tailscale](https://tailscale.com). The agent runs *inside* the cluster and dials *out* to join a private tailnet, so the control plane can reach the cluster over an encrypted WireGuard tunnel without anyone forwarding a port. Media is offloaded to **Google Cloud Storage** and served straight from Google's edge.

The two halves are deployed independently: the control plane ships from this repo's CI, the cluster from a separate GitOps repo. They only ever meet over the tailnet.

## The life of a request

When you call `/v1/chat/completions`:

1. **TLS terminates at the edge.** A Caddy reverse proxy on the VPS handles HTTPS and streams server-sent events through without buffering.
2. **The backend authenticates and routes.** Django validates your API key and selects the first online provider serving the requested model and service type ([routing rules](/docs/concepts#routing)).
3. **The request crosses the tailnet.** The backend forwards it through its Tailscale sidecar over WireGuard, addressing the agent by a stable MagicDNS hostname like `club-host-1` — no DNS or TLS gymnastics, because the tunnel already encrypts the wire.
4. **The agent routes inside the cluster.** It forwards the call to the right in-cluster model server (vLLM, LM Studio, a diffusion service…) at its Kubernetes DNS name.
5. **The response streams back** the same way, untouched. The backend records latency, token counts, and time-to-first-token on an `InferenceRequest` row as it passes through.

Generated images, audio, video, and 3D don't take this path back — they're written to object storage and returned as URLs the browser fetches directly.

## Liveness without inbound access

Because nothing reaches *into* the cluster uninvited, the agent proves it's alive by reaching *out*: it sends a heartbeat every ~30 seconds, and the backend also runs a prober that pings each agent's health endpoint over the tailnet. A provider counts as online only if it was seen within the last ~2 minutes, so one missed beat is fine and a dead agent drops out quickly.

## Go deeper

::doc-cards
  :::doc-card{title="The home cluster" to="/docs/architecture/cluster" icon="cpu"}
  k3s, GPU discovery, the model services, and how the agent reads the cluster.
  :::

  :::doc-card{title="The platform" to="/docs/architecture/platform" icon="server"}
  The Hetzner deployment, Django + Celery, storage, auth, and CI/CD.
  :::
::
