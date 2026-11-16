---
title: Voice cloning
description: POST /v1/voice/generations — Dia voice cloning and multi-speaker dialogue synthesis.
category: API reference
order: 10
---

# `POST /v1/voice/generations`

::api-endpoint{method="POST" path="/v1/voice/generations"}

Synthesize expressive, cloned speech using [Dia](https://github.com/nari-labs/dia). Dia is a text-to-dialogue model that takes a multi-speaker script and, optionally, short audio clips from your voice library to clone one or two speakers. Routes only to `tts` providers advertising the `voice-cloning` feature.

## Request

```bash
curl https://api.inference.club/v1/voice/generations \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "[S1] Hello! Welcome to the show.\n[S2] Thanks for having me.",
    "speakers": {
      "S1": 12,
      "S2": 17
    }
  }' \
  --output dialogue.wav
```

| Field | Type | Notes |
|---|---|---|
| `input` | string | **Required.** The dialogue script (see [Script format](#script-format)). |
| `model` | string | Optional. A model id with the `voice-cloning` feature from `GET /v1/models`. Omit to auto-select. |
| `speakers` | object | Optional. Maps speaker tags (`"S1"`, `"S2"`) to voice-sample IDs from your library. |
| `cfg_scale` | number | 1–5, default 3.0. How strongly the model follows the transcript. |
| `temperature` | number | 0.1–2.0, default 1.8. Higher = more expressive, lower = more consistent. |
| `top_p` | number | 0.1–1.0, default 0.95. Nucleus sampling threshold. |
| `cfg_filter_top_k` | integer | 1–100, default 45. |
| `speed_factor` | number | 0.5–2.0, default 1.0. Speaking rate. |
| `max_new_tokens` | integer | 256–4096, default 3072. |
| `seed` | integer | Fixed seed for reproducibility. Omit (or `-1`) for random. |
| `delivery` | string | `bytes` (default) or `url` — see [below](#getting-a-url-instead-of-bytes). |

Also accepts the [`visibility` and `collection` sharing fields](/docs/sharing).

## Script format

The `input` field is a dialogue script. Each line is prefixed with a speaker tag:

```
[S1] Hello! Welcome to the show.
[S2] Thanks for having me. It's great to be here.
[S1] So, tell me about your project.
```

- Use `[S1]` for the first speaker and `[S2]` for the second.
- A script with no `[S*]` tags is treated as a single `[S1]` monologue.
- Speaker tags `[S3]` and above are not yet supported.
- Lines must start with `[S1]` — you can't open with `[S2]`.

## Voice samples

Voice samples let you clone a real voice for S1 and/or S2. A sample is a short audio clip (a few seconds of the speaker talking) stored in your account's **voice library** at **Dashboard → Voice library**.

When you reference a sample via `"speakers": { "S1": <id> }`, the engine:

1. Fetches the sample's audio and transcript from your library.
2. Transcodes the audio to WAV if needed (browser recordings are webm/opus).
3. Concatenates S1 and S2 clips (if both are cloned) with a short silence gap.
4. Passes the assembled audio + transcript to Dia as an audio prompt.

If a sample has no transcript, the request is rejected — Dia needs the transcript to do cloning. The dashboard auto-fills the transcript when a sample is uploaded, using an STT model if one is available.

## Response

The finished audio as `audio/wav` bytes, as long as the dialogue requires. The request is stored in your dashboard history.

This endpoint is **synchronous only** — it doesn't accept `async`. In a [workflow](/docs/api/workflows), a `voice` step runs Dia through the job queue.

## Getting a URL instead of bytes

Add `"delivery": "url"` to get JSON instead of the raw file — easier for agents and scripts that only need a link:

```json
{
  "object": "inference.result",
  "id": "8812",
  "public_id": "kQ3v9xZp1aE",
  "inference_type": "VOICE",
  "model": "dia",
  "status": "PROCESSED",
  "created": 1780266332,
  "data": [{ "id": 551, "kind": "audio", "url": "https://…", "content_type": "audio/wav", "duration_seconds": 8.1 }]
}
```

With the default `"delivery": "bytes"`, the response headers still name the stored copy: `X-Inference-Request-Id` (pollable at `GET /v1/jobs/<id>`), `X-Asset-Id`, and `X-Asset-Url`.

## Errors

| `type` | When | HTTP |
|---|---|---|
| `missing_input` | No `input` field | 400 |
| `invalid_script` | Script starts with `[S2]`, uses `[S3+]`, etc. | 400 |
| `invalid_voice_sample` | A speaker id doesn't exist or doesn't belong to you | 400 |
| `missing_transcript` | A referenced voice sample has no transcript | 400 |
| `audio_decode_failed` | A voice sample's audio couldn't be decoded | 400 |
| `request_too_large` | Input text over the character limit | 413 |
| `no_provider` | No online voice-cloning provider available | 404 |
| `at_capacity` | Every slot on the device is busy (after a ~20s wait). Honor `Retry-After` | 429 |
| `upstream_error` | The Dia server failed | 502 |

## Managing voice samples

Manage samples in the dashboard (**Dashboard → Voice library**) or over the API with the same Bearer key (these live under `/api/inference/`, not `/v1`):

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/inference/voice-samples/` | List your samples — `id` is what `speakers` takes. |
| `POST` | `/api/inference/voice-samples/` | Upload one: multipart `audio` file plus optional `speaker_name`, `transcript`, `label`, `language`, `is_default`. With no `transcript`, one is auto-filled via your STT service if you have one. |
| `GET` / `PATCH` / `DELETE` | `/api/inference/voice-samples/<id>/` | Read, edit (transcript, label, language, speaker, default), or delete a sample. |
| `POST` | `/api/inference/voice-samples/<id>/transcribe/` | Re-run STT on the sample and store the transcript. |

```bash
curl https://api.inference.club/api/inference/voice-samples/ \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -F audio=@me.wav -F speaker_name="Brian" -F transcript="Hi, this is a short sample of my voice."
```

Each sample has a `speaker_name` and an optional `is_default` flag; the default sample is pre-selected in the Voice playground.

You can also record directly in the browser — the recording is stored as webm/opus and transcoded to WAV on the backend before being sent to Dia.
