# inference.club API cheat sheet

Base: `https://api.inference.club/v1` · Auth: `Authorization: Bearer <key>` ·
Spec: `https://api.inference.club/openapi.json` · Docs: https://inference.club/docs

## Endpoints

| Task | Method + path | Body | Async-able |
|---|---|---|---|
| List models | `GET /models` | — | — |
| Live GPU load | `GET /capacity?service_type=` | — | — |
| Chat | `POST /chat/completions` | OpenAI chat JSON | yes |
| Image | `POST /images/generations` | `{model, prompt, size, n, seed, negative_prompt, background}` | yes |
| Image edit | `POST /images/edits` | multipart `image` (or repeated `image[]`), `prompt`, `model` | no |
| Video | `POST /videos/generations` | `{model, prompt, image?, width, height, num_frames, fps, seed}` | yes |
| Music | `POST /music/generations` | `{model, prompt, lyrics, audio_duration, seed}` | yes |
| Speech | `POST /audio/speech` | `{model, input, voice}` | yes |
| Dialogue / cloning (Dia) | `POST /voice/generations` | `{model, input:"[S1] … [S2] …", speakers?}` | no |
| Transcribe | `POST /audio/transcriptions` | multipart `file`, `model` | no |
| 3D | `POST /3d/generations` | multipart `image`, `model` | no |
| Scrape | `POST /scrape` | `{model, url}` → markdown | yes |
| Job | `GET /jobs/{id}` · `POST /jobs/{id}/cancel` | — | — |
| Workflows | `GET /workflows/templates` · `POST /workflows/runs {template, inputs}` · `GET /workflows/runs/{id}` | | |

## inference.club extensions (stripped before reaching the model)

- `"async": true | "auto"` — `true` always queues; `"auto"` runs now if a GPU slot is
  free, else queues (also queues while a known model's node is briefly offline).
  Queued → `202 {id, status:"QUEUED", poll_url, queued_reason}`.
- `"delivery": "url"` (audio/video/voice endpoints) → JSON
  `{object:"inference.result", id, data:[{id, kind, url, content_type, duration_seconds}]}`
  instead of raw bytes. Byte responses carry `X-Asset-Url` / `X-Inference-Request-Id`.
- `"visibility": "PUBLIC|UNLISTED|PRIVATE|SECRET"`, `"collection": "name"`.
- Header `Idempotency-Key: <unique>` on retries of async submissions.

## Polling a job

`GET /jobs/{id}` → `status` ∈ QUEUED, PROCESSING, PROCESSED, FAILED, CANCELED.
When PROCESSED: `media[]` (all outputs) and `output_text` (full LLM/STT/scrape text).
Back off 3s → 15s between polls.

## Errors

`{"error": {"type", "message"}}`: `no_provider` 404 · `at_capacity` 429 (+`Retry-After`;
device busy) · rate limit 429 (+`Retry-After`) · `upstream_error` 502 ·
`request_too_large` 413 · `async_disabled` 503. Auth errors: 401 `{"detail"}`.
