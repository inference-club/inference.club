---
title: Text to speech
description: Synthesize speech from text over the OpenAI-compatible /v1/audio/speech endpoint.
category: API reference
order: 7
---

# Text to speech

::api-endpoint{method="POST" path="/v1/audio/speech" async="true"}

Generate natural speech from text with any TTS model on the network. The endpoint mirrors OpenAI's speech API, so the official SDKs and `curl` work unchanged.

::callout{type="tip"}
This endpoint can also be run asynchronously — add `"async": true` to queue it as a job instead of blocking. See [Direct vs async](/docs/services/direct-vs-async).
::

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
  -d '{ "model": "<your-tts-model>", "input": "Hello from inference club", "voice": "en-US-female-1" }' \
  --output speech.wav
```

### Python (openai SDK)

```python
from openai import OpenAI

client = OpenAI(base_url="https://api.inference.club/v1", api_key="<your-api-key>")
with client.audio.speech.with_streaming_response.create(
    model="<your-tts-model>",
    voice="en-US-female-1",
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

## Voice cloning

For expressive multi-speaker dialogue with voice cloning, see [`POST /v1/voice/generations`](/docs/api/voice-generations). That endpoint routes to providers running [Dia](https://github.com/nari-labs/dia) and accepts `[S1]`/`[S2]` speaker-tagged scripts with optional voice samples from your library.

## Notes

- **Formats:** providers typically return WAV natively; we also accept `opus` as a `response_format`. mp3/aac/flac aren't transcoded — a request for those returns WAV.
- **Speed** and other OpenAI parameters not supported by the provider are ignored.

## Errors

| `type` | When | HTTP |
|---|---|---|
| `missing_input` | No `input` text | 400 |
| `request_too_large` | Input text over the limit | 413 |
| `no_provider` | No online TTS provider serves the model for you | 404 |
| `upstream_error` | The provider's speech server failed | 502 |
