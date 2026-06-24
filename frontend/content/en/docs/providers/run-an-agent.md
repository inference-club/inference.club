---
title: Run an agent
description: Deploy inference-club-agent on Kubernetes in discovery mode and watch your cluster register itself — GPUs, services, and all.
category: Providers
order: 2
---

# Run an agent

The `inference-club-agent` runs on **Kubernetes**. You install it once in
discovery mode, label the Services you want to share, and the cluster
*describes itself* to inference.club — GPU model, VRAM, the launch command
behind each service, all read live from the cluster.

> **Heads up — this changed.** Earlier versions of the agent shipped as a
> single Docker container configured with environment variables or an
> `agent.yaml` manifest, often via `docker compose`. **That path has been
> retired.** There's no `agent.yaml` to write and no compose file to maintain —
> the agent reads everything from the cluster. If you're coming from the old
> setup, this page is the replacement.

## How it works

Instead of hand-writing a manifest, you run the agent in **kubernetes discovery
mode**. The agent:

1. Lists the Services in your namespace that carry the
   `inference-club.com/managed: "true"` label.
2. Follows each Service to the pod and node actually running it, and reads the
   GPU model + VRAM straight from node labels.
3. Heartbeats the resulting picture to inference.club every ~30 seconds.

Add a service by labeling it. Scale it to zero and it drops off the next poll.
There's no agent config to keep in sync with reality — the cluster *is* the
manifest.

## Prerequisites

- A **k3s** (or any other Kubernetes) cluster with GPU nodes.
- The **NVIDIA device plugin** running, so `nvidia.com/gpu` appears in
  `kubectl describe node`. Under k3s, run it with the `nvidia` RuntimeClass.
- `kubectl` admin access.
- An inference.club API key — [dashboard → settings → token](/dashboard/settings/token).

A single GPU box is enough; "cluster" can be one node. If you don't have
Kubernetes yet, k3s installs in one command and is the path we use across the
home fleet.

## 1. Install the agent

Put your API key in a Secret, then install the chart with
`discovery.mode=kubernetes`:

```bash
kubectl create namespace inference-club

kubectl create secret generic inference-club-agent \
  --namespace inference-club \
  --from-literal=api-key=<your-key>

helm install agent oci://ghcr.io/inference-club/charts/inference-club-agent \
  --namespace inference-club \
  --set agentName=club-host-k8s \
  --set apiKey.existingSecret=inference-club-agent \
  --set discovery.mode=kubernetes \
  --set discovery.namespace=inference-club
```

The chart ships the RBAC the agent needs (read Services, EndpointSlices, Pods,
and named Secrets in the namespace; read Nodes cluster-wide). The most useful
values:

| Value | Meaning |
|---|---|
| `agentName` | The provider name this registers as. |
| `discovery.mode` | `kubernetes` — discover from labeled Services. |
| `discovery.namespace` | Namespace to watch (default: the release namespace). |
| `discovery.interval` | Re-list interval (default `30s`). |

## 2. Advertise a service — just label it

Tag any Service with the discovery labels and it appears on your provider. The
**only required label** is `inference-club.com/managed: "true"`.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: vllm-qwen
  namespace: inference-club
  labels:
    inference-club.com/managed: "true"   # required — the discovery selector
    inference-club.com/type: llm         # llm | stt | tts | image | music | video | mesh | scrape | audio-enhance
    inference-club.com/engine: vllm      # vllm | lmstudio | ollama | sglang | llamacpp | tgi | other
  annotations:
    inference-club.com/base-path: /v1
    inference-club.com/models: |
      - id: qwen3-30b-a3b
        hf: Qwen/Qwen3-30B-A3B
        name: Qwen3 30B A3B
        features: [reasoning, tools]
spec:
  selector: { app: vllm-qwen }
  ports:
    - { name: http, port: 8000 }
```

Everything else — the host address, GPU model/VRAM, the service URL, and the
exact launch command — is **derived from the cluster, not declared**. A Service
with no running pod is simply left out; scale the Deployment back up and it
reappears on the next poll.

## 3. Verify

```bash
kubectl -n inference-club logs deploy/agent | grep "discovered manifest"
# discovered manifest from kubernetes (4 hosts, 7 services)
```

Within ~30s your provider lights up at **Dashboard → Compute → My nodes** and on
your public profile, each machine showing its GPU, relative memory, and the
services it's running.

## Going further

- **[Running the agent on Kubernetes](/docs/providers/kubernetes-agent)** — the
  full walkthrough: native GPU discovery with Node Feature Discovery +
  GPU-feature-discovery (so GPU model and VRAM self-report), the complete
  Service label/annotation reference, multi-modal services (STT, TTS, image,
  video, music, voice cloning), unified-memory boards like the DGX Spark, and a
  troubleshooting table.
- **[Become a provider](/docs/providers/overview)** — how heartbeats and
  proxied requests work under the hood.

## Updating

Pull the latest chart and upgrade in place:

```bash
helm upgrade agent oci://ghcr.io/inference-club/charts/inference-club-agent \
  --namespace inference-club --reuse-values
```

The agent heartbeats back in within ~30 seconds and your provider record picks
up where it left off.
