---
title: Video generation
description: POST /v1/videos/generations — text-to-video and image-to-video.
category: API reference
order: 9
---

# `POST /v1/videos/generations`

Generate a short video from a text prompt, optionally conditioned on a first-frame image. Routes to providers running a `video` service (LTX-2). The response is the **raw MP4 bytes** — not JSON. Video generation is slow; expect minutes, not seconds.

## Request

```bash
curl https://api.inference.club/v1/videos/generations \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ltx-2",
    "prompt": "a paper boat drifting down a rain-soaked gutter, cinematic",
    "duration": 6,
    "fps": 24
  }' \
  --output video.mp4
```

| Field | Type | Notes |
| --- | --- | --- |
| `model` | string | **Required.** A model with `service_type: video` from `GET /v1/models`. |
| `prompt` | string | **Required.** |
| `negative_prompt` | string | Optional. |
| `image` | string | Optional first frame for image-to-video: a `data:` URI or raw base64. |
| `image_strength` | number | 0–1, default 1. How strongly the image constrains the result. |
| `duration` | number | Seconds, 1–20. |
| `num_frames` / `fps` | integer | Alternative to `duration`; frames ≤ 1281, fps ≤ 60. |
| `width` / `height` | integer | 64–1920. |
| `num_inference_steps` | integer | 1–100. |
| `guidance_scale` | number | 0–30. |
| `enhance_prompt` | boolean | Let the server expand your prompt. |
| `seed` | integer | Optional fixed seed. |

Also accepts the [`visibility` and `collection` sharing fields](/docs/sharing).

## Response

The finished video (`video/mp4`), with the actual resolved parameters (frames, fps, resolution) recorded on the stored request. Generated videos appear in **Dashboard → Watch** and can be organized into playlists via [collections](/docs/sharing).

Errors use the standard [error format](/docs/api/overview): `404 no_provider` when no online provider serves the model, `502 upstream_error` if the provider fails mid-render.
