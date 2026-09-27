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
| `n` | no | How many images to generate (clamped server-side, max 4). |
| `size` | no | `WxH`, e.g. `1024x1024`. Models with the `custom-size` feature accept any size up to their limit — Qwen-Image 2.1 goes to 2048 per side (`2048x2048`, `2752x1536` for 16:9). |
| `response_format` | no | `url` (default) or `b64_json`. See [below](#response). |
| `seed` | no | Integer for reproducible sampling. Omit for a random seed (the one used comes back in `data[].seed` from providers that report it). |
| `steps` | no | Denoising steps, 1–100. Qwen-Image 2.1 defaults to 40. |
| `negative_prompt` | no | What to avoid. Turns on classifier-free guidance together with `guidance`. |
| `guidance` | no | Guidance scale (1–20), only meaningful with a `negative_prompt`. Qwen-Image 2.1 is meant to run *without* guidance; 4 is a good value when you do use it. |
| `background` | no | `transparent` asks for a real RGBA PNG (cutouts, stickers, logos) from models with the `transparent-background` feature; `opaque` is the default. |

Which of the optional knobs a model honours is listed in its `supported_features`
from `GET /v1/models` (`seed`, `steps`, `negative-prompt`, `transparent-background`,
`custom-size`, `image-edit`, `multi-reference`). Fields a model doesn't support are
ignored by that provider.

### curl

```bash
curl https://api.inference.club/v1/images/generations \
  -H "Authorization: Bearer $INFERENCE_CLUB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{ "model": "my-image-model", "prompt": "a watercolor fox", "size": "1024x1024" }'
```

A transparent sticker with a fixed seed from Qwen-Image 2.1:

```bash
curl https://api.inference.club/v1/images/generations \
  -H "Authorization: Bearer $INFERENCE_CLUB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{ "model": "qwen-image-2.1", "prompt": "a cartoon capybara in a wizard hat, sticker style",
        "background": "transparent", "seed": 42, "size": "1024x1024" }'
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
| `image` | yes | The source image to edit (png/jpeg/webp, up to 25 MB). For several references send repeated `image[]` parts (FLUX.2 Klein up to 8, Qwen-Image 2.1 up to 10) and refer to them as "image 1", "image 2", … in the prompt. |
| `prompt` | yes | How to change it. |
| `model` | yes | An image model id. |
| `mask` | no | Optional transparency mask. |
| `n`, `size`, `response_format` | no | As above. |
| `seed`, `steps`, `negative_prompt`, `guidance`, `background` | no | As above, sent as form fields. `background=transparent` with a prompt like "extract the subject as a cutout" returns an RGBA PNG from Qwen-Image 2.1. |

Qwen-Image 2.1 also takes region hints without a mask: draw a red circle on
the reference and say "replace what is inside the red circle", or pass a black
and white mask as a second reference ("image 2 is a mask; only change the white
region").

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
