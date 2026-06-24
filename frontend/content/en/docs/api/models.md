---
title: GET /v1/models
description: List the models available to your account right now.
category: API reference
order: 2
---

# `GET /v1/models`

::api-endpoint{method="GET" path="/v1/models"}

Returns every model currently served by an online provider belonging to you. OpenAI-format response — drop-in compatible with anything that calls `/models` to populate a dropdown.

## Request

```bash
curl https://api.inference.club/v1/models \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

## Response

```json
{
  "object": "list",
  "data": [
    {
      "id": "qwen3-8b",
      "object": "model",
      "created": 1729960000,
      "owned_by": "home-rig",
      "service_type": "llm",
      "input_modalities": ["text"],
      "output_modalities": ["text"],
      "supported_features": ["tools", "streaming"],
      "context_length": 32768
    },
    {
      "id": "llama-3.1-8b-instruct",
      "object": "model",
      "created": 1729960500,
      "owned_by": "office-3090",
      "service_type": "llm",
      "input_modalities": ["text"],
      "output_modalities": ["text"],
      "supported_features": ["streaming"],
      "context_length": 131072
    }
  ]
}
```

`owned_by` is the **provider name** that's serving the model — useful when you have multiple providers. If two providers serve the same `id`, only one entry appears (first writer wins).

Beyond the OpenAI baseline fields, each entry carries the model's capabilities — `service_type`, `input_modalities`, `output_modalities`, `supported_features`, and `context_length` — so a caller can pick a model programmatically (e.g. "an `image` model that accepts a mask," or an `llm` with `tools`). These capabilities are **declared by the operator** who runs the model and are never guessed.

## Empty list?

If `data` is empty, no agent on your account is currently advertising any model. Check that:

- Your agent is running and shows as **online** in the dashboard (**Dashboard → Compute → My nodes**).
- Its Kubernetes model services are labeled so the agent discovers them, and each has a running pod backing it.
- A heartbeat has landed recently — if the agent stopped beaconing, the provider is marked offline.

The [My nodes](/dashboard/providers/my-nodes) page in the dashboard is the easiest way to see the heartbeat status of each of your agents.
