---
title: Kubernetes agent
description: Run inference-club-agent in Kubernetes discovery mode — label your Services and the cluster reports itself, GPUs and all. No agent.yaml.
category: Providers
order: 3
---

# Kubernetes-native discovery

On Kubernetes you don't hand-write a manifest. You run `inference-club-agent`
in **kubernetes discovery mode** and the cluster *is* the manifest: the agent
lists Services you've tagged, follows each to the pod and node actually running
it, and reports the GPU model + VRAM straight from node labels. Add a service by
labeling it; scale it to zero and it drops off — no `agent.yaml` to maintain.

## What you'll set up

1. **GPU discovery** — Node Feature Discovery + GPU‑feature‑discovery so nodes
   self-report `nvidia.com/gpu.product` and `nvidia.com/gpu.memory`.
2. **The agent** — one Helm install, `discovery.mode: kubernetes`.
3. **Your services** — a few labels on each Service you want to advertise.

## Prerequisites

- A k3s (or other Kubernetes) cluster with GPU nodes.
- The **NVIDIA device plugin** running (`nvidia.com/gpu` shows up in
  `kubectl describe node`). Under k3s, run it with the `nvidia` RuntimeClass.
- `kubectl` admin access and an inference.club API key
  ([dashboard → settings → token](/dashboard/settings/token)).

## 1. Native GPU discovery (NFD + GFD)

GPU model and memory come from node labels written by NVIDIA's
**GPU‑feature‑discovery** (GFD), surfaced by **Node Feature Discovery** (NFD).
Install both:

```bash
# Node Feature Discovery (master + worker + CRDs)
kubectl apply -k "https://github.com/kubernetes-sigs/node-feature-discovery/deployment/overlays/default?ref=v0.16.6"

# Allow GFD's nvidia.com/* labels through nfd-master (default whitelist is
# feature.node.kubernetes.io only)
kubectl -n node-feature-discovery patch cm nfd-master-conf --type merge \
  -p '{"data":{"nfd-master.conf":"extraLabelNs: [\"nvidia.com\"]\n"}}'
kubectl -n node-feature-discovery rollout restart deploy/nfd-master

# GPU-feature-discovery — pinned to your device-plugin version. Run it with the
# nvidia RuntimeClass so it can read NVML, and (with NFD v0.16) target the
# pci-0300_10de label NFD adds to every NVIDIA GPU node.
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.17.4/deployments/static/gpu-feature-discovery-daemonset.yaml
```

> **k3s notes.** GFD needs `runtimeClassName: nvidia` (same as the device
> plugin) to read the GPU via NVML, and NFD v0.16 emits the PCI label as
> `feature.node.kubernetes.io/pci-0300_10de.present` rather than the older
> `pci-10de.present` the upstream GFD affinity hard-codes — patch the affinity
> to match, or label your GPU nodes `nvidia.com/gpu.present=true`.

Confirm the labels land:

```bash
kubectl get nodes -L nvidia.com/gpu.product,nvidia.com/gpu.memory,nvidia.com/gpu.count
# NAME   GPU.PRODUCT               GPU.MEMORY   GPU.COUNT
# a1     NVIDIA-GeForce-RTX-4090   24564        1
```

The agent reads exactly these, so every node's GPU shows up with zero agent
config.

> **Unified-memory boards (DGX Spark / GB10).** GFD can't read VRAM for the GB10
> (its memory is the unified system pool, so NVML returns *Not Supported*). Add
> an NFD `NodeFeatureRule` that sets `nvidia.com/gpu.memory` for GB10 nodes
> (PCI `10de:2e12`) to the node's RAM capacity in MiB.

## 2. Install the agent

```bash
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

Key values:

| Value | Meaning |
|---|---|
| `agentName` | The provider name this registers as (must match the dashboard). |
| `discovery.mode` | `kubernetes` — discover from labeled Services. |
| `discovery.namespace` | Namespace to watch (default: the release namespace). |
| `discovery.interval` | Re-list interval (default `30s`). `SIGHUP` forces a re-list. |
| `service.type` | `LoadBalancer` (k3s ServiceLB binds node LAN IPs for the backend). |

The chart ships the RBAC the agent needs (read Services, EndpointSlices, Pods,
named Secrets in the namespace; read Nodes cluster-wide).

## 3. Advertise a service — just label it

Tag any Service with the discovery labels and it appears on your provider. The
**only required label** is `inference-club.com/managed: "true"`.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: flux2-klein
  namespace: inference-club
  labels:
    inference-club.com/managed: "true"   # required — the discovery selector
    inference-club.com/type: image       # llm | stt | tts | image | mesh | music | video | scrape | audio-enhance
    inference-club.com/engine: other     # vllm | lmstudio | ollama | sglang | llamacpp | tgi | other
  annotations:
    inference-club.com/base-path: /v1                 # appended to the service URL
    inference-club.com/models: |                      # YAML list, same fields as a manifest model
      - id: flux-2-klein
        name: FLUX.2 Klein 4B
        input_modalities: [text, image]
        output_modalities: [image]
    # inference-club.com/features: "voice-cloning,dialogue"   # optional, comma list
    # inference-club.com/port: http                           # when the Service has several ports
    # inference-club.com/api-key-secret: lmstudio-key         # Secret whose `api-key` the agent sends upstream
spec:
  selector: { app: flux2-klein }
  ports:
    - { name: http, port: 8000 }
```

Everything else is **derived, not declared**:

| Field | Where it comes from |
|---|---|
| host address / hostname | the backing pod's node → Node addresses |
| GPU vendor / model / VRAM / count | node labels from GPU‑feature‑discovery |
| service URL | `http://<svc>.<ns>.svc.cluster.local:<port>` + `base-path` |
| launch command | the pod's image + command + args (exact, always current) |

A service with no running pod is simply left out — the manifest reports what's
actually serving. Scale a Deployment back up and it reappears on the next poll.

## 4. Verify

```bash
kubectl -n inference-club logs deploy/agent | grep "discovered manifest"
# discovered manifest from kubernetes (4 hosts, 7 services)
```

Within ~30s your provider lights up at **Dashboard → Compute → My nodes** and on
your public profile — each machine with its GPU, relative memory, and the
services it's running.

## Adding more compute

There's nothing agent-specific to touch: deploy a workload, put a labeled
Service in front of it, and it shows up. New GPU node? Once the device plugin +
GFD land on it, its model and VRAM self-report. That's the whole point — the
cluster describes itself.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Service missing from the manifest | No running pod behind it, or `inference-club.com/managed` not set. |
| GPU shows count but no model/VRAM | NFD/GFD not installed, or `nvidia.com` not in nfd-master's `extraLabelNs`. |
| GFD pod `Pending` / not scheduling | Affinity expects `pci-10de.present`; NFD v0.16 emits `pci-0300_10de.present`. Patch the affinity or label the node `nvidia.com/gpu.present=true`. |
| `401` in agent logs | Wrong/expired API key in the Secret. |
| Provider offline | The backend can't reach the agent's `LoadBalancer`/advertised address (tailnet or direct mode). |
