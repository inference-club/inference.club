---
title: Text to speech
description: Synthesize speech from text over the OpenAI-compatible /v1/audio/speech endpoint.
category: API reference
order: 6
---

# Text to speech

Generate natural speech from text with any TTS model on the network. The endpoint mirrors OpenAI's speech API, so the official SDKs and `curl` work unchanged.

```
POST /v1/audio/speech
```

Requests route only to services a provider declared as `type: tts`. The response is the **raw audio** (just like OpenAI), and a copy is stored on inference.club so it shows up in your history.

## Request

`application/json`:

| Field | Required | Description |
|---|---|---|
| `model` | yes | A `tts` model id from `GET /v1/models`. |
| `input` | yes | The text to synthesize. |
| `voice` | no | A voice name (see [voices](#voices)). Defaults to the provider's default. |
| `response_format` | no | `wav` (default) or `opus`. |
| `language` | no | Language hint, e.g. `en-US` (the model is multilingual). |

### curl

```bash
curl https://api.inference.club/v1/audio/speech \
  -H "Authorization: Bearer $INFERENCE_CLUB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{ "model": "magpie-tts-multilingual", "input": "Hello from inference club", "voice": "Magpie-Multilingual.EN-US.Mia" }' \
  --output speech.wav
```

### Python (openai SDK)

```python
from openai import OpenAI

client = OpenAI(base_url="https://api.inference.club/v1", api_key="<your-api-key>")
with client.audio.speech.with_streaming_response.create(
    model="magpie-tts-multilingual",
    voice="Magpie-Multilingual.EN-US.Mia",
    input="Hello from inference club",
) as response:
    response.stream_to_file("speech.wav")
```

## Response

The raw audio bytes, with `Content-Type: audio/wav` (or `audio/ogg` for Opus). Metered by the duration of the generated audio.

## Voices

Voices are model-specific. List what a model offers:

```
GET /v1/audio/voices?model=<model-id>
```

```json
{ "voices": ["Magpie-Multilingual.EN-US.Mia", "Magpie-Multilingual.EN-US.Jason", "…"] }
```

(`/v1/audio/voices` is an inference.club extension, not part of OpenAI's API.) The in-dashboard [Speech playground](/dashboard/playground/speech) populates a voice dropdown from this.

## Notes

- **Formats:** the reference provider (NVIDIA Riva / Magpie) returns WAV natively; we also offer Opus. mp3/aac/flac aren't transcoded — a request for those returns WAV.
- **Speed** and other OpenAI parameters not supported by the provider are ignored.

## Errors

| `type` | When | HTTP |
|---|---|---|
| `missing_input` | No `input` text | 400 |
| `request_too_large` | Input text over the limit | 413 |
| `no_provider` | No online TTS provider serves the model for you | 404 |
| `upstream_error` | The provider's speech server failed | 502 |
