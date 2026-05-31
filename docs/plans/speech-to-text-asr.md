# Plan: Speech-to-Text (STT / ASR) as a first-class modality

> **Status:** Implemented. Verified end-to-end against the reference
> Qwen3-ASR agent with `audio.wav` (transcript returned, `usage.seconds`
> metered, input audio stored). Backend, frontend, infra, and the agent
> (`~/git/inference-club-agent`) are all updated.
>
> **Decisions taken** (were open questions): STT lives on a **separate
> playground page** (`/dashboard/playground/transcribe`); input audio is
> **stored by default** (`STT_STORE_INPUT_AUDIO`); prod uses **MinIO**
> (same as local, swappable to S3/R2 via env); `audio_seconds` is
> recorded now with the leaderboard surface deferred; the inference-type
> label is **`STT`** (YAML service type `stt`).
>
> **Audience:** the agent working on either this repo or
> `~/git/inference-club-agent`. This document is the contract between
> the two so the feature works end-to-end. It also pulls in a new piece
> of shared infrastructure (S3-compatible object storage) that later
> modalities (TTS, image generation) will reuse.

Until now inference.club has proxied one modality: text-in / text-out
LLMs over `/v1/chat/completions` and `/v1/completions`. This plan adds a
second, **deliberately isolated** modality — speech-to-text (a.k.a.
automatic speech recognition, ASR) — exposed at the OpenAI-standard
endpoint **`POST /v1/audio/transcriptions`**.

We are *not* doing translations (`/v1/audio/translations`) in this pass,
though the design leaves room for it. TTS (`/v1/audio/speech`) comes
next and is explicitly anticipated below, but is out of scope here.

A reference STT service already exists on the network: a vLLM
deployment of `Qwen/Qwen3-ASR-1.7B` at `http://192.168.5.173:8000/v1`.
The repo root has `audio.wav` (10s, mono 44.1kHz PCM) for end-to-end
testing.

---

## 0. What the reference server actually does (verified)

Probed `http://192.168.5.173:8000/v1` with `audio.wav` on 2026-05-31:

```
GET /v1/models
  → { "data": [ { "id": "Qwen/Qwen3-ASR-1.7B", "max_model_len": 65536, ... } ] }

POST /v1/audio/transcriptions   (multipart: file, model)
  → { "text": "Hey, this is a demo ...",
      "usage": { "type": "duration", "seconds": 10 } }

POST .../transcriptions  with response_format=verbose_json
  → 400 "Currently do not support verbose_json for Qwen/Qwen3-ASR-1.7B"
```

**Two load-bearing facts that shape the whole design:**

1. **`usage.seconds` is the universal metering signal** for audio (the
   analogue of token counts for LLMs). Every OpenAI-compatible ASR
   server reports audio duration. We mirror it into a dedicated column.

2. **Word/segment timestamps are NOT universal.** This Qwen3-ASR
   deployment supports only `response_format=json` (plain `{text, usage}`).
   Whisper-family servers (`faster-whisper`, `whisper.cpp` server,
   vLLM-Whisper) *do* support `verbose_json` with `segments[]` and
   `words[]`. Therefore the fancy timestamp visualization is a
   **capability-gated, gracefully-degrading** feature — when the model
   can't do it, we show a clean plain-text result and never send
   `verbose_json`.

---

## 1. Design principles

- **Isolation from LLM.** STT gets its own proxy view, its own service
  type, its own playground surface, and its own `InferenceRequest`
  type. It must not complicate the hot LLM path. Shared machinery
  (provider routing, request logging, capability chips, mic recording)
  is reused, not forked.
- **Standards-compliant.** Clients that already speak the OpenAI audio
  API (`openai-python`, `openai-node`, curl) work unchanged against
  `https://inference.club/v1/audio/transcriptions`.
- **Service-type awareness everywhere.** A new `type` axis (`llm | stt
  | tts`) on services flows from `agent.yaml` → manifest → routing, so
  a transcription request can only land on an STT service and a chat
  request can only land on an LLM service.
- **Object storage is shared infra, built once.** STT only *needs* to
  store the input audio (for history/replay), but we stand up
  S3-compatible storage (MinIO locally) the right way now so TTS audio
  output and future image output drop straight in.
- **Forward-looking, not over-built.** We add exactly the
  storage/model/columns STT needs, shaped so TTS and image-gen extend
  them rather than replace them.

---

## 2. The `agent.yaml` service-type axis

Today a service declares an `engine` (`vllm | ollama | …`). That's the
*how*. We add `type` — the *what* — defaulting to `llm` so every
existing manifest stays valid.

```yaml
schema_version: 1
agent:
  name: brian-home
hosts:
  - id: rig-01
    gpu: { vendor: nvidia, model: RTX 4090, vram_gb: 24 }
    services:
      - name: rtx-4090-vllm          # existing LLM service
        type: llm                     # NEW — optional, defaults to "llm"
        engine: vllm
        url: http://192.168.1.10:8000/v1
        models:
          - hf: Qwen/Qwen3-30B-A3B

      - name: asr-qwen                # NEW STT service
        type: stt                     # NEW
        engine: vllm
        url: http://192.168.5.173:8000/v1
        models:
          - id: Qwen/Qwen3-ASR-1.7B
            hf: Qwen/Qwen3-ASR-1.7B
```

**Validator** (`backend/apps/inference/manifest_validator.py`): add
`SERVICE_TYPES = {"llm", "stt", "tts"}`; validate `svc.get("type",
"llm")` is in the set. `tts` is accepted now (cheap, keeps the agent and
server in lockstep for the next chapter) even though no TTS endpoint
ships yet. Mirror the same constant + check in the agent's own
validator.

---

## 3. Backend changes (`inference.club`)

### 3.1 New endpoint + view — `POST /v1/audio/transcriptions`

`openai_urls.py`: register `audio/transcriptions` →
`AudioTranscriptionsView`.

The existing `_ChatOrCompletionsProxy` assumes JSON
(`requests.post(json=body)`, `request.data` as a dict, token guardrails).
**Do not** shoehorn STT into it. Add a sibling base/mixin for the shared
bits (provider lookup, `InferenceRequest` create/finalize,
`last_seen_at` bump, rate-limit headers) and a dedicated multipart view:

```
class AudioTranscriptionsView(APIView):
    throttle_scope = "inference"            # reuse existing throttle
    inference_type = "STT"

    def post(self, request):
        # 1. parse multipart: file = request.FILES["file"]; form fields from request.data
        # 2. guardrails: file present, size <= STT_MAX_UPLOAD_BYTES (default 25MB),
        #    content-type/extension in an allowlist (wav, mp3, m4a, flac, ogg, webm)
        # 3. model = request.data.get("model");  resolve provider with
        #    _find_provider_for_model(user, model, service_type="stt")   # see 3.3
        # 4. persist the upload as a MediaAsset (kind=INPUT_AUDIO)        # see 3.4
        # 5. drop verbose_json if the model can't do timestamps           # see 3.5
        # 6. forward multipart to the agent:
        #       requests.post(endpoint, files={"file": (...)}, data=form, ...)
        # 7. store results; mirror usage.seconds -> InferenceRequest.audio_seconds
```

Notes:

- **No streaming.** Transcriptions return a single buffered JSON body.
  This is simpler than the LLM path — no SSE assembly.
- **Read the upload once.** DRF buffers it (`InMemoryUploadedFile` /
  `TemporaryUploadedFile`). Save to storage, then `seek(0)` and forward
  the same bytes (or re-open from storage). Cap in memory via
  `STT_MAX_UPLOAD_BYTES`.
- **Forward via Tailscale** exactly like the LLM path: same
  `verify=False`, same `_tailnet_proxies()`, same `UPSTREAM_TIMEOUT`.
- **Model-id rewrite** still applies: rewrite the form `model` field
  from the public catalog slug to the provider's served name.

### 3.2 `InferenceRequest` — add `STT` type + audio metering column

- Add `("STT", "Speech to Text")` to `INFERENCE_TYPES`.
- Add a nullable `audio_seconds` column (mirrors `usage.seconds`,
  parallel to how `total_tokens` is mirrored for cheap aggregation).
  Leave `prompt/completion/total_tokens` null for STT.
- `payload` (required JSONField) stores **metadata, not bytes**:
  `{model, language?, prompt?, response_format, temperature?,
  filename, content_type, size_bytes, asset_id}`.
- `results` stores `{text, language?, duration?, segments?, words?}`
  plus the linked input-audio asset reference.
- One migration. Leaderboard/profile token aggregation is unaffected
  (STT rows have null tokens); a follow-up can add an "audio minutes"
  stat from `audio_seconds`.

### 3.3 Routing gains a service-type filter

`_find_provider_for_model(user, model_name)` is inference-type-agnostic
today — good, we reuse it, but it must not route an STT request onto an
LLM service that happens to share a name. Thread an optional
`service_type` through the matchers (`_own_provider_match`,
`_any_provider_match`, `_model_match_q`) that filters
`ProviderModel.service.service_type`. LLM callers pass `"llm"` (or
`None` = any, for back-comat), STT callers pass `"stt"`. Access-control
(`ProviderService.grants_access_to`) is unchanged.

### 3.4 Object storage + `MediaAsset` (shared infra)

Stand up S3-compatible storage and a generic asset model that STT, TTS,
and image-gen all share.

- **Dependencies:** `django-storages[s3]` + `boto3`.
- **Settings:** when `OBJECT_STORAGE_ENDPOINT`/bucket env vars are set,
  point `STORAGES["default"]` at the S3 backend (path-style addressing
  for MinIO); otherwise keep `FileSystemStorage` (so contributors
  without MinIO still run). Public read of generated media is via the
  backend, not bucket ACLs.
- **New model** `MediaAsset(BaseModel)` in the `inference` app:

  ```
  user               FK CustomUser
  inference_request  FK InferenceRequest (null, related_name="assets")
  kind               CharField: INPUT_AUDIO | OUTPUT_AUDIO | OUTPUT_IMAGE
  file               FileField(upload_to="<kind>/<user>/<uuid>")  # -> STORAGES default
  content_type       CharField
  size_bytes         BigIntegerField
  duration_seconds   FloatField (null)      # audio only
  metadata           JSONField (default dict)
  ```

  STT uses `INPUT_AUDIO`; TTS will use `OUTPUT_AUDIO`; image-gen
  `OUTPUT_IMAGE`. This is the "exactly what we need, shaped for what's
  next" piece.
- **Retention:** persist input audio so the playground/profile can
  replay it. Make it configurable (`STT_STORE_INPUT_AUDIO`, default on)
  and note a future cleanup job — we don't want unbounded growth, but
  we don't build GC now.
- **Serving:** a thin authenticated backend route (e.g.
  `/api/inference/assets/<id>/`) streams/redirects to the asset so the
  playground audio player and history work regardless of bucket
  privacy.

### 3.5 Capability gating for timestamps

Timestamp support is a **per-deployment** property, not a model-identity
one: Qwen3-ASR returns word/segment timings only when vLLM is launched
with its ForcedAligner (plain `vllm serve` rejects `verbose_json` — we
confirmed this on the reference box, which runs without the aligner).
So the operator **declares** it in the manifest:

```yaml
services:
  - name: asr-qwen
    type: stt
    features: [timestamps]   # only when the server really returns timings
```

The agent ships `services[].features` (a free-form capability list);
the backend stores it on `ProviderService.declared_features` and
`_model_caps` unions it with the catalog's HF-derived
`supported_features` (Whisper-family still auto-gets `timestamps`).
The backend **strips** `response_format=verbose_json` /
`timestamp_granularities[]` down to `json` whenever the resolved model
lacks the `timestamps` feature, so a client asking for timestamps
against a plain Qwen3-ASR deployment gets a clean plain result instead
of the upstream 400 — never a synthesized/fake timing. Real timings
flow through only when the operator has actually enabled them.

### 3.6 Catalog & capabilities for STT models

- STT `CatalogModel`s carry `input_modalities=["audio"]`,
  `output_modalities=["text"]`. The capability UI already has an audio
  icon, so they render correctly with zero frontend model-card work.
- `sync_provider_models_from_manifest`: propagate `service.type` onto a
  new `ProviderService.service_type` field, and set audio/text
  modalities on STT catalog models.
- `hf_enrich.py`: map `pipeline_tag == "automatic-speech-recognition"`
  → audio-in/text-out, and infer timestamp support for the
  whisper architecture family.
- `/v1/models` and the OpenRouter-style catalog already emit
  modalities/features — STT models flow through unchanged.

---

## 4. Agent changes (`inference-club-agent`)

The agent today reverse-proxies all `/v1/*` to a single local server.
With a service-type axis it must route **by endpoint → service type**:

- `/v1/chat/completions`, `/v1/completions`, `/v1/models` → an `llm`
  service's `url`.
- `/v1/audio/transcriptions` → the `stt` service's `url`
  (`http://192.168.5.173:8000/v1` in the reference setup).
- (later) `/v1/audio/speech` → the `tts` service's `url`.

Work items:

1. Parse and validate the new `type` field (mirror §2's
   `SERVICE_TYPES`; default `llm`).
2. Build an endpoint→service routing table from the manifest. If two
   services share a type, pick by the request's `model` field.
3. **Pass multipart bodies through untouched.** A Go `httputil`
   reverse proxy streams the raw body + `Content-Type` (multipart
   boundary) already; confirm no JSON-only assumption sneaks in
   (no body buffering/parsing for audio — files can be large).
4. `/v1/models` aggregation: when multiple service types exist, the
   agent should report each service's models (the backend already
   prefers the manifest as source of truth, so this is mostly for the
   live-probe path).
5. Update the agent's `agent.yaml` example/docs and ROADMAP.

> The agent lives in a separate repo. This document is the cross-repo
> contract; the agent PR implements §2 + §4 against it.

---

## 5. Frontend changes (`frontend/`)

### 5.1 A dedicated STT playground (isolated surface)

Add a transcription surface separate from the chat playground —
either a sibling page `dashboard/playground/transcribe` or a
tabbed mode within the playground shell. It reuses the **existing mic
recording code** already living in `playground/index.vue` (extract it
into a `useAudioRecorder` composable) plus a file drop/upload.

Flow: pick an STT model (filtered to audio-in models) → record or
upload audio → `POST` multipart to `/v1/audio/transcriptions` → render
the result. A new `useTranscription()` composable (sibling to
`usePlayground`) owns the multipart fetch + CSRF/session handling.

### 5.2 Word-timestamp visualization (capability-gated)

When the selected model advertises timestamp support and the response
includes `words[]`/`segments[]`, render an **interactive transcript**:

- An `<audio>` player bound to the stored `INPUT_AUDIO` asset.
- The transcript as per-word chips carrying `start`/`end`. Clicking a
  word seeks the audio; during playback the current word
  karaoke-highlights as `audio.currentTime` crosses its interval.
- Optional segment lane / simple waveform underlay.

When the model can't do timestamps (the Qwen3-ASR case), degrade to a
clean copyable transcript block with a small "timestamps not supported
by this model" note — **no broken UI, no failed request.**

Always show: detected language (if returned), audio duration
(`usage.seconds`), and latency.

### 5.3 History, cards, profile, docs

- `InferenceRequestCard.vue`: handle `STT` — a "Speech-to-Text" badge,
  a transcript preview, audio duration, and an inline audio player from
  the linked asset.
- `[username].vue`: served STT models already render via
  `ModelCapabilities` (audio→text). The "served models" CTA and code
  snippets gain an `/v1/audio/transcriptions` curl/python/ts example
  for STT models.
- **Docs:** new `content/docs/api/audio-transcriptions.md` (request
  shape, multipart fields, `response_format`, timestamp caveat,
  metering by `usage.seconds`); update `api/overview.md` (endpoint
  list + modalities), `providers/run-an-agent.md` (the `type: stt`
  manifest example), and `concepts.md` (service types / modalities).

---

## 6. Infrastructure changes

- **Local (`docker-compose.yml`):** add a `minio` service + a
  `minio-setup` (mc) one-shot that creates the bucket; wire the backend
  with `OBJECT_STORAGE_*` env. Document the console port in the dev
  memory/notes.
- **Prod (`infra/`, Pulumi/TS + compose template):** add MinIO (or
  point at managed S3/R2) and the same env in
  `infra/templates/docker-compose.yml.tpl` +
  `backend.env.tpl`. Caddy route for the asset-serving endpoint if
  needed (it goes through the backend, so likely nothing extra).
- **Settings guardrails:** `STT_MAX_UPLOAD_BYTES` (25MB),
  `STT_ALLOWED_CONTENT_TYPES`, `STT_STORE_INPUT_AUDIO`.

---

## 7. Testing

- **Live e2e:** drive `audio.wav` through
  `inference.club/v1/audio/transcriptions` against the real Qwen3-ASR
  agent; assert `{text, usage.seconds}` round-trips and an
  `INPUT_AUDIO` MediaAsset is stored.
- **Backend units:** multipart parsing + size/type guardrails; provider
  resolution honors `service_type` (STT request never lands on an LLM
  service); `verbose_json` is stripped for non-timestamp models;
  `audio_seconds` mirrored from `usage`; manifest validator accepts/
  rejects `type`.
- **Storage:** MediaAsset write/read against MinIO (and FileSystem
  fallback).
- **Frontend:** transcription composable posts multipart with
  CSRF/session; timestamp UI renders from a `words[]` fixture and
  degrades cleanly without one.

---

## 8. Out of scope / explicitly deferred

- `/v1/audio/translations` (related, not now).
- **TTS** (`/v1/audio/speech`) — the `tts` service type and
  `OUTPUT_AUDIO` asset kind are scaffolded here so the next chapter is
  additive; model choice (likely Qwen TTS) is still being decided.
- Image generation — `OUTPUT_IMAGE` asset kind reserved.
- Audio-minutes billing/leaderboard surface (column lands now; the UI
  stat is a fast follow).
- Asset garbage-collection / retention enforcement (flagged, not built).

---

## 9. Open questions for review

1. **STT playground placement:** separate page (`/dashboard/playground/
   transcribe`) vs. a tab inside the existing playground? (Leaning
   separate page for clean isolation.)
2. **Store input audio by default?** On (enables replay/history) vs.
   off (privacy/storage). Default proposed: **on**, configurable.
3. **MinIO in prod** vs. managed S3/R2 from day one. Proposed: MinIO to
   match local, swap to managed later via the same env.
4. **Metering name/units:** `audio_seconds` column — surface as "audio
   minutes" on the leaderboard, or keep STT out of the token-centric
   leaderboard for now?
5. **Inference-type label:** `STT` (chosen, matches your wording)
   vs. `ASR`. Service-type key in YAML is `stt`.
