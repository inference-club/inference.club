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
This endpoint can also be run asynchronously — add `"async": true` to always queue it as a job, or `"async": "auto"` to queue only when the device is busy. See [Direct vs async](/docs/services/direct-vs-async).
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
| `delivery` | no | `bytes` (default) or `url` — see [below](#getting-a-url-instead-of-bytes). |
| `async` | no | `true` or `"auto"` — see [Async jobs](/docs/api/jobs). |

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

## Getting a URL instead of bytes

Add `"delivery": "url"` to get JSON instead of the raw file — easier for agents and scripts that only need a link:

```json
{
  "object": "inference.result",
  "id": "8812",
  "public_id": "kQ3v9xZp1aE",
  "inference_type": "TTS",
  "model": "<your-tts-model>",
  "status": "PROCESSED",
  "created": 1780266332,
  "data": [{ "id": 551, "kind": "audio", "url": "https://…", "content_type": "audio/wav", "duration_seconds": 2.4 }]
}
```

With the default `"delivery": "bytes"`, the response headers still name the stored copy: `X-Inference-Request-Id` (pollable at `GET /v1/jobs/<id>`), `X-Asset-Id`, and `X-Asset-Url`.

## Voices

Voices are model-specific. List what a model offers:

```
GET /v1/audio/voices?model=<model-id>
```

```json
{ "voices": ["Magpie-Multilingual.EN-US.Mia", "Magpie-Multilingual.EN-US.Jason", "…"] }
```

(`/v1/audio/voices` is an inference.club extension, not part of OpenAI's API.) The in-dashboard [Speech playground](/dashboard/playground/speech) populates a voice dropdown from this.

## More than one TTS model

A provider can run several TTS models side by side, for example a multilingual GPU model and a small CPU model. Each appears on `GET /v1/models` with its own id, and `model` decides which one speaks. Voice names are not shared between models, so list a model's voices before choosing one; a voice the model doesn't know falls back to that model's default.

```json
{ "voices": ["af_heart", "am_michael", "bf_emma", "bm_george", "…"] }
```

That is what `GET /v1/audio/voices?model=nano-edge-tts` returns for [nano-edge-tts](https://huggingface.co/drmhse/nano-edge-tts), a CPU-only English model built on Kokoro.

## Serving a TTS model (providers)

Any speech server can join the network as a `type: tts` service if it answers two paths, the same two an NVIDIA Riva speech NIM serves:

| Path | Request | Response |
|---|---|---|
| `POST /v1/audio/synthesize` | `multipart/form-data` fields `text`, `language`, `voice`, `sample_rate_hz`, `encoding` (`LINEAR_PCM` or `OGGOPUS`) | the audio bytes (`audio/wav` or `audio/ogg`) |
| `GET /v1/audio/list_voices` | none | `{"<language tags>": {"voices": ["…"]}}` |

inference.club adds `?model=<served id>` to both calls. The agent uses it to pick the right service when a host runs more than one, and a server is free to ignore it. Tips from wiring up a non-Riva model:

- Honor `sample_rate_hz` (the default request is 44100) by resampling if the model has another native rate.
- Accept an unknown `voice` and fall back to a default instead of returning an error, since a client may still hold another model's voice name.
- Declare the model id on the service (see the [Kubernetes agent](/docs/providers/kubernetes-agent) labels) so it routes by name.

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
| `at_capacity` | Every slot on the device is busy (after a ~20s wait). Honor `Retry-After`, or send `"async": "auto"` | 429 |
| `upstream_error` | The provider's speech server failed | 502 |
