# Plan: Image generation as a modality

> **Status:** Proposed. Not yet implemented.
>
> **Audience:** the agent working on either this repo or
> `~/git/inference-club-agent`. This document is the contract between
> the two so the feature works end-to-end. It builds directly on the
> STT chapter — the service-type axis, the `MediaAsset` object store
> (MinIO), the per-deployment feature declaration, and the multipart
> proxy pattern are all reused.
>
> **Decisions taken** (from review): images travel **inline as
> `b64_json`** over the existing tailnet response and the backend stores
> them in MinIO; the API is **synchronous** with the `InferenceRequest`
> created up front; the default client response **stores the image and
> returns an inference.club URL** (`b64_json` honored on request); v1
> covers **`/v1/images/generations` + `/v1/images/edits`**.

Adds a third modality: text-to-image (and image+prompt → edited image)
via the OpenAI-standard endpoints **`POST /v1/images/generations`** and
**`POST /v1/images/edits`**. Reference server: an OpenAI-compatible
image server at `http://192.168.5.96:8000/v1`.

---

## 0. What the reference server actually does (verified)

Probed `http://192.168.5.96:8000` on 2026-05-31:

```
GET  /v1/models                      → 404 (no model catalog endpoint)

POST /v1/images/generations          {prompt, n, size, response_format}
  → { "created": 1780265556,
      "data": [ { "b64_json": "<base64 PNG>" } ] }
  → response_format=url ⇒ 400 "response_format='url' is not supported; only 'b64_json'"
  → output is a valid PNG (e.g. 256×256 RGB)

POST /v1/images/edits                multipart: image + prompt (+ mask)
  → { "created": ..., "data": [ { "b64_json": "<base64 PNG>" } ] }
```

**Load-bearing facts:**

1. **The server returns image bytes inline (`b64_json`) and *only*
   `b64_json`.** It rejects `response_format=url`. So the inline
   transport isn't just our preference — it's the only thing the server
   does. The backend always asks upstream for `b64_json`, stores the
   bytes in MinIO, and then returns whatever the *client* asked for.
2. **No `/v1/models`.** Like the Qwen3-ASR box, the server doesn't
   advertise a model id (and ignores the `model` field). Model identity
   is **operator-declared in the manifest** (served id + optional HF
   id), exactly as for STT.
3. **`/v1/images/edits` is multipart** (image + prompt, optional mask),
   same shape as `/v1/audio/transcriptions` — we reuse the multipart
   proxy + input-asset storage pattern.

---

## 1. Design principles

- **Isolation, then reuse.** Image gen gets its own views, its own
  playground surface, its own `image` service type, and the existing
  `IMAGE` `InferenceRequest` type — but reuses provider routing,
  `MediaAsset`/MinIO storage, the asset-serving route, request logging,
  and the capability UI.
- **OpenAI-standard.** `openai-python`/`-node`/curl image clients work
  unchanged against `https://inference.club/v1/images/*`.
- **Store everything, return a URL.** Every generated image is a
  `MediaAsset` (kind `OUTPUT_IMAGE`); every edit's source is an
  `INPUT_IMAGE`. The default response returns inference.club asset URLs
  (replayable, visible in history/playground); `response_format=b64_json`
  also returns the inline bytes.
- **Synchronous, IR up front.** The request blocks until the image is
  ready (bounded by the upstream timeout). The `InferenceRequest` is
  created in `PROCESSING` *before* forwarding so the job is recorded
  even if the connection drops, and finalized on completion.

---

## 2. The `image` service type

Extend the service-type axis (`llm | stt | tts`) with **`image`**.

```yaml
hosts:
  - id: rig-01
    services:
      - name: sdxl-images          # an image-generation service
        type: image                 # NEW — routes /v1/images/* here
        engine: other               # (or vllm/comfyui/etc.)
        url: http://192.168.5.96:8000/v1
        models:
          - id: my-image-model      # served id the client passes; the
            hf: stabilityai/...     # server ignores model, but we pool by this
```

- Add `image` to `SERVICE_TYPES` in both validators
  (`manifest_validator.py` and the agent's `manifest.go`).
- `_apply_service_type_modalities`: an `image` service seeds its catalog
  model with `input_modalities=["text", "image"]` (text always; image
  for edits) and `output_modalities=["image"]`. HF enrichment refines.

---

## 3. Backend changes (`inference.club`)

### 3.1 Endpoints + views

`openai_urls.py`: register

- `images/generations` → `ImageGenerationsView` (JSON body).
- `images/edits` → `ImageEditsView` (multipart).

Both are synchronous and buffered (no streaming). Factor the shared
logic into an `_ImageProxyBase` (sibling to the STT view, *not* the
JSON LLM proxy): provider lookup with `service_type="image"`, IR
create/finalize, upstream forward requesting `b64_json`, decode + store
each output image as `OUTPUT_IMAGE`, build the client response, bump
`last_seen_at`.

```
ImageGenerationsView.post:
  1. body = request.data (JSON); prompt required; guardrails (3.4)
  2. provider = _find_provider_for_model(user, body["model"], service_type="image")
  3. IR = InferenceRequest(inference_type="IMAGE", payload={prompt,size,n,...}, PROCESSING)
  4. forward JSON to <agent>/v1/images/generations with response_format=b64_json forced
  5. for each data[i].b64_json: decode → MediaAsset(OUTPUT_IMAGE) in MinIO, link to IR
  6. finalize IR (image_count, results, latency); respond (3.3)

ImageEditsView.post:           # multipart
  1. image = request.FILES["image"]; prompt required; optional mask
  2. store image as MediaAsset(INPUT_IMAGE); guardrails on size/type
  3. provider = ... service_type="image"
  4. forward multipart to <agent>/v1/images/edits (files=image[,mask], data=prompt/n/size/b64_json)
  5–6. same store + finalize + respond
```

### 3.2 `InferenceRequest` + `MediaAsset`

- `IMAGE` is already in `INFERENCE_TYPES` — no enum change.
- Add a nullable `image_count` column (mirrors `audio_seconds`/tokens —
  cheap aggregation of how many images a request produced).
- `MediaAsset`: add `INPUT_IMAGE` kind (`OUTPUT_IMAGE` already exists).
- `payload` (JSON) stores `{model, prompt, n, size, quality?,
  response_format, input_image_asset_id?}`. `results` stores
  `{created, image_asset_ids: [...], revised_prompt?}` plus the upstream
  metadata (no raw bytes).

### 3.3 Response shaping

Always request `b64_json` upstream (the server only does that, and we
need bytes to store). Then honor the **client's** `response_format`:

- default / `url` → `data: [{ "url": "<asset-serving URL>", "revised_prompt"? }]`
- `b64_json` → `data: [{ "b64_json": "<base64>" }]` (still stored)

The asset URL is the existing authenticated route
(`/api/inference/assets/<id>/`), which already streams from MinIO.
(Owner-gated today — see Open Questions on whether generated images
should be shareable/public.)

### 3.4 Guardrails (settings)

- `IMAGE_MAX_PROMPT_CHARS` (e.g. 4000).
- `IMAGE_MAX_N` (e.g. 4) — clamp `n`.
- `IMAGE_MAX_UPLOAD_BYTES` (edits/mask input, e.g. 25 MB) +
  content-type allowlist (png, jpeg, webp), reusing the STT pattern.
- `IMAGE_ALLOWED_SIZES` optional — otherwise pass `size` through.

### 3.5 Routing + catalog

- Reuse `_find_provider_for_model(..., service_type="image")` — already
  threaded through the matchers. An image request only lands on an
  `image` service.
- `_model_caps` already surfaces `service_type`; the image model reports
  `service_type="image"`, `output_modalities=["image"]`.
- `hf_enrich`: image models (pipeline_tag `text-to-image`) →
  input `["text"]`/`["text","image"]`, output `["image"]`.

---

## 4. Agent changes (`inference-club-agent`)

- Add `image` to `SERVICE_TYPES` (manifest validation).
- Router: route `POST /v1/images/generations` and
  `POST /v1/images/edits` to the `image`-typed backend via the existing
  `serveByType` (the multipart/JSON body streams through untouched —
  same as the STT transcription route). No model-peeking needed; the
  `/v1/images/*` paths are unambiguous.
- Update the example `agent.yaml` and ROADMAP.

> Cross-repo contract: the agent PR implements §2 (validation) + §4
> (routing) against this document.

---

## 5. Frontend changes (`frontend/`)

### 5.1 A dedicated Images playground

New page `dashboard/playground/images` (sibling to `chat` and
`transcribe`), added to the dashboard nav under Playground. It:

- lists models filtered to `service_type === 'image'`;
- has a prompt box, `n` / `size` / (optional `quality`) controls;
- has an **optional source-image upload** (drag/drop) — when present the
  request goes to `/v1/images/edits`, otherwise `/v1/images/generations`;
- renders results as a gallery of `<img>` (from the returned asset URLs)
  with download + "open" affordances and a spinner while generating.

A `useImageGeneration()` composable (sibling to `useTranscription`)
owns the JSON/multipart POST + CSRF/session handling and returns asset
URLs.

### 5.2 History, cards, profile, docs

- `InferenceRequestCard.vue`: handle `IMAGE` — show a thumbnail (first
  output asset), the prompt preview, and an image-count chip.
- Request detail page: render the prompt, the input image (for edits),
  and the output gallery via the asset URLs.
- `[username].vue`: served image models render via `ModelCapabilities`
  (text→image) with a curl/python example for `/v1/images/generations`.
- **Docs:** new `content/docs/api/images.md` (both endpoints, multipart
  fields, response shaping, the "we store + return a URL" behavior,
  metering by image count); update `api/overview.md` (endpoint list) and
  `concepts.md` (the `image` service type).

---

## 6. Infrastructure

No new infra — this is the payoff for the STT chapter. Generated images
land in the **same MinIO bucket** (`inference-club-media`) under the
`output_image/` and `input_image/` prefixes via `MediaAsset`. Confirm
the prod bucket lifecycle/retention story is shared across modalities
(see Open Questions).

---

## 7. Testing

- **Live e2e:** drive a prompt through
  `inference.club/v1/images/generations` against the real image agent;
  assert a PNG `OUTPUT_IMAGE` asset is stored in MinIO and the response
  URL streams it back. Repeat for `/v1/images/edits` with a source image
  (assert an `INPUT_IMAGE` asset too).
- **Backend units:** JSON + multipart parsing/guardrails; provider
  resolution honors `service_type="image"`; `b64_json` forced upstream;
  response shaping (`url` default vs `b64_json`); `n` clamping;
  `image_count` recorded; `INPUT_IMAGE`/`OUTPUT_IMAGE` assets created.
- **Frontend:** image composable posts JSON and multipart; gallery
  renders from asset URLs; edits path triggered by a source image.

---

## 8. Out of scope / deferred

- `/v1/images/variations` (the user didn't ask; trivial to add later on
  the same base).
- **Async job + poll** — the IR-up-front design leaves room, but v1 is
  synchronous.
- Streaming/progressive image previews.
- Video generation (would likely revisit the presigned-upload transport
  for large payloads).
- A per-image billing/leaderboard surface (`image_count` lands now; the
  stat is a fast follow, mirroring `audio_seconds`).

---

## 9. Open questions for review

1. **Are generated images shareable?** The asset route is owner-gated
   today. Options: keep owner-only (private, simplest) / make an output
   image viewable by anyone with the link (so it can show on the public
   profile and be embedded). Proposed: **owner-only for v1**, revisit
   when profiles surface image history.
2. **Retention / GC of media.** STT audio + now images accumulate in
   MinIO. Proposed: ship `image_count`/assets now, add a retention job
   (size- or age-based) as a separate task — flagged, not built.
3. **`quality`/`size`/extra params passthrough.** Proposed: pass through
   `size`, `quality`, `style`, `background` etc. verbatim to the
   upstream (the server ignores what it doesn't support), only clamping
   `n` and validating the source-image upload.
