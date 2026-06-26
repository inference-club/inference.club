# PRD 18 — Semantic Media Embeddings & Search

> **Status:** Drafted (2026-06-25), **not planned for the near term** — filed now
> so the Media Library (PRD 17) is built with this destination in mind. Index every
> piece of a user's media in a vector space so they can **search by meaning**
> ("the diagram about k3s networking", "where I talked about Hetzner pricing"),
> **find similar**, and eventually **ask questions over their own media** (RAG) —
> all powered by inference.club's own embedding services and a `pgvector` index in
> the existing Postgres.
>
> **Builds on:** PRD 17 (the `MediaAsset` model + Library + `asset_is_visible_to`
> privacy function), PRD 10 async jobs (embedding is a background job), the
> manifest/`agent.yaml` capability contract (new embedding service types), and the
> STT modality (audio/video → transcript → text embedding).
>
> **Depends on:** new cluster services that do not exist yet (a text-embedding
> model and an image-embedding/CLIP model). This PRD is **service-gated** — it
> ships when those services are served.
>
> **Author:** Brian (product direction) · drafted with Claude Code.

---

## 1. Summary

PRD 17 gives every user a Media Library. This PRD makes that Library *searchable
by meaning*. Each asset is embedded into a vector space — images via a CLIP-family
image encoder, audio/video via their transcript text, docs/text directly — and the
vectors live in `pgvector` inside our existing Postgres, joined to `MediaAsset`.

Three capabilities, in order of ambition:

1. **Semantic search** — "find my images of a 3D cluster diagram" or "the audio
   where I explained the tailnet bug." Text query → nearest assets.
2. **Find similar** — given an asset, surface its neighbors.
3. **Ask your media (RAG)** — retrieve the most relevant transcripts/docs/images
   for a question and answer with an LLM, citing the source assets.

The non-negotiable constraint: **embeddings inherit the privacy of their source
asset.** Search is scoped to what the viewer is already allowed to see
(`asset_is_visible_to` from PRD 17), enforced in the SQL join — vectors never leak
across users.

---

## 2. Goals & non-goals

**Goals**
- Semantically index all of a user's media (image / audio-via-transcript / video /
  doc / text) using inference.club's own embedding services.
- Cross-modal text→image search (type words, find images) via a shared CLIP space.
- A `pgvector` index in the existing Postgres — transactional, joinable to
  `MediaAsset`, privacy enforced by the same audience function.
- Search that is **strictly owner+public scoped**; deletion of an asset removes
  its embeddings.

**Non-goals**
- Embedding the *whole* world's media or building a public search engine.
- A standalone vector database (Pinecone/Weaviate/etc.) — we stay in Postgres.
- Real-time streaming embedding; batch/async on upload is fine.
- Fine-tuning embedding models.

---

## 3. Why `pgvector` in the existing Postgres

| Option | Verdict |
|---|---|
| **`pgvector` in our Postgres** | **Chosen.** One database, transactional with `MediaAsset`, ANN + relational filter (ownership/visibility) in a single query, no new infra, backs up with everything else. Scales comfortably to the millions-of-rows range this hobby cluster will ever see. |
| External vector DB | Rejected for now — second datastore, second privacy boundary, cross-store joins for the owner/visibility filter, more ops. |
| In-process FAISS | Rejected — no persistence/transactions, awkward multi-process, reinvents what `pgvector` gives free. |

Deployment note: the Hetzner Postgres (compose) needs the `pgvector` extension —
swap the image for a `pgvector`-enabled Postgres (e.g. `pgvector/pgvector:pg16`)
and `CREATE EXTENSION vector`. Use an **HNSW** index per vector column for ANN.

---

## 4. Data model

```python
class MediaEmbedding(BaseModel):
    asset        = FK(MediaAsset, on_delete=CASCADE, related_name="embeddings")
    space        = CharField(choices=["clip", "text"])   # which vector space
    model        = CharField()        # e.g. "siglip-so400m", "qwen3-embed-0.6b"
    dim          = IntegerField()     # 768 / 1024 / ...
    vector       = VectorField(dimensions=...)            # pgvector
    source_text  = TextField(blank=True)  # transcript/doc/caption actually embedded
    source_kind  = CharField()        # "image", "transcript", "doc", "caption"
    # Meta: HNSW index on `vector`; unique (asset, space, model).
```

Notes:
- **Two spaces, deliberately.** `clip` holds image vectors *and* CLIP-text-encoded
  query vectors (shared space → cross-modal text→image search). `text` holds
  transcript/doc/prompt vectors from a dedicated text-embedding model (better for
  long-form semantic search and RAG). A query routes to the space matching the
  target modality. Storing `space`/`model`/`dim` per row lets the two coexist and
  lets models be swapped/reindexed without a schema change.
- **Privacy by construction.** No vector exists without an `asset`; the asset's
  `visibility` + `inference_request` (PRD 17 §4) is the single source of truth.
  `CASCADE` means deleting an asset deletes its embeddings.
- A future generalization could embed `InferenceRequest` prompts / `ChatThread`
  messages too (global semantic recall); keep that out of V1 but the `space`/
  `source_kind` shape already accommodates it.

---

## 5. The embedding services (cross-repo contract)

Two new capabilities, declared in `agent.yaml` like every other modality (the
manifest ↔ agent `Model` struct ↔ `CatalogModel` contract), surfaced as a new
`EMBED` inference type:

| Service type | Model family | Produces |
|---|---|---|
| `embed-text` | a text embedding model (e.g. a Qwen-embed / sentence-transformer served via vLLM or LM Studio) | `text`-space vectors for transcripts, docs, prompts |
| `embed-image` | a CLIP/SigLIP image+text encoder | `clip`-space vectors for images **and** for text queries (cross-modal) |

API shape mirrors OpenAI embeddings: `POST /v1/embeddings` `{ model, input }` →
`{ data: [{ embedding: [...] }] }`. Internally the embed job calls this and writes
a `MediaEmbedding`. Service-gated: if no provider serves `embed-*`, the feature
preflight-fails gracefully (reuse PRD 10's `services_unavailable` 409 pattern).

---

## 6. The indexing pipeline

On asset creation (or via a backfill command for existing assets), enqueue an
async embed job (PRD 10 Celery infra):

1. **Resolve embeddable text/image:**
   - Image → embed the image with `embed-image` (clip space). Optionally also
     caption it (vision LLM) and embed the caption in text space.
   - Audio/Video → ensure a transcript exists (run STT if not, linking via
     `derived_from`), then embed the transcript with `embed-text`.
   - Doc/text → embed directly (chunk long docs; one `MediaEmbedding` per chunk
     with chunk offsets in `metadata`).
2. **Write `MediaEmbedding` row(s).**
3. **Idempotent & versioned:** `(asset, space, model)` is unique; re-embedding with
   a new model adds rows and a reindex command can retire the old `model`.

Backfill: `manage.py embed_assets [--space ...] [--model ...] [--dry-run]` walks
existing `MediaAsset`s and enqueues jobs, with progress logging (no silent caps).

---

## 7. Search API & UX

### API

```
POST /v1/search
{ query: "k3s cluster diagram",
  modalities: ["image", "audio", "doc"],   # optional filter
  space: "auto",                            # auto → clip for image targets, text otherwise
  k: 20 }
→ { results: [ { asset: {id, kind, url, ...}, score, snippet }, ... ] }
```

Flow:
1. Embed the `query` (text) → query vector in the relevant space (CLIP-text for
   image targets; text model otherwise; may fan out to both and merge).
2. ANN over `MediaEmbedding` **joined to `MediaAsset`, filtered by
   `asset_is_visible_to(viewer)`** — i.e. ownership/visibility is part of the SQL,
   so the index only ever returns permitted assets (owner's media + public).
3. Rank by cosine distance; return assets with a snippet (matched transcript span
   / caption).

`POST /v1/search/similar` `{ asset_id, k }` → nearest neighbors of an existing
asset's vector (same privacy filter).

### UX

- **Search bar in `/dashboard/media`** (PRD 17 Library) — type meaning, get assets.
- **"Find similar"** on any asset drawer.
- **"Ask your media"** (RAG, later phase): retrieve top-k → answer with an LLM,
  citing source assets inline.

---

## 8. Privacy (treated as a first-class requirement)

- Embeddings are **derived data** with the **same audience as their source asset**.
  There is no separate visibility on `MediaEmbedding`.
- Every search query filters by `asset_is_visible_to(viewer)` **inside the SQL**,
  before results leave the database — a user can only ever match their own media
  plus genuinely-public assets. No global/cross-user search.
- Deleting an asset cascades its embeddings; un-publishing an asset immediately
  removes it from other users' search (the filter re-evaluates per query).
- Embedding text (transcripts, captions) is itself private content — it is stored
  on `MediaEmbedding.source_text` and inherits the same gate; the metadata route
  never exposes it to non-owners.
- An **inversion-risk note:** raw vectors can leak information about their source.
  `MediaEmbedding` rows are never served to clients — only ranked *assets* (already
  access-checked) and snippets are returned. Vectors stay server-side.

---

## 9. Phasing

| Phase | Theme | Gate |
|---|---|---|
| **V0** | `pgvector` enabled in Postgres; `MediaEmbedding` model + HNSW index + migration; `EMBED` modality + `embed-*` manifest contract (authorable, no provider yet). | Schema + contract land; manifest validates `embed-text`/`embed-image`; no behavior change. |
| **V1** | `embed-text` service live; embed docs/transcripts (STT-first for audio/video); `POST /v1/search` over the **text** space; search bar in the Library. | Search a transcript by meaning and get the right audio asset, owner-scoped. |
| **V2** | `embed-image` (CLIP) live; image embeddings + **cross-modal text→image** search; "find similar". | Type "3D cluster diagram", get the matching image even with no filename match. |
| **V3** | RAG — "ask your media": retrieve top-k → cited LLM answer. | Ask a question, get an answer citing your own assets. |
| **V4** | Extend embedding to `InferenceRequest` prompts / `ChatThread` messages → global semantic recall across everything you've done. | "Find that chat where I debugged the SOCKS outage" works. |

---

## 10. Open questions

1. **Embedding model choice.** Which text model (dimension vs quality vs serve
   cost on the cluster) and which CLIP/SigLIP variant? Decide when serving them.
2. **Chunking strategy** for long docs/transcripts (fixed window vs semantic) and
   how snippets are surfaced.
3. **Index maintenance.** HNSW build/recall tuning, and the reindex workflow when
   an embedding model is swapped.
4. **Cost ceiling.** Auto-embed-on-upload for everyone vs opt-in per asset / per
   account, given cluster compute is finite.
5. **Scope of V4** — embedding all prompts/messages is powerful but a large index;
   gate behind a setting?
```
