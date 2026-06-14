---
title: Music generation
description: POST /v1/music/generations — generate a song from a prompt and optional lyrics.
category: API reference
order: 8
---

# `POST /v1/music/generations`

Generate music from a text prompt, with optional lyrics. Routes to providers running a `music` service (ACE-Step). The response is the **raw audio bytes** (`audio/mpeg` by default) — not JSON.

## Request

```bash
curl https://api.inference.club/v1/music/generations \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ace-step",
    "prompt": "dreamy lo-fi hip-hop with mellow piano and soft vinyl crackle",
    "lyrics": "[verse]\nNeon rain on the window...",
    "audio_duration": 60
  }' \
  --output song.mp3
```

| Field | Type | Notes |
| --- | --- | --- |
| `model` | string | **Required.** A model with `service_type: music` from `GET /v1/models`. |
| `prompt` | string | **Required.** Style, mood, instruments. |
| `lyrics` | string | Optional. Use `[verse]` / `[chorus]` section tags. |
| `audio_duration` | number | Seconds, 5–300. Omit to let the model decide. |
| `audio_format` | string | `mp3` (default), `wav`, `flac`, `opus`, `aac`. |
| `inference_steps` | integer | 1–200, default 8. |
| `guidance_scale` | number | 0–30, default 7. |
| `seed` | integer | Fixed seed; or `use_random_seed: true` (default). |
| `bpm` | integer | Optional tempo hint. |
| `key_scale` | string | Optional, e.g. `"C major"`. |
| `vocal_language` | string | Optional, e.g. `"en"`. |

Also accepts the [`visibility` and `collection` sharing fields](/docs/sharing).

## Response

The finished audio, streamed back with `Content-Disposition: inline`. The request and its audio are stored in your dashboard (and in **Dashboard → Music**) for replay, sharing, and playlists.

Errors use the standard [error format](/docs/api/overview): `404 no_provider` when no online provider serves the model, `413` when prompt + lyrics are too long.
