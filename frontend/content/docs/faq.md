---
title: FAQ
description: Common questions and gotchas.
order: 99
---

# FAQ

### Is this OpenAI-compatible?

Yes. The `/v1/...` surface mirrors OpenAI's request and response shapes for chat completions, completions, and `/models`. Anything that talks to `api.openai.com` should work against `api.inference.club/v1` with just a base URL and key change.

### Can I use the same API key for inference and for my agent?

Yes. One key per user covers both directions. Your agent uses it to heartbeat in; your client uses it to do inference. There's no separate "provider key" vs "consumer key" concept.

### What models can I run?

Anything your local LLM server can serve and that you list in your agent's `LLM_MODELS`. inference.club doesn't validate model names — they're free-form strings, exact-match.

### What happens if my agent goes offline mid-request?

The in-flight request fails with `502 upstream_error`. Subsequent requests for the same model fail with `404 no_provider` until your agent comes back. There's no automatic failover to a second provider in the MVP — that's a known limitation.

### Can other people use my agent's hardware?

No. inference.club only routes a user's requests to that user's own providers. Your hardware serves your inferences.

That model will probably evolve as the community grows (the whole point is shared compute), but for the MVP it's strictly per-user.

### How is usage metered?

It isn't, yet. Every successful proxied request is recorded as an `InferenceRequest` row tied to your user, with model name and latency. Billing and quotas come later.

### What about rate limits?

None in the MVP. Don't be a jerk about it.

### Where do I report bugs?

GitHub: <https://github.com/inference-club/inference.club/issues> for the platform; <https://github.com/inference-club/inference-club-agent/issues> for the agent.

### Is there a self-hosted option?

The whole platform is open source — both this site and the agent. If you'd rather run your own inference.club instance instead of using the hosted one, the [deploy runbook](https://github.com/inference-club/inference.club/blob/main/infra/README.md) is the same as ours: Pulumi + Hetzner + docker compose.
