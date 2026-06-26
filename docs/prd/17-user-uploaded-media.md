# PRD 17 — User-Uploaded Media & the Media Library

> **Status:** Drafted (2026-06-25), not yet implemented. Make user-uploaded media
> a **first-class, private-by-default, owner-owned** resource: one upload API, one
> storage model, one privacy rule. Close the existing byte-level privacy leak,
> stop losing chat/agent attachments on save, and give every user a browsable
> **Media Library** they can manage and re-process with inference.club services.
>
> **Builds on:** the `MediaAsset` model + `derived_from` provenance graph (PRD 12),
> the GCS two-bucket storage backend (`backend/backend/storage.py`), the
> `InferenceRequest.visibility` sharing model (PRD 01), the OpenAI-compatible
> `/v1/*` API + DRF Bearer/session auth, and PRD 10 async jobs (for re-processing).
>
> **Sets up:** PRD 18 — Semantic Media Embeddings (search & RAG over the Library).
>
> **Author:** Brian (product direction) · drafted with Claude Code.

> **Progress** — **V0 SHIPPED (2026-06-25):** `MediaAsset.visibility` (default
> SECRET/owner-only) + opaque `public_id` + the single `is_visible_to` audience
> rule + `is_world_public`; both serving routes (`/api/inference/assets/<ref>/`
> bytes and `/v1/assets/<ref>` metadata) now gate by audience and accept the
> opaque id (legacy int ids still resolve, now gated); `asset_url()` only ever
> emits the gated app route — no direct bucket URL. Migration `0042` adds the
> fields + backfills `public_id`. The leak is closed: a SECRET request's image is
> unreachable by non-owners on every route and its permanent URL is never emitted
> (owner gets it streamed, not redirected). 35-case privacy matrix
> (`test_media_privacy.py`) + full inference suite green (529 passed). The
> physical public-bucket→private object move is intentionally deferred to V1
> (kind-based bucket routing untouched; new non-public objects keep a random-UUID
> key and are never addressable via an app-emitted URL).
>
> **Progress** — **V1 part 1 SHIPPED (2026-06-25):** the `/v1/files` Media Library
> API — `POST` (multipart upload → owner-only `MediaAsset`), `GET` (owner-scoped
> list with kind/bound/q filters + pagination), `GET/PATCH/DELETE /v1/files/<ref>`
> (audience-gated read; owner-only publish/metadata/delete, guests clamped off
> PUBLIC), and `GET /v1/files/<ref>/content` (audience-gated bytes, reusing the
> shared `serve_media_asset`). New central `apps/inference/uploads.py`
> (`validate_upload`/`store_upload`, consolidating the per-modality size/type
> caps; 413/415) + `MEDIA_MAX_UPLOAD_BYTES`; new `INPUT_VIDEO` kind (migration
> `0043`, routed to the private bucket). 12 API tests green. **Remaining in V1:**
> chat/agent attachment **persistence + rendering** (the placeholder fix) — store
> uploads as assets referenced (not base64) in payloads/threads, resolve refs to
> a provider-fetchable form at dispatch, render in request-detail + chat-thread.
>
> **Progress** — **V1 part 2a SHIPPED (2026-06-25):** the **chat-thread** half of
> the placeholder fix. New shared `useUploads` composable (the one client for
> `/v1/files`); the chat playground now uploads each attachment to the Library in
> the background, persists the gated asset **URL + opaque id** in the
> `ChatThread` (never the base64), and re-renders image/audio/video on reopen —
> both in the live history and the `/dashboard/chats/<id>` viewer. Continuing a
> hydrated thread refetches the bytes (credentialed) so the model still receives
> the media; in-flight uploads are awaited before save. The agent playground has
> no user-upload UI, so nothing to change there. **Still open:** the
> **InferenceRequest request-log** half — the `/v1/chat/completions` proxy still
> stores base64 in `payload` (renders as `[image_url]` in the request-detail
> Messages list). That needs the proxy ref-resolution (store ref, inline base64
> to the provider, bind assets to the request) + serializer `content_parts`, and
> is the remaining V1 task before V2 (the Library UI).

---

## 1. Summary

Today, media only ever exists *attached to a generation*. There is no concept of
"my uploads," uploaded inputs are handled five different ways across the app, and
— most importantly — **the privacy story is wrong**:

- **Byte access is gated only by `kind`, not by the parent request's visibility.**
  A `SECRET` request's output (or input) image is **world-readable** by direct
  URL (`MediaAssetView`, `views.py:3022`; public GCS bucket via
  `storage.py`). Asset URLs use a **sequential integer id**
  (`assets/<int:id>/`), so they are trivially enumerable.
- **Chat/agent inline media is dropped on save.** When you attach an image in the
  LLM playground, it is sent as a base64 `data:` URL inside the chat `content`
  array, the serializer flattens it to the literal string `[image_url]`
  (`_stringify_content`, `serializers.py:214`), and the `ChatThread` save copies
  **text only** (`index.vue:283`). No `MediaAsset` is created. Reopening the
  thread shows the placeholder text you described — the image is simply gone.
- **There is no Media Library.** Nothing surfaces a user's uploaded source media
  as a browsable, manageable collection.

This PRD makes user-uploaded media a real thing:

1. **One privacy rule** — an asset's audience is *derived* from its context
   (parent request, or its own visibility), **private by default**, and enforced
   on every byte. (§4 — this is the heart of the PRD.)
2. **One upload API** — an OpenAI-style `POST /v1/files` that stores the upload as
   a private `MediaAsset` and returns a stable, opaque reference. Chat, agent, and
   every per-modality playground funnel through it. (§5)
3. **Persist & render attachments** — chat/agent uploads become real assets,
   referenced (not inlined) in stored payloads, and rendered when you reopen an
   old request or thread. (§6)
4. **A Media Library** — `/dashboard/media`, owner-only, where you browse, manage
   visibility, see where each asset was used (provenance), and **re-process** it
   with inference.club services (transcribe, edit, animate, describe, embed). (§7)

---

## 2. Goals & non-goals

**Goals**
- Every uploaded byte respects the visibility of the context it belongs to;
  private by default; the existing leak is closed (including objects already in
  the public bucket).
- Reopening any old request or chat/agent thread renders the media that was part
  of it — never placeholder text.
- A single, validated, reusable upload path replaces the five fragmented ones.
- A user can find, view, manage, delete, and re-process their own uploads in one
  place; only they can see them unless they explicitly publish.
- Provenance: every derived artifact traces back to the upload it came from.

**Non-goals (this PRD)**
- Semantic / vector search — that is **PRD 18** (this PRD ships the data model and
  Library surface it plugs into).
- Per-org / shared-team media, folders, or quotas (future).
- Re-architecting the per-modality *generation* endpoints themselves — only their
  *upload* step is unified.

---

## 3. Current state (verified)

| Concern | Where | Today |
|---|---|---|
| Blob model | `MediaAsset` `models.py:989` | Generic, `kind`-discriminated (INPUT/OUTPUT × image/audio/video/doc/model/subtitle), FK `user` + `inference_request`, `derived_from`↔`derivatives` provenance. **No `visibility` field.** |
| Byte privacy | `MediaAssetView` `views.py:3022`; `job_views.py:742`; `storage.py` | Gated **only** by `kind ∈ PUBLIC_KINDS`. Public kinds served from a public GCS bucket (no signing, immutable CDN). **Does not consult `inference_request.visibility`.** |
| Asset id | `urls.py:157` `assets/<int:id>/` | Sequential integer — enumerable. No opaque id on `MediaAsset` (unlike `InferenceRequest.public_id`). |
| Request privacy | `InferenceRequest.visibility` `models.py:756` | 4-tier PUBLIC/UNLISTED/PRIVATE/SECRET, `is_visible_to(user)` `models.py:862`. Governs **pages/listings**, *not* bytes. |
| Dedicated modalities | image-edit `openai_views.py:2696`, i2v `:2447`, mesh `:3134`, STT `:761`, enhance `:1433` | **Correctly** store inputs as `MediaAsset(kind=INPUT_*)` and render them on request-detail (`ImageGenMedia`, posters). Not the problem. |
| Chat inline media | `index.vue:228` `mediaPart`; `_stringify_content` `serializers.py:214`; `index.vue:283` `serializeMessages` | Base64 inlined into `content`; flattened to `[image_url]` on read; **attachments dropped** on `ChatThread` save. No asset created. **This is the "placeholder text" gap.** |
| Upload UI | per-playground; `useImageGeneration.ts`, `useTranscription.ts`, etc. | Mature but **fragmented** — base64-in-JSON for chat, multipart `FormData` per modality, a `csrf()` helper duplicated in each composable. No shared client. |
| Library | — | **Does not exist.** Every gallery is keyed off `InferenceRequest.inference_type`; uploads are never browsable on their own. |

The good news: the schema is already media-capable and provenance-aware. The work
is a **privacy rule**, an **upload API**, **attachment persistence**, and a
**Library surface** — not a new storage model.

---

## 4. The privacy model (the core of this PRD)

### 4.1 One question, one function

Every access decision reduces to: **may user `X` see asset `A`?** We replace the
kind-based gate with a single derived **audience function**:

```
def asset_is_visible_to(A, X):
    if X is A.owner:                      return True          # owner always
    if A.visibility == PUBLIC:            return True          # explicitly public
    if A.inference_request is not None:                        # bound to a request
        return A.inference_request.is_visible_to(X)            # follows the request
    return False                                              # standalone & private
```

Read it as a precedence ladder:

1. **Owner** always sees their own media.
2. **Explicitly public** assets are world-readable (the user opted in).
3. **Bound to a request** → the asset inherits the request's audience. Share the
   request publicly and its media becomes viewable by that same audience; an
   `UNLISTED` request's media is reachable by link; a `SECRET` request's media is
   owner-only. *This is exactly "respect the visibility of the request it is part
   of."*
4. **Standalone & not public** → owner-only. **This is the default.**

`A.visibility` is a new field on `MediaAsset`, default **`PRIVATE`**. It governs
standalone Library items and provides the explicit-publish override; the bound
case is governed by the request. (We deliberately do **not** let a private asset
override a public request downward — if you publish a request, you are publishing
its media; the Library's per-asset control is for *standalone* uploads.)

> **Why derive instead of copy?** Copying the request's visibility onto the asset
> would drift the moment a request is re-shared. Deriving means there is exactly
> one source of truth per context and "re-share the request" just works.

### 4.2 Opaque ids

Add `MediaAsset.public_id` (opaque token, mirroring `InferenceRequest.public_id`
from PRD 13). All external references use it. The sequential-integer route is
retired (or kept but hard-gated to owner) so assets can't be enumerated.

### 4.3 Byte serving & bucket routing (closing the leak for real)

The leak has two layers and both must close:

1. **The app route** (`/v1/files/<public_id>/content`) runs
   `asset_is_visible_to` before serving. Easy.
2. **The direct GCS URL.** Public-bucket objects are world-readable *by GCS*,
   independent of our app. So an object's **physical bucket must match its
   audience**, not its kind.

New routing rule (replaces `KindRoutedGCSStorage`'s kind logic):

- **Default: private bucket.** All new uploads and all request-bound media live in
  the **private** bucket. The content route does the access check, then **302s to
  a short-lived signed URL** (or streams) — works for every audience.
- **Promotion on publish.** When an asset becomes **world-public** — `A.visibility`
  set to `PUBLIC`, *or* its bound request transitions to `PUBLIC` — a Celery task
  copies the object to the **public** bucket (CDN, immutable) and records
  `A.public_url`. The content route then 302s to that stable public URL.
- **Demotion on un-publish.** The reverse transition deletes the public-bucket
  copy and clears `public_url`, so the only live bytes are private again.

> **V0 simplification:** promotion is a CDN optimization. V0 may serve *all* media
> (public included) through the access-checked content route with signed URLs and
> skip bucket-moving entirely — correct, just no edge cache. Promotion lands in V1
> once correctness is proven. At current scale this is a fine ordering.

### 4.4 The backfill migration (one-time, security-critical)

Existing rows currently rely on the kind→public-bucket mapping, so previously
"public" output images of non-public requests are **already exposed**. The
migration must:

1. Add `visibility` (default `PRIVATE`) + `public_id` + `public_url` columns.
2. **Backfill `visibility`** per row: an asset bound to a `PUBLIC` request → keep
   `PUBLIC`; everything else (bound to UNLISTED/PRIVATE/SECRET, or standalone) →
   `PRIVATE`.
3. **Move objects out of the public bucket** for every row that is now `PRIVATE`
   but physically sits in the public bucket: copy → private bucket, update the
   storage key, delete the public object. *Until an object is physically moved, a
   saved direct URL still works — so this step is mandatory, not cosmetic.* Run it
   as a management command with a dry-run + report; it's the actual leak closure.

### 4.5 Privacy test matrix (the proof gate)

A test module must assert the full cross-product before V0 ships:

`viewer ∈ {owner, other full member, guest, anonymous}` ×
`asset ∈ {bound→PUBLIC, bound→UNLISTED, bound→PRIVATE, bound→SECRET, standalone PRIVATE, standalone PUBLIC}` ×
`action ∈ {fetch bytes, fetch metadata, appears in my-library list, appears in public profile}`.

Expected outcomes follow directly from `asset_is_visible_to`. This matrix is the
definition of done for §4.

---

## 5. The upload API — `POST /v1/files`

One OpenAI-shaped endpoint, one validator, one model row.

| Endpoint | Purpose |
|---|---|
| `POST /v1/files` | Multipart upload. Body: `file` (required), `kind` (optional — auto-detected from content-type), `purpose` (optional, OpenAI-style: `vision`/`input`/`user_data`). Creates `MediaAsset(user=request.user, visibility=PRIVATE, inference_request=None)`. Returns `{id: public_id, object: "file", kind, content_type, size_bytes, duration_seconds, url, created_on}`. |
| `GET /v1/files` | List the **current user's** assets (owner-scoped). Filters: `kind`, `q` (filename/metadata search), `bound` (true/false — attached to a request or standalone), `visibility`. Pagination. Backs the Library. |
| `GET /v1/files/<public_id>` | Metadata + provenance (generalizes the existing `MediaAssetDetailView`). Access-checked via §4.1. |
| `GET /v1/files/<public_id>/content` | The bytes. Access-checked; 302 to signed/public URL or stream. |
| `PATCH /v1/files/<public_id>` | Owner-only. Set `visibility` (PUBLIC/PRIVATE), `title`, `metadata`. Triggers promote/demote (§4.3). |
| `DELETE /v1/files/<public_id>` | Owner-only. Deletes the row **and** the object(s) in both buckets. |

**Central validator** (`apps/inference/uploads.py`): consolidates the scattered
per-modality checks (`STT_MAX_UPLOAD_BYTES`, `IMAGE_ALLOWED_CONTENT_TYPES`, …) into
one `validate_upload(file, kind)` returning `(kind, content_type, size_bytes)` or
raising 413/415. Per-kind caps stay in settings; the *logic* lives in one place.

**Shared frontend client** (`composables/useUploads.ts` + a tiny `useApi` wrapper):
one `uploadFile(file, {kind, purpose})` → `{id, url, ...}`, with the CSRF/session
handling that is currently copy-pasted into every composable. The playgrounds call
this instead of re-implementing FileReader → FormData each time.

---

## 6. Persisting & rendering attachments (the placeholder fix)

The principle: **stored payloads reference assets; they never embed bytes.**

### 6.1 Chat & agent

1. On attach, the playground calls `uploadFile()` → gets a `public_id` + content
   URL.
2. The chat `content` part stores a **reference**, not base64:
   `{ type: "image_url", image_url: { url: "/v1/files/<pid>/content" }, asset_id: "<pid>" }`.
   `InferenceRequest.payload` and `ChatThread.messages` therefore stay small and
   re-renderable.
3. `MediaAsset.inference_request` is linked to the created request (and a new
   `ChatThread.assets` M2M ties uploads to the thread for listing + GC).
4. **At dispatch time**, the backend resolves each `asset_id` to a form the model
   server can actually fetch — a short-lived signed URL, or re-inlined base64 in
   the *outbound* provider payload only. Private bytes are **never** handed to a
   provider as a public URL, and the base64 is **never** persisted. (This cleanly
   separates "what we store" from "what we send.")

### 6.2 Rendering

- **Serializer:** `_stringify_content` keeps producing `[image_url]` for *plain
  text previews* (list cards), but the request-detail and chat-thread serializers
  gain a structured `content_parts` (or `media`) field that resolves `asset_id`s
  to access-checked viewable URLs.
- **Request detail** (`requests/[id].vue`): the LLM "Messages" section renders
  image/audio/video parts inline (reuse `ImageGenMedia` / `<audio>` / `<video>`),
  instead of only `MarkdownRenderer(m.content)`.
- **Chat thread** (`chats/[id].vue`): render multimodal user-message parts (today
  it only renders tool-output media and would show `[object Object]` for a
  structured user `content`). Stop dropping attachments in `serializeMessages`.

Net effect: open a year-old chat or request and the image/audio you uploaded is
right there.

---

## 7. The Media Library — `/dashboard/media`

Owner-only by default; the home for everything you've uploaded or generated.

- **Grid** backed by `GET /v1/files`, reusing existing cards (`VideoCard`,
  `ImageGenMedia`, `TrackList`, `InferenceRequestCard`). Filter by kind/modality,
  search by name, toggle standalone-vs-used.
- **Per-asset detail / drawer:** preview, kind, size, duration, created date,
  **where it was used** (the provenance graph — which requests consumed it,
  which artifacts derive from it), and visibility control (Private ⇄ Public,
  wired to §4.3 promotion).
- **Re-process actions** (§8): launch an inference.club service against the asset
  without re-uploading.
- **Privacy:** only the owner sees the Library. A future public profile "Media"
  tab would list only `PUBLIC` assets (reuses `asset_is_visible_to`).
- **Empty/first-run:** a clear "drag a file here or attach one in any playground"
  affordance, since uploads can originate anywhere.

---

## 8. Re-processing uploads with inference.club services

Provenance already exists (`derived_from` / `record_derivation`), so "process this
upload" is: create an `InferenceRequest` with the asset as input, link the result
back. From the Library (or an asset drawer), context-aware actions:

| Upload kind | Actions |
|---|---|
| Image | Edit (image-edit), Animate (image→video), Make 3D (mesh), Describe (vision LLM), **Embed** (PRD 18) |
| Audio | Transcribe (STT), Enhance (StudioVoice), **Embed transcript** (PRD 18) |
| Video | Transcribe, Extract frames (future), **Embed** (PRD 18) |
| Doc/text | Summarize, Ask (LLM), **Embed** (PRD 18) |

Each action reuses the existing modality endpoint, now fed an `asset_id` instead
of a fresh upload, and records a provenance edge so the Library shows the lineage.
This is also where the per-modality playgrounds migrate onto `/v1/files` (drop the
fragmented multipart paths).

---

## 9. Phasing

| Phase | Theme | Gate (proof of success) |
|---|---|---|
| **V0** | **Privacy first.** `MediaAsset.visibility` + `public_id` + `public_url`; `asset_is_visible_to`; access-checked content route by opaque id; the backfill/object-move migration. No new UI. | The §4.5 test matrix is green; a `SECRET` request's image is **not** fetchable by a non-owner via *any* URL, including the old direct one. |
| **V1** | **Upload API + attachment persistence.** `POST /v1/files` + central validator + `useUploads`; chat/agent store asset refs; dispatch-time resolution; serializer `content_parts`; render in request-detail + chat-thread. (Optional: bucket promotion for CDN.) | Attach an image in chat, reload a saved thread a day later → the image renders. Stored `payload` contains a ref, not base64. |
| **V2** | **Media Library.** `GET /v1/files` list + `/dashboard/media` grid + asset drawer + visibility toggle + where-used. | A user browses, searches, makes one asset public, deletes another — all owner-scoped and correct. |
| **V3** | **Re-process + unify.** Library "process" actions via provenance; per-modality playgrounds adopt `/v1/files`; retire the fragmented upload code + integer-id route. | From the Library, transcribe an uploaded audio and see the transcript linked as a derivative; no playground uploads via the old paths. |
| **→ PRD 18** | Semantic embeddings & search over the Library. | See PRD 18. |

---

## 10. Open questions

1. **Quotas / retention.** Standalone uploads that are never used — keep forever,
   or GC after N days unless used/pinned? (Lean: keep; revisit with storage cost.)
2. **Promotion timing.** Is the V0 "serve everything through the app" acceptable
   for public content's performance until V1 promotion lands? (Assumed yes at
   current scale.)
3. **Public profile media tab.** In scope for V2, or a later PRD? (Assumed later.)
4. **Dedup.** Hash-dedupe identical uploads per user (content-addressed), or allow
   duplicates? (Lean: store a content hash now in `metadata`, dedupe later.)
```
