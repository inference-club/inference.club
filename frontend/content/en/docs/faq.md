---
title: FAQ
description: Common questions and gotchas.
category: Reference
order: 9
---

# FAQ

### Is this OpenAI-compatible?

Yes. The `/v1/...` surface mirrors OpenAI's request and response shapes for chat completions, completions, and `/models`. Anything that talks to `api.openai.com` should work against `api.inference.club/v1` with just a base URL and key change. Non-text modalities (music, video, voice) use the same REST conventions but are inference.club extensions — no OpenAI equivalent.

### Can I use the same API key for inference and for my agent?

Yes. One key per user covers both directions. Your agent uses it to heartbeat in; your client uses it to do inference. There's no separate "provider key" vs "consumer key" concept.

### What models can I run?

Anything your local server can serve. For LLMs that's any OpenAI-compatible server (vLLM, Ollama, LM Studio, llama.cpp). For other modalities, you label the Kubernetes Service with its type — `tts`, `stt`, `image`, `music`, `video`, `mesh`, `audio-enhance`, `scrape` — and the agent routes each upstream call to the matching in-cluster server. See [Run an agent](/docs/providers/run-an-agent).

### What modalities does inference.club support beyond LLMs?

Text, speech-to-text, text-to-speech, image generation, image editing, music generation (ACE-Step), video generation (LTX-2), voice cloning (Dia), and 3D mesh generation. Each modality needs a provider running the matching service type. See [Concepts → Service type](/docs/concepts).

### What is voice cloning and how do I use it?

Voice cloning lets you provide short audio samples for one or two speakers, and the Dia model synthesizes a dialogue that sounds like them. Upload samples in **Dashboard → Voice library**, then call `/v1/voice/generations` with a `[S1]`/`[S2]` tagged script and `"speakers": { "S1": <sample-id> }`. See the [voice generations reference](/docs/api/voice-generations).

### What's the difference between async jobs, batches, and workflows?

- **Async job**: a single inference request that runs in the background. Add `"async": true` (always queue) or `"async": "auto"` (queue only when the GPU is busy) to an async-capable call — chat, completions, images, video, music, speech, scrape.
- **Batch**: up to 256 async requests submitted as one unit — useful for bulk generation.
- **Workflow**: a DAG of steps that chain together, fan out (one image per list item), do inline data transforms, and can pause for human review (gate steps). Workflows are the right tool when each request's output feeds the next.

See the [jobs](/docs/api/jobs), [batches](/docs/api/batches), and [workflows](/docs/api/workflows) references.

### What happens if my agent goes offline mid-request?

Synchronous request: fails with `502 upstream_error`. Subsequent requests fail with `404 no_provider` until the agent comes back — unless you send `"async": "auto"`, which queues the request for up to an hour while the provider returns. An async job that hits a transient failure is retried with backoff (up to 3 attempts). There's no automatic failover to a second provider for a synchronous call.

### Can other people use my agent's hardware?

Only if you share it. Each service you run has an access policy: **private** (the default — only you), **any signed-in member**, or a **restricted** allowlist of GitHub usernames. Shared services show up in those members' `GET /v1/models` and their requests route to your hardware. Either way, your service's declared `max_concurrent` caps how many requests it receives at once.

### How is usage metered?

Every successful proxied request is recorded as an `InferenceRequest` row tied to your user, with model name and latency. Billing and quotas aren't enforced yet.

### What about rate limits?

Yes: by default 60 inference requests per minute per account (15 for guest accounts) and 120 `GET /v1/models` calls per minute. Every response carries `X-RateLimit-Limit` / `-Remaining` / `-Reset` headers, and a throttled request returns `429` with `Retry-After`. Separately, a busy GPU returns `429 at_capacity` — see [Capacity](/docs/services/direct-vs-async#capacity).

### How does the agent run — Docker or Kubernetes?

Kubernetes. The agent runs in **discovery mode**: you install it once with Helm, label the Services you want to share, and it reports them — including each one's GPU — read live from the cluster. The older single-container Docker / `agent.yaml` path has been retired. See [Run an agent](/docs/providers/run-an-agent) and the [Kubernetes deep-dive](/docs/providers/kubernetes-agent). A single GPU box running k3s counts as a cluster.

### Where do I report bugs?

GitHub: <https://github.com/inference-club/inference.club/issues> for the platform; <https://github.com/inference-club/inference-club-agent/issues> for the agent.

### Is there a self-hosted option?

The whole platform is open source — both this site and the agent. If you'd rather run your own inference.club instance instead of using the hosted one, the [deploy runbook](https://github.com/inference-club/inference.club/blob/main/infra/README.md) is the same as ours: Pulumi + Hetzner + docker compose.
