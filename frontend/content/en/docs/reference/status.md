---
title: Status & limitations
description: What's solid, what's rough, and what's actively being built. An honest map of the edges.
category: Reference
order: 1
---

# Status & limitations

inference.club is a young, fast-moving project run on real hardware. Much of it is solid; some of it is deliberately incomplete; some is changing under your feet. This page is the honest map so nothing surprises you.

## What's solid

The core works and is in daily use: the OpenAI-compatible API across every modality, GitHub sign-in, the agent's Kubernetes discovery, the Tailscale bridge, the playground, sharing and collections, and the async jobs / batches / workflows engine. If it's documented in the [API reference](/docs/api/overview), you can rely on the request and response shapes.

## Known limitations

::callout{type="limitation" title="Routing is first-match, not balanced"}
A request goes to the **first** online provider serving the model and service type. There's no load balancing within a tier and no automatic failover — if the chosen provider errors, a direct call fails (an [async job](/docs/services/direct-vs-async) retries). Smarter, load-aware routing is on the roadmap.
::

::callout{type="limitation" title="No billing or quotas yet"}
Every request is metered into an `InferenceRequest` row, but nothing is charged and there are no enforced quotas. There are also no hard rate limits in the current build — be considerate of other people's GPUs.
::

::callout{type="limitation" title="Compute is per-user by default"}
By default your requests only route to your own providers. Cross-user sharing exists through per-service access policies, but the "use the whole community's compute" experience is still early — sharing controls and discovery will deepen.
::

::callout{type="limitation" title="A few modality edges"}
Voice cloning is synchronous-only. There's no embeddings endpoint yet. Some capability-gated features (timestamps, tool use, vision) depend entirely on what the operator's model declares — always check `/v1/models`.
::

## Active development

::callout{type="construction" title="Payments & metered access"}
On-chain micropayments (USDT on Base, the x402 pattern) and a premium tier are designed but not yet implemented. Until then, access is membership-gated and unmetered.
::

::callout{type="construction" title="Evaluations"}
Native performance metrics, links to external benchmarks, and provider-run quality evals are planned so you can compare models and nodes on more than vibes.
::

::callout{type="construction" title="Media pipeline & narration"}
The Narration Studio and a URL-to-video media pipeline are being folded into workflow-native features. Expect rapid change in the studio and compose endpoints.
::

::callout{type="construction" title="Storage & delivery"}
Media has moved to Google Cloud Storage; the legacy self-hosted object store is being removed, and a CDN in front of the media bucket is still to come.
::

## Internationalization

The docs and marketing site are translated into several languages; pages that aren't yet translated fall back to English (you'll see a small notice). Inside the product, some dashboard pages are still English-only. Translations are ongoing.

## Found an edge we didn't list?

Report it — the platform issues live at [github.com/inference-club/inference.club](https://github.com/inference-club/inference.club/issues) and the agent at [github.com/inference-club/inference-club-agent](https://github.com/inference-club/inference-club-agent/issues). See the [FAQ](/docs/faq) for the common ones.
