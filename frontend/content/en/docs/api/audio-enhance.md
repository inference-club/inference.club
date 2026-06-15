---
title: Audio enhancement
description: Clean up noisy speech over the OpenAI-style /v1/audio/enhance endpoint (NVIDIA Maxine Studio Voice).
category: API reference
order: 14
---

# Audio enhancement

Remove background noise, reverberation, and distortion from a speech recording, producing studio-quality audio. Audio file **in**, cleaned audio file **out**. Powered by [NVIDIA Maxine Studio Voice](https://developer.nvidia.com/maxine).

```
POST /v1/audio/enhance
```

The request is `multipart/form-data` (an audio file plus form fields), mirroring `/v1/audio/transcriptions`. The response is the **raw enhanced audio** (just like `/v1/audio/speech`), and a copy is stored on inference.club so it shows up in your history. Requests route only to services a provider declared as `type: audio-enhance`.

## Request

`multipart/form-data`:

| Field | Required | Description |
|---|---|---|
| `file` | yes | The audio file to enhance (wav, mp3, m4a, flac, ogg, webm). |
| `model` | yes | An `audio-enhance` model id from `GET /v1/models`. |
| `response_format` | no | `wav` (default) or `opus`. |

### curl

```bash
curl https://api.inference.club/v1/audio/enhance \
  -H "Authorization: Bearer $INFERENCE_CLUB_API_KEY" \
  -F file="@noisy.wav" \
  -F model="<your-audio-enhance-model>" \
  --output enhanced.wav
```

## Response

The raw enhanced audio bytes, with `Content-Type: audio/wav` (or `audio/ogg` for Opus). The cleaned clip is also persisted to your library as an output audio asset. Metered by the duration of the audio.

## Notes

- **Formats:** providers typically return WAV natively; `opus` is also accepted as a `response_format`. mp3/aac/flac aren't transcoded — a request for those returns WAV.
- The in-dashboard [Audio enhancement playground](/dashboard/playground/enhance) wraps this endpoint with upload, record, and preview.

## Errors

| `type` | When | HTTP |
|---|---|---|
| `missing_file` | No `file` part in the request | 400 |
| `file_too_large` | Upload exceeds the size limit | 413 |
| `unsupported_media_type` | The file's content-type isn't an accepted audio type | 415 |
| `no_provider` | No online audio-enhancement provider serves the model for you | 404 |
| `upstream_error` | The provider's enhancement server failed | 502 |
