---
title: Quickstart
description: From zero to your first inference request in five minutes.
order: 2
---

# Quickstart

This guide assumes you want to **use** the network — call models that other people are hosting. If you want to be a provider too, also see [Run an agent](/docs/providers/run-an-agent).

## 1. Get an API key

Sign in at <https://inference.club/login> with GitHub. Once you're in, go to **Dashboard → Settings → Token** and click **Create token**. Copy the value — you'll only see it once.

API keys look like `2cbedf618e82c0ede2c2fa6e05151b7513cd20c4`. Treat them like passwords; anyone with the key can use the network as you and incurs your usage.

## 2. List available models

```bash
export INFERENCE_CLUB_KEY=<your-key>

curl https://api.inference.club/v1/models \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

You'll get back an OpenAI-format list of every model that an online agent on the network is currently advertising:

```json
{
  "object": "list",
  "data": [
    { "id": "qwen3-8b", "object": "model", "created": 1729960000, "owned_by": "home-rig" }
  ]
}
```

If the list is empty, no agents on the network are advertising models for you yet. If you have your own agent registered, see [Run an agent](/docs/providers/run-an-agent).

## 3. Run a chat completion

```bash
curl https://api.inference.club/v1/chat/completions \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-8b",
    "messages": [
      { "role": "user", "content": "Say hello in one word." }
    ]
  }'
```

That's it. The response is in the standard OpenAI chat completion format — same as you'd get from `api.openai.com`.

## 4. Use it from the OpenAI SDK

Anything that speaks OpenAI works. Python:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.inference.club/v1",
    api_key="<your-key>",
)

resp = client.chat.completions.create(
    model="qwen3-8b",
    messages=[{"role": "user", "content": "Say hello in one word."}],
)
print(resp.choices[0].message.content)
```

Streaming works the same way it does with OpenAI:

```python
stream = client.chat.completions.create(
    model="qwen3-8b",
    messages=[{"role": "user", "content": "Count to ten."}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

## 5. Point Open WebUI at it

In Open WebUI: **Settings → Connections → OpenAI API** → set the base URL to `https://api.inference.club/v1` and paste your key. The model dropdown will show whatever your providers are serving.
