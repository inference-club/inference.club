---
title: Welcome to inference.club
description: A community-run inference network. Bring your own hardware, or use someone else's.
order: 1
---

# Documentation

inference.club is a community-run inference network. Members run GPUs at home and expose their local model servers; everyone calls those models through one OpenAI-compatible API. One key works in both directions — to **consume** inference and to **provide** it.

```
Base URL   https://api.inference.club/v1
Auth       Authorization: Bearer <your-api-key>
```

## Start here

::doc-cards
  :::doc-card{title="Quickstart" to="/docs/quickstart" icon="rocket"}
  Get a key and make your first request in five minutes.
  :::

  :::doc-card{title="For AI agents" to="/docs/quickstart-agents" icon="bot"}
  Model discovery, routing, async, and workflows — written for automated callers.
  :::

  :::doc-card{title="Concepts" to="/docs/concepts" icon="book"}
  The vocabulary: users, keys, providers, agents, models, routing.
  :::

  :::doc-card{title="Become a provider" to="/docs/providers/overview" icon="server"}
  Share your own GPUs on the network with the Kubernetes agent.
  :::
::

## What you can build with

The network serves far more than chat. Which modalities are live depends on what models the providers are running right now.

::doc-cards
  :::doc-card{title="The playground" to="/docs/playground/overview" icon="sparkles"}
  A browser tool for every modality — chat, agents, images, video, music, voice, and more.
  :::

  :::doc-card{title="Services & modalities" to="/docs/services/overview" icon="layers"}
  Each model type, the endpoint it answers, and the model behind it.
  :::

  :::doc-card{title="API reference" to="/docs/api/overview" icon="code"}
  Every endpoint, request shape, and error code.
  :::

  :::doc-card{title="Async, batches & workflows" to="/docs/services/direct-vs-async" icon="workflow"}
  Fire-and-forget jobs, 256-item batches, and multi-step DAGs.
  :::
::

## How it fits together

A small always-on cloud box is the **control plane** — the website, the API, auth, routing, billing, and async orchestration. The heavy **GPU compute** lives on home hardware that is never exposed to the internet. A private Tailscale tunnel bridges the two, and generated media is offloaded to object storage so the small box stays off the hot path.

::arch-diagram
::

The agent reports what it serves every ~30 seconds, so the platform's model list and routing always reflect what is actually online. For the full story — request path, the home k3s cluster, the Hetzner deployment, and storage — see [Architecture](/docs/architecture/overview).

::callout{type="note" title="Two front doors"}
**Humans** sign in with GitHub and use the dashboard + playground. **Machines** read [`llms.txt`](https://inference.club/llms.txt) and the [OpenAPI spec](https://api.inference.club/openapi.json), then call the API directly. Both use the same key.
::
