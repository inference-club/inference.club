---
title: GET /v1/catalog
description: Every node, service and model the club can reach for you, grouped by type.
category: API reference
order: 2.5
---

# `GET /v1/catalog`

::api-endpoint{method="GET" path="/v1/catalog"}

Where [`/v1/models`](/docs/api/models) is a flat, OpenAI-shaped list of model ids, the catalog shows the topology behind them: which **nodes** (machines and their GPUs) exist, which **services** run on each, what models each service serves, and whether it is ready right now. Use it to discover "what image model can I call?" without trial and error.

It is built from what providers' agents already report: the uploaded manifest (hosts, GPUs, services, and each model's declared `id`, `name`, modalities, features and context length) plus heartbeat liveness. You see your own providers in full and other members' services that you have access to. Any valid API key works.

## Request

```bash
curl https://api.inference.club/v1/catalog \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

## Response

```json
{
  "generated_at": "2026-11-14T18:59:48Z",
  "nodes": [
    {
      "name": "spark",
      "provider": "club-host",
      "gpus": [{ "name": "NVIDIA GB10", "memory_gb": 128.0 }],
      "online": true,
      "last_seen": "2026-11-14T18:59:40Z"
    }
  ],
  "services": [
    {
      "type": "llm",
      "name": "vllm-spark",
      "node": "spark",
      "provider": "club-host",
      "engine": "vllm",
      "endpoint_kind": "/v1/chat/completions",
      "ready": true,
      "models": [
        {
          "id": "nemotron-3-super",
          "name": "Nemotron 3 Super",
          "input_modalities": ["text"],
          "output_modalities": ["text"],
          "features": ["reasoning", "tools"],
          "context_length": 131072
        }
      ]
    }
  ],
  "by_type": { "llm": ["nemotron-3-super"] }
}
```

| Field | Meaning |
|---|---|
| `nodes[].online` | The node's agent has sent a heartbeat in the last two minutes (and, when a recent cluster snapshot is cached, the node reports ready). `last_seen` is the agent's last heartbeat. |
| `services[].type` | `llm`, `asr`, `tts`, `image`, `music`, `video`, `3d`, or `other`. Comes from the manifest's `type`; an untyped service is classified by its models' modalities. |
| `services[].endpoint_kind` | The `/v1` endpoint requests to this service are routed from (follows the manifest's declared `type`). |
| `services[].ready` | The node is online and accepting requests and the service has active models; a parked (scaled-to-zero) service in a cached cluster snapshot is not ready. |
| `by_type` | Model ids grouped by service type, across every listed service (ready or not). |

Fields with no value are omitted (for example `context_length` on image models, `memory_gb` when a manifest doesn't declare VRAM).
