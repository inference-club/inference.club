---
title: Audio transcriptions
description: Speech-to-text (STT/ASR) over the OpenAI-compatible /v1/audio/transcriptions endpoint.
category: API reference
order: 4
---

# Audio transcriptions

Transcribe speech to text with any STT (speech-to-text / ASR) model on the network. The endpoint mirrors OpenAI's transcription API, so the official SDKs and `curl` work unchanged.

```
POST /v1/audio/transcriptions
```

This is a separate modality from the chat/completions LLM endpoints — it takes an **audio file** (`multipart/form-data`, not JSON) and returns text. Requests are routed only to services a provider has declared as `type: stt`, so a transcription never lands on a text model.

## Request

`multipart/form-data` with these fields:

| Field | Required | Description |
|---|---|---|
| `file` | yes | The audio file. wav, mp3, m4a, flac, ogg, or webm. Up to 25 MB. |
| `model` | yes | An STT model id from `GET /v1/models` (e.g. `qwen/qwen3-asr-1.7b`). |
| `language` | no | ISO-639-1 hint (e.g. `en`). Improves accuracy/latency when known. |
| `prompt` | no | Free-text hint — names, jargon, or context to bias decoding. |
| `response_format` | no | `json` (default) or `verbose_json`. See [Timestamps](#timestamps). |
| `timestamp_granularities[]` | no | `word` and/or `segment`. Requires `verbose_json` **and** a model that supports it. |

### curl

```bash
curl https://api.inference.club/v1/audio/transcriptions \
  -H "Authorization: Bearer $INFERENCE_CLUB_API_KEY" \
  -F file=@audio.wav \
  -F model=qwen/qwen3-asr-1.7b
```

### Python (openai SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.inference.club/v1",
    api_key="<your-api-key>",
)

with open("audio.wav", "rb") as f:
    result = client.audio.transcriptions.create(
        model="qwen/qwen3-asr-1.7b",
        file=f,
    )
print(result.text)
```

## Response

Default (`response_format=json`):

```json
{
  "text": "Hey, this is a demo of the new model…",
  "usage": { "type": "duration", "seconds": 10 }
}
```

`usage.seconds` is the **audio duration** — the metering unit for speech, the way token counts are for text. It's recorded on every transcription request.

## Timestamps

When you ask for `response_format=verbose_json` with `timestamp_granularities[]`, models that support it return word- and segment-level timings:

```json
{
  "text": "Hello world",
  "language": "en",
  "duration": 1.2,
  "segments": [{ "id": 0, "start": 0.0, "end": 1.2, "text": "Hello world" }],
  "words": [
    { "word": "Hello", "start": 0.0, "end": 0.5 },
    { "word": "world", "start": 0.6, "end": 1.2 }
  ]
}
```

> **Not every deployment supports timestamps.** Whether word/segment timings are available depends on how the provider serves the model, not just the model id — e.g. Qwen3-ASR returns timestamps only when launched with its [ForcedAligner](https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B) (plain `vllm serve` rejects `verbose_json`). So the capability is **declared by the operator** in their agent manifest (`services[].features: [timestamps]`) and surfaced as the `timestamps` entry in a model's `supported_features` on `/v1/models`.
>
> When a model isn't declared timestamp-capable, inference.club **automatically downgrades** a `verbose_json` request to plain `json` — so you get a clean transcript instead of an upstream error, never a fake one. The in-dashboard [Transcription playground](/dashboard/playground/transcribe) only offers the timestamp toggle, and renders the interactive click-to-seek transcript, when the selected model actually supports it.

## Errors

| `type` | When | HTTP |
|---|---|---|
| `missing_file` | No `file` field in the request | 400 |
| `file_too_large` | Audio exceeds the 25 MB cap | 413 |
| `unsupported_media_type` | The file's content-type isn't an accepted audio type | 415 |
| `no_provider` | No online STT provider serves the requested model for you | 404 |
| `upstream_error` | The provider's local ASR server failed or didn't respond | 502 |

## Not supported (yet)

Translations (`/v1/audio/translations`) and streaming transcription are not available. The response is always a single buffered JSON body.
