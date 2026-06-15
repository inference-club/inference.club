# PRD 12 — Media Pipeline & Narration Studio

> **Status:** Draft / roadmap (2026-06-14). Nothing in the feature phases (V0–V5)
> is implemented yet. What *is* shipped alongside this PRD is the **admin
> roadmap surface** that tracks it (see §9): `apps/inference/roadmap.py` (the
> living, git-versioned tracker), `AdminRoadmapView` in `staff_views.py`
> (`/api/admin/roadmap/`, `IsStaff`), and `pages/dashboard/admin/roadmap.vue`
> (nav `dashboard.items.roadmap`). The structured tracker in `roadmap.py` is the
> source of truth for status; this document is the prose behind it.
>
> **Builds on:** PRD 10 (async jobs, batches, DAG engine, capacity gating) and
> PRD 11 (Workflow Studio: authoring canvas, prompt node, structured output,
> single-step rerun). This PRD is essentially **PRD 11 V3+V4 ("multimodal
> compositing", "library/sharing") expanded into a full programme**, plus a new
> dedicated review surface (the Narration Studio) that the workflow engine alone
> can't express.
>
> **Source material:** two existing repos of Brian's whose patterns we are
> adapting — `~/git/hn.fm` (URL → podcast-with-video pipeline) and
> `~/git/inference-club-studio` (the **Narrations** review app). §3 summarises
> both. Their design notes live in this repo's exploration history; this PRD is
> the adaptation.
>
> **Author:** Brian (product direction) · drafted with Claude Code.

---

## 1. Summary

inference.club can already *run* a DAG of inference steps (PRD 10) and let users
*author* one on a canvas (PRD 11). What it cannot yet do is the thing the two
reference repos do well: take a single seed (a URL, an article, a script) and
fan it all the way out to a **finished, narrated, subtitled, illustrated video**
— with every intermediate artifact (dialog line, audio take, image, caption,
clip) **traceable back to its component parts** and **independently
re-runnable**. And it has no **review surface** for the part of that pipeline
that is inherently human-in-the-loop: listening to narration takes, trimming
dead air, cleaning audio, picking the best retake, and steering the images that
accompany each line.

This PRD defines two interlocking tracks, both expressed on the existing
workflow/job engine:

- **Track A — Media Pipeline** (adapted from **hn.fm**): new node kinds
  (`scrape`, `dialog`, `transcribe`, `subtitle`, `compose`) and a durable
  **media-asset model with provenance**, so an end-to-end "URL → video" workflow
  is a first-class, forkable, re-runnable graph.
- **Track B — Narration Studio** (adapted from **inference-club-studio**): a
  dedicated review app for audio narration — segments, **retakes/variants**,
  **headspace trimming**, **StudioVoice cleaning**, **Dia voice samples**, a
  **waveform timeline with word-level highlight**, and **dynamic per-segment
  image series** (LLM-planned, image-to-image continuity).

The two tracks share one substrate (jobs, capacity gating, media assets, Dia
voice cloning, STT, image/video/music modalities — all already present) and feed
each other: the Studio is the hands-on front end for the same segments a Media
Pipeline workflow produces, and a polished Studio episode can be "sent to a
compose workflow" to render the final video.

---

## 2. What does NOT change (load-bearing promises)

- **The sync inference path is untouched.** Everything here runs on the async
  queue (PRD 10) and is gated by `ASYNC_ENABLED`. A sync-only deployment loses
  these features and nothing else.
- **The workflow spec format is additive.** New node `kind`s extend the existing
  `steps[]`/`depends_on`/templating contract (PRD 10 §5.5, PRD 11). Existing
  workflows keep validating and running unchanged.
- **No new always-on infrastructure for V0–V2.** Render/compose work is a Celery
  task on the existing worker; Firecrawl/FFmpeg are invoked by the **provider
  agent** (same proxy model as every other modality), not added to the Django
  box. New heavy services (StudioVoice, frame-interpolation, music) follow the
  established "declare it in the manifest, the agent serves it" contract
  (see `project_model_capabilities`).
- **Media assets are pointers, not blobs.** Following hn.fm and our existing GCS
  story (`project_gcs_media`), every generated artifact is a file URL + metadata
  row, never binary in the DB.

---

## 3. Source material (what we're adapting)

### 3.1 hn.fm — the URL→video pipeline

A Python (FastAPI + Celery + Redis) pipeline that turns a Hacker News article
into an AI podcast with video. Stages, each a discrete, independently re-runnable
Celery task chained with `continue_chain=True`:

1. **HN fetch** (Firebase HN API) → item
2. **Scrape** (Firecrawl) → raw markdown
3. **Clean** (regex) → normalized text
4. **Summarize/enrich** (local LLM) → summary, tags, emoji, haiku
5. **Dialog script** (LLM) → `[S1]/[S2]` two-speaker transcript
6. **TTS** per section (2 dialog lines = 1 section) → WAV per section
7. **Audio cleaning** (NVIDIA NIM **StudioVoice**, gRPC) → polished WAV
8. **Stitch** (pydub) → one combined WAV
9. **ASR** (WhisperX) → word-level timestamps `{word, start_ms, duration_ms}`
10. **Image prompts** (LLM, per section) → prompt strings
11. **Images** (InvokeAI/Flux) → PNG per section
12. **Subtitles** (custom) → ASS/VTT, word-synced
13. **Video compose** (FFmpeg + timeline builder) → MP4

**Patterns worth stealing:**

- **Provenance everywhere.** Each artifact stores its source key: an image knows
  its section text + prompt; an audio section knows its line text. Disk layout
  mirrors the data model (`.../runs/{run}/segments/{seg}/images/{idx}/`).
- **Versioning via counters.** A new run / segment is a *new id*, old one
  preserved — non-destructive re-runs and script variants for free.
- **Timeline as the sync contract.** Alignment metadata `(start_ms, duration_ms)`
  is computed once from ASR and reused by the image, subtitle, and video steps.
  This generalises to *any* time-based composition (3D, music, captions).
- **Fan-out / fan-in shape.** One run → many segments (fork at script);
  one segment's audio+images → one video (merge at compose). This is exactly our
  `map`/`collect` node vocabulary.

### 3.2 inference-club-studio — the Narrations review app

Nuxt 3 + FastAPI + (SQLite for narration, Postgres for images) + Celery. The
**Narrations** feature is a timeline-based audio-narration studio:

- **Segments**: paste a script (one line per segment) or an article that an LLM
  splits + sanitises; drag-reorder; inline edit; per-segment status.
- **Retakes (variants)**: every generation is a `variant` row; the segment has a
  `selected_variant_id`. Regenerate → new variant, auto-selected; A/B compare in
  the UI; deleting a variant falls back to the next best.
- **Headspace trim**: pydub `seg[start_ms:end_ms]` in place; interactive waveform
  canvas with drag handles; "Preview" then "Apply"; auto re-transcribe after.
- **StudioVoice cleaning**: optional denoise/enhance; stored as a *separate*
  `studio_voice_audio_path` with its own status (`not_cleaned`/`cleaned`/
  `unavailable`/`error`) so the original is never lost.
- **Dia voice samples**: upload WAV + transcript → reference for Dia cloning;
  per-segment voice override (`voice_sample_id`); project default voice.
- **Transcription + word highlight**: STT returns `{text, words:[{word,start,end}]}`;
  the timeline renders a karaoke-style highlight and seek-to-word.
- **Dynamic image series** (the standout): per segment, an LLM reads the segment
  text + a "creative direction" and emits a **plan** (`plan_json`) of N frames
  with parent/child links and `text_to_image`/`image_to_image` modes;
  `image_to_image` frames inherit the parent's output for **visual continuity**;
  a "suggest next prompts" loop keeps the series coherent. Frames carry full
  generation params + `output_image_path`.
- **Export**: concatenate selected variants with configurable gaps, fade,
  LUFS normalize → WAV/MP3. (Blender export exists but is shallow/deferred.)

**Patterns worth stealing:** the variant/selected model, in-place trim with
re-transcribe, the keep-original cleaning pattern, the per-segment voice
override, and above all the **LLM-planned image series with image-to-image
continuity**.

---

## 4. Current state (what we already have to build on)

| Capability | Where | Today |
|---|---|---|
| Async job queue + dispatcher + capacity gating | `jobs.py`, `tasks.py` | ✅ PRD 10 |
| DAG engine: `inference`/`map`/`transform`/`collect`/`gate`/`prompt` | `workflows.py` | ✅ PRD 10/11 |
| Visual builder, fork/run, structured output, single-step rerun | `WorkflowBuilder.vue`, `useWorkflowSpec.ts` | ✅ PRD 11 |
| Modalities: LLM, IMAGE, VIDEO (LTX-2), MUSIC, TTS, **VOICE (Dia)**, **STT**, MESH (TRELLIS) | `openai_views.py` | ✅ |
| Dia voice cloning with samples | VoiceGenerationsView, `VoiceSample` | ✅ PRD 09 |
| Media on GCS, served directly | `project_gcs_media` | ✅ |
| Admin staff surface (activity, moderation, access) | `staff_views.py`, `/dashboard/admin/*` | ✅ |

**The gaps this PRD closes:** (a) no `scrape`/`transcribe`/`subtitle`/`compose`
node kinds; (b) no durable, provenance-bearing **media-asset** model distinct
from a one-shot `InferenceRequest.results`; (c) no human-review surface for
narration (retakes, trim, clean, voice, image series); (d) no final-render
(video compose) worker; (e) no advanced compositing (HyperFrames overlays, 3D,
Blender export).

---

## 5. Design

### 5.1 Media assets & provenance (the spine — V0)

Today a job's output lives in `InferenceRequest.results`. That's fine for one
shot, but a pipeline needs artifacts that **outlive a single request**, **link to
their inputs**, and can be **re-pointed when a node re-runs**. We already have a
durable **`MediaAsset`** model (`apps/inference/models.py`: `user`, `kind`,
`file` on GCS, `content_type`, `size_bytes`, `duration_seconds`, `metadata`
JSON, FK `inference_request`) used by STT/TTS/image/video/3D. V0 **extends it**
rather than adding a parallel model:

- **New kinds**: `INPUT_DOC` (scraped markdown), `OUTPUT_DOC` (generated
  script), `OUTPUT_SUBTITLE` (ASS/VTT, public). *(shipped — migration 0028)*
- **`derived_from`** — a self M2M (`related_name="derivatives"`) recording the
  upstream asset(s) an artifact was produced from, plus a `record_derivation()`
  helper. *(shipped)* Provenance = `inference_request` (which job + prompt/params)
  **+** `derived_from` (which assets). This is hn.fm's "source key", normalized.
- **Later**: `episode`/`segment` FKs (V3, with the Episode model).
- **Workflow steps emit assets.** A `compose`/`tts`/`image` step's output value
  references `MediaAsset` ids in the run context, so `{{ steps.tts.output.assets }}`
  is a list of durable URLs, not a transient blob. Re-running a step mints new
  assets and re-points downstream — old assets stay (versioning by id, à la
  hn.fm counters).

*Out of scope for V0:* a media-asset *browser* UI; assets are addressable but
surfaced through the existing gallery/queue until V3.

### 5.2 New node kinds (V0–V2)

All extend the PRD 10/11 spec contract (additive `kind`s, same templating):

| Kind | Phase | Consumes | Produces | Backed by |
|---|---|---|---|---|
| `scrape` | V0 | `url` | doc asset (markdown + title) | provider agent → Firecrawl (new `service_type: scrape`) |
| `transcribe` | V0 | audio asset | text + `words[]` (timestamps) | existing STT modality, wrapped as a node |
| `compose` | V0 | images/audio/subtitles + timeline | video asset (MP4) | render worker (FFmpeg) — agent `service_type: render` |
| `dialog` | V1 | text/summary | `[S1]/[S2]` script (structured) | `prompt`/LLM node + `response_schema` |
| `tts-clone` | V1 | dialog sections + voice sample | audio asset per section | existing VOICE (Dia) via `map` |
| `clean` | V1 | audio asset | cleaned audio asset (kept separate) | StudioVoice (new `service_type: audio-enhance`) |
| `stitch` | V1 | audio assets[] | combined audio + section offsets | `transform` (pydub on worker) |
| `subtitle` | V2 | `words[]` + style | ASS/VTT subtitle asset | `transform` (worker) |
| `image-series` | V2 | segment text + direction | plan + image assets[] | LLM plan node + IMAGE `map` (i2i continuity) |

> `scrape`, `clean`, `audio-enhance`, `render` are **new manifest service
> types**: a provider declares them in `agent.yaml`, `manifest_validator`
> accepts them, and they route through the same proxy as every other modality
> (`project_model_capabilities` contract). No special-casing in Django.

### 5.3 The Episode (Track A's unit of work)

hn.fm's "run + segments" becomes an **`Episode`**: a named container that owns an
ordered list of **`Segment`s** (dialog line(s) + their audio variants + image
series + alignment) and links to the `Workflow`/`WorkflowRun` that produced it.
An Episode can be born two ways: **(1)** a Media Pipeline workflow writes it, or
**(2)** a user creates it by hand in the Narration Studio (§5.4). Same model,
two front doors. The Episode is the join point between the two tracks.

### 5.4 Narration Studio (Track B — V3)

A dedicated surface at `/dashboard/studio` (and `/dashboard/studio/[episode]`),
adapting inference-club-studio's `NarrationWorkspaceNext`. It reads/writes
`Episode`/`Segment`/`Variant`/`ImageSeries` and drives the existing job engine.
Components (ported to our Nuxt + shadcn + Vue stack):

- **Segment list** — reorderable cards; inline text edit; status; per-segment
  voice override (Dia sample picker).
- **Waveform timeline** — combined audio with word-level highlight from the
  `transcribe` node; click-to-seek; variable speed.
- **Retakes panel** — `Variant` rows per segment; generate/regenerate;
  A/B player; select active; auto-fallback on delete.
- **Trim panel** — drag-handle waveform; preview/apply in-place; auto
  re-transcribe (a small `transform` job).
- **Clean toggle** — fire a `clean` (StudioVoice) job; show cleaned-vs-original;
  never destroy the original.
- **Voices dialog** — manage Dia voice samples (upload WAV+transcript, preview,
  set default/per-segment) — reuses PRD 09 `VoiceSample`.
- **Image-series panel** — per segment: "auto" (LLM plan from creative
  direction + target count) or "manual" (seed prompt); frame gallery with
  image-to-image continuity, per-frame regenerate, "suggest next prompts".
- **Export bar** — concatenate selected variants (gaps/fade/normalize) → audio
  asset; "Send to compose workflow" → render the illustrated, subtitled video.

Everything here is **just orchestration over jobs**: each button enqueues a job
(or a tiny workflow) and polls. The Studio is the human-in-the-loop face of the
same engine the Media Pipeline runs headless.

### 5.5 Advanced compositing & 3D (V4)

The "almost infinite ways to combine media" track. All as `compose`-family nodes
and Studio options:

- **HyperFrames** title cards, lower-thirds, animated text, chapter headers,
  alpha overlays (image-on-bg + text), audio-reactive motion — rendered to clips
  the `compose` node lays onto the timeline.
- **Image→video** per section (LTX-2, already a modality) instead of static
  slides; optional **frame interpolation** (new service) and effects/filters.
- **Music bed** (existing MUSIC modality) ducked under narration.
- **3D**: TRELLIS meshes (existing MESH) and ThreeJS scenes composited into the
  video; image+video+3D mixes.
- **Blender export** (from inference-club-studio): export an Episode's
  segments/audio/images/timeline as a `.blend` + Python build script — the
  "node workflow → Blender scene" representation Brian wants, while keeping the
  canonical graph in inference.club.

### 5.6 Re-runnability, versioning, forking

Already native to the engine and extended by §5.1: single-step rerun (PRD 11)
re-mints a node's assets and re-flows downstream; workflows fork (PRD 11
`from-run`/`from-template`); Episodes/Segments/Variants version by id (hn.fm
counter pattern). The promise "re-runnable from any node, completely
regenerated, versioned, forked" is met by composing these, not by new
machinery.

---

## 6. API surface (incremental)

| Endpoint | Phase | Purpose |
|---|---|---|
| `POST /v1/workflows/runs` with `scrape`/`compose` steps | V0 | run a media pipeline |
| `GET /v1/assets/<id>` | V0 | resolve a media asset + provenance |
| `GET/POST /v1/episodes`, `/v1/episodes/<id>` | V3 | Episode CRUD |
| `POST /v1/episodes/<id>/segments` (+ reorder) | V3 | Segment CRUD |
| `POST /v1/segments/<id>/regenerate` → variant | V3 | retake |
| `POST /v1/segments/<id>/variants/<vid>/select` | V3 | pick active take |
| `POST /v1/segments/<id>/trim` | V3 | headspace trim + re-transcribe |
| `POST /v1/segments/<id>/clean` | V3 | StudioVoice |
| `POST /v1/segments/<id>/image-series/auto`/`/manual` | V3 | dynamic images |
| `POST /v1/episodes/<id>/export` / `/render` | V3 | audio export / compose video |
| `GET /api/admin/roadmap/` | **shipped** | this roadmap (staff) — §9 |

---

## 7. Infra & ops

- **New manifest service types**: `scrape`, `render`, `audio-enhance`,
  `frame-interp` (V4). Each declared in `agent.yaml`, validated by
  `manifest_validator`, routed by `service_type` — capacity-gated by
  `max_concurrent`/`resource_group` (PRD 10) since render/clean are GPU/CPU-heavy
  and want serialization.
- **Render worker**: FFmpeg compositing as a Celery task (or, preferably, an
  agent-side `render` service so the heavy lifting stays on provider hardware,
  consistent with our proxy model). Decide at V0 (open question §10).
- **Storage**: all assets to GCS (`project_gcs_media`); thumbnails via the
  existing image pipeline (`project_media_playback`).
- **Migrations**: `MediaAsset`, `Episode`, `Segment`, `Variant`, `ImageSeries`,
  `ImageFrame` (DRF serializers + Nuxt composables per house pattern). Land in
  phase order, not all at once.

---

## 8. Rollout

| Phase | Headline | Gate / proof of success |
|---|---|---|
| **V0** | Foundations: `MediaAsset` + provenance, `scrape`/`transcribe`/`compose` nodes | A saved workflow takes a URL → scraped doc → (canned narration) → slideshow MP4, fully re-runnable per node |
| **V1** | Dialog & audio pipeline: `dialog`/`tts-clone`/`clean`/`stitch` | URL → `[S1]/[S2]` script → Dia-cloned, StudioVoice-cleaned, stitched narration track |
| **V2** | Subtitles & illustrated video: `subtitle` + `image-series` + timeline align | The full hn.fm flow as one inference.club workflow: URL → narrated, subtitled, illustrated MP4 |
| **V3** | **Narration Studio**: Episode/Segment review app (retakes, trim, clean, voices, image series, export) | A user hand-builds & polishes an episode in the Studio and renders it |
| **V4** | Advanced compositing & 3D: HyperFrames, image→video, frame-interp, music bed, ThreeJS/TRELLIS, Blender export | An episode rendered with title cards + a 3D scene + music; Blender export opens |
| **V5** | Sharing & roadmap surfaces: pipeline templates, episode sharing, **public roadmap** | Template gallery for these pipelines; public roadmap live |

---

## 9. Admin roadmap surface (shipped with this PRD)

So this programme is reviewable in-app and survives interruption, the structured
tracker is **`apps/inference/roadmap.py`** (phases → tasks → status + a progress
log), served by **`AdminRoadmapView`** (`GET /api/admin/roadmap/`, `IsStaff`) and
rendered at **`/dashboard/admin/roadmap`** (nav `dashboard.items.roadmap`,
`staffOnly`). `roadmap.py` is the source of truth for *status*; this document is
the *prose*. Update both as phases land. The page is built so a **public
roadmap** (V5) can reuse the same data shape with the staff gate removed and
internal notes filtered out.

---

## 10. Open questions

1. **Render location**: FFmpeg on the Django/Celery worker vs. an agent-side
   `render` service on provider GPUs. Leaning agent-side (consistent proxy
   model, keeps heavy deps off the web box) — confirm at V0.
2. **Narration store**: extend the main Postgres models (Episode/Segment/Variant)
   vs. a separate service like inference-club-studio's SQLite. Leaning main
   Postgres for one provenance graph and reuse of auth/visibility.
3. **Timeline alignment authority**: ASR-derived (hn.fm) vs. TTS-reported
   durations. Probably ASR for word-level, TTS for coarse — store both.
4. **Where does HyperFrames render** (V4): agent service vs. a Node sidecar?
5. **Asset GC**: when a node re-runs, orphaned assets accumulate. Retention
   policy / "prune old variants" — V3+.
