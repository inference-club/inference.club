---
title: GET /v1/models
description: List the models available to your account right now.
category: API reference
order: 2
---

# `GET /v1/models`

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
      "owned_by": "home-rig"
    },
    {
      "id": "llama-3.1-8b-instruct",
      "object": "model",
      "created": 1729960500,
      "owned_by": "office-3090"
    }
  ]
}
```

`owned_by` is the **provider name** that's serving the model — useful when you have multiple providers. If two providers serve the same `id`, only one entry appears (first writer wins).

## Empty list?

If `data` is empty, no agent on your account is currently advertising any model. Either:

- Your agent isn't running — start it.
- Your agent isn't reaching inference.club — check its `INFERENCE_CLUB_URL` env var and look at agent logs.
- More than 60 seconds have passed since the last heartbeat — the provider is marked offline.

The `/providers/my-nodes` page in the dashboard is the easiest way to see the heartbeat status of each of your agents.
