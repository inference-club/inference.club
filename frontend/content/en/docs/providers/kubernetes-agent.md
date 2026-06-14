---
title: Kubernetes agent
description: Deploy inference-club-agent as a Kubernetes Deployment, with GPU scheduling and a manifest ConfigMap.
category: Providers
order: 3
---

# Running the agent on Kubernetes (k3s)

This guide walks through deploying `inference-club-agent` on a Kubernetes cluster — including a home cluster running k3s. The setup stores the agent manifest in a ConfigMap and schedules the agent on a GPU node.

## Prerequisites

- A running k3s (or other Kubernetes) cluster.
- A node with a GPU and drivers installed (CUDA or ROCm). The node should be labeled so the agent pod can be scheduled there.
- `kubectl` configured against your cluster.
- An inference.club API key (see [Quickstart](/docs/quickstart)).

## 1. Label your GPU node

```bash
kubectl label node <your-gpu-node-name> inference.club/gpu=true
```

This lets you target the agent pod to GPU hardware via a `nodeSelector`.

## 2. Create the API key secret

```bash
kubectl create secret generic inference-club-agent-secret \
  --from-literal=INFERENCE_CLUB_API_KEY=<your-key>
```

## 3. Create the agent manifest ConfigMap

The agent manifest declares which local services to advertise. Save this as `agent-manifest.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: inference-club-agent-manifest
data:
  agent.yaml: |
    hosts:
      - id: k3s-home-cluster
        services:
          - name: vllm-qwen
            engine: vllm
            url: http://localhost:8000/v1
            models:
              - hf: Qwen/Qwen3-8B

          - name: dia-voice
            type: tts
            engine: dia
            url: http://localhost:7860/v1
            features: [voice-cloning]
            models:
              - id: nari-labs/Dia-1.6B

          - name: ltx-video
            type: video
            url: http://localhost:8003/v1
            models:
              - id: Lightricks/LTX-Video-2
```

Apply it:

```bash
kubectl apply -f agent-manifest.yaml
```

## 4. Deploy the agent

Save this as `agent-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inference-club-agent
  labels:
    app: inference-club-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: inference-club-agent
  template:
    metadata:
      labels:
        app: inference-club-agent
    spec:
      nodeSelector:
        inference.club/gpu: "true"
      containers:
        - name: agent
          image: ghcr.io/inference-club/inference-club-agent:latest
          env:
            - name: INFERENCE_CLUB_URL
              value: "https://api.inference.club"
            - name: INFERENCE_CLUB_API_KEY
              valueFrom:
                secretKeyRef:
                  name: inference-club-agent-secret
                  key: INFERENCE_CLUB_API_KEY
            - name: AGENT_NAME
              value: "home-k3s"
            - name: AGENT_CALLBACK_URL
              value: "http://<your-node-ip>:8002/v1"
            - name: AGENT_MANIFEST
              value: "/config/agent.yaml"
          volumeMounts:
            - name: agent-manifest
              mountPath: /config
          ports:
            - containerPort: 8002
      volumes:
        - name: agent-manifest
          configMap:
            name: inference-club-agent-manifest
```

Apply it:

```bash
kubectl apply -f agent-deployment.yaml
```

## 5. Expose the agent callback

inference.club needs to reach your agent's callback URL from the internet. On a home cluster without a public IP, use one of:

- **Tailscale:** install the Tailscale k3s operator or run a `tailscale` sidecar container and use the Tailscale node's address.
- **Cloudflare Tunnel:** deploy `cloudflared` in the cluster and create a tunnel pointing to the agent service.
- **NodePort + router port-forward:** expose port 8002 as a NodePort, then forward it on your router.

## 6. Verify

```bash
kubectl get pods -l app=inference-club-agent
kubectl logs -f deployment/inference-club-agent
```

Within 30 seconds of the pod becoming `Running`, the agent heartbeats into inference.club and your provider appears in the dashboard.

## Updating

```bash
kubectl rollout restart deployment/inference-club-agent
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `401` in agent logs | Wrong or expired API key in the secret. |
| Provider shows offline | `AGENT_CALLBACK_URL` is not reachable from the inference.club server — check your tunnel or port-forward. |
| No models advertised | The `agent.yaml` in the ConfigMap doesn't match the services actually running on that node. |
| Pod stuck in `Pending` | No node matches the `nodeSelector` — check your GPU node label. |

## GPU scheduling

If your cluster has multiple GPU nodes with different capabilities, use additional labels and a more specific `nodeSelector` or `affinity` block to steer each agent to the right node:

```bash
kubectl label node spark nvidia.com/gpu-model=RTX4090
```

```yaml
nodeSelector:
  inference.club/gpu: "true"
  nvidia.com/gpu-model: RTX4090
```
