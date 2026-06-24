---
title: Image generation
description: Text-to-image and image edits over the OpenAI-compatible /v1/images endpoints.
category: API reference
order: 6
---

# Image generation

::api-endpoint{method="POST" path="/v1/images/generations"}

::api-endpoint{method="POST" path="/v1/images/edits"}

Generate images from a text prompt, or edit an existing image with a prompt, using any image model on the network. The endpoints mirror OpenAI's image API (`/v1/images/generations` takes JSON; `/v1/images/edits` takes multipart).

Requests are routed only to services a provider declared as `type: image`. inference.club stores every generated image in object storage and, by default, returns a URL you can drop straight into an `<img>` tag.

## Generations

`application/json`:

| Field | Required | Description |
|---|---|---|
| `prompt` | yes | The text description of the image. |
| `model` | yes | An image model id from `GET /v1/models`. |
| `n` | no | How many images to generate (clamped server-side). |
| `size` | no | e.g. `1024x1024`. Passed through to the provider. |
| `response_format` | no | `url` (default) or `b64_json`. See [below](#response). |

### curl

```bash
curl https://api.inference.club/v1/images/generations \
  -H "Authorization: Bearer $INFERENCE_CLUB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{ "model": "my-image-model", "prompt": "a watercolor fox", "size": "1024x1024" }'
```

### Python (openai SDK)

```python
from openai import OpenAI

client = OpenAI(base_url="https://api.inference.club/v1", api_key="<your-api-key>")
img = client.images.generate(model="my-image-model", prompt="a watercolor fox")
print(img.data[0].url)
```

## Edits

`multipart/form-data` — supply a source `image` (and optional `mask`) plus a `prompt`:

| Field | Required | Description |
|---|---|---|
| `image` | yes | The source image to edit (png/jpeg/webp, up to 25 MB). |
| `prompt` | yes | How to change it. |
| `model` | yes | An image model id. |
| `mask` | no | Optional transparency mask. |
| `n`, `size`, `response_format` | no | As above. |

```bash
curl https://api.inference.club/v1/images/edits \
  -H "Authorization: Bearer $INFERENCE_CLUB_API_KEY" \
  -F model=my-image-model \
  -F image=@photo.png \
  -F prompt="make the sky a sunset"
```

## Response

```json
{
  "created": 1780266332,
  "data": [ { "url": "https://api.inference.club/api/inference/assets/42/" } ]
}
```

- **`url` (default):** the image is stored on object storage and the response returns its URL, ready to drop into an `<img>` tag. Like every generation endpoint, `/v1/images/generations` and `/v1/images/edits` accept `visibility` and `collection` fields so you control who can see each image and how it's organized — see [Sharing](/docs/sharing).
- **`b64_json`:** set `response_format: b64_json` to also get the raw base64 bytes inline. The image is still stored.

Every request is recorded as an inference request with the prompt, the source image (for edits), and the output image(s), visible in your dashboard. Generation is metered by **image count**.

## Errors

| `type` | When | HTTP |
|---|---|---|
| `missing_prompt` | No `prompt` | 400 |
| `missing_file` | `/edits` with no `image` | 400 |
| `file_too_large` / `request_too_large` | Source image or prompt over the limit | 413 |
| `unsupported_media_type` | Source image isn't png/jpeg/webp | 415 |
| `no_provider` | No online image provider serves the model for you | 404 |
| `upstream_error` | The provider's image server failed | 502 |

## Async generation

Add `"async": true` to the request body to queue the image generation instead of waiting. Returns `202 Accepted` with a job envelope. Poll `GET /v1/jobs/<id>` for status, then read `result_url` when done. See [Async jobs](/docs/api/jobs).

## Not supported (yet)

`/v1/images/variations` and streaming/progressive previews.
