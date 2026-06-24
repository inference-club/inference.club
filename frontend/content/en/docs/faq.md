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

- **Async job**: a single inference request that runs in the background. Add `"async": true` to any JSON-bodied call.
- **Batch**: up to 256 async requests submitted as one unit — useful for bulk generation.
- **Workflow**: a DAG of steps that chain together, fan out (one image per list item), do inline data transforms, and can pause for human review (gate steps). Workflows are the right tool when each request's output feeds the next.

See the [jobs](/docs/api/jobs), [batches](/docs/api/batches), and [workflows](/docs/api/workflows) references.

### What happens if my agent goes offline mid-request?

Synchronous request: fails with `502 upstream_error`. Subsequent requests fail with `404 no_provider` until the agent comes back. Async job: remains `QUEUED` until a provider comes online. There's no automatic failover to a second provider.

### Can other people use my agent's hardware?

No. inference.club only routes a user's requests to that user's own providers. Your hardware serves your inferences.

That model will probably evolve as the community grows (the whole point is shared compute), but for now it's strictly per-user.

### How is usage metered?

Every successful proxied request is recorded as an `InferenceRequest` row tied to your user, with model name and latency. Billing and quotas aren't enforced yet.

### What about rate limits?

None in the MVP. Don't be a jerk about it.

### How does the agent run — Docker or Kubernetes?

Kubernetes. The agent runs in **discovery mode**: you install it once with Helm, label the Services you want to share, and it reports them — including each one's GPU — read live from the cluster. The older single-container Docker / `agent.yaml` path has been retired. See [Run an agent](/docs/providers/run-an-agent) and the [Kubernetes deep-dive](/docs/providers/kubernetes-agent). A single GPU box running k3s counts as a cluster.

### Where do I report bugs?

GitHub: <https://github.com/inference-club/inference.club/issues> for the platform; <https://github.com/inference-club/inference-club-agent/issues> for the agent.

### Is there a self-hosted option?

The whole platform is open source — both this site and the agent. If you'd rather run your own inference.club instance instead of using the hosted one, the [deploy runbook](https://github.com/inference-club/inference.club/blob/main/infra/README.md) is the same as ours: Pulumi + Hetzner + docker compose.
