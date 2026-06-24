---
title: The home cluster
description: The k3s GPU fleet that actually runs the models — and how it describes itself to the network.
category: Architecture
order: 2
---

# The home cluster

The compute behind the reference deployment is a small **k3s** cluster of GPU machines on one home LAN. It runs every model the network serves and reports itself to the control plane through the agent — but it has no public address and accepts no inbound connections. This page is about how that side works. To run your *own* cluster, see [Run an agent](/docs/providers/run-an-agent).

## The fleet

The reference cluster is four boxes — three amd64 workstations with RTX 4090s and an arm64 DGX Spark with a GB10 superchip and unified memory:

| Node | GPU | Role |
|---|---|---|
| a3 | RTX 4090 | control plane + workloads |
| a1 | RTX 4090 | workloads |
| a2 | RTX 4090 | workloads |
| spark | DGX Spark (GB10) | workloads |

Each model service runs as a Kubernetes Deployment fronted by a Service: vLLM and LM Studio for language models, plus diffusion and generative services for image, video, music, voice, speech, transcription, and 3D. Services load on demand, so a 4090 isn't pinned to one model forever.

## GPU facts come from the cluster, not config

The agent never hand-types what GPU a service runs on. **Node Feature Discovery** and NVIDIA's **GPU-feature-discovery** label every node with its GPU model, memory, and count, read straight from the hardware. The agent reads those labels, so each service shows up on your profile with the right GPU automatically.

::callout{type="note" title="Unified-memory boards are special"}
The GB10 DGX Spark has no dedicated VRAM — its memory is a shared 128 GB system pool, which NVML reports as "not supported." A small node rule labels it with the right memory figure so it reports correctly alongside the discrete GPUs. A separate VRAM-reporter runs on every node to attribute live GPU memory back to the pod (and service) using it.
::

## The cluster is the manifest

The agent runs in **kubernetes discovery mode**. Rather than reading a static config file, every ~30 seconds it lists the Services you've labeled `inference-club.com/managed: "true"`, follows each to the pod and node actually running it, and assembles a live picture:

- the **service type** and **model list** from the Service's labels and annotations,
- the **service URL** as the in-cluster DNS name,
- the **GPU** from the backing node's discovery labels,
- the exact **launch command** from the running pod's image and args.

It pushes that picture to the control plane and atomically swaps its internal router. The effect: scale a Deployment up and it appears on the network; scale it to zero and it drops off — no agent config to keep in sync with reality. This is what makes the catalog and routing always reflect what's truly online.

## Observability

The cluster runs its own monitoring stack — Prometheus and Grafana, per-GPU metrics from dcgm-exporter, node metrics, and Phoenix for LLM traces and evals. A subset of cluster state (node conditions, GPU allocatable, pod phases) is also exposed to the control plane, which powers the live [cluster visualization](/docs/playground/overview) on the dashboard and public profiles.

## What this buys

Because the cluster self-describes and stays sealed, adding compute is almost nothing: deploy a workload, put a labeled Service in front of it, and it shows up. A new GPU node self-reports its hardware the moment the device plugin and discovery land on it. The cluster, not a config file, is the source of truth.
