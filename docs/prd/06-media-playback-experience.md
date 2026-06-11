# PRD 06 — Media Playback Experience (Music & Video)

**Status:** implemented (2026-06-11) — all five phases. Notable deltas from the
draft: the image-generations endpoint now returns `request_id` (mirroring
mesh/video) so the cover dialog can link covers without a follow-up query;
reorder is move-up/down buttons + native HTML drag (no DnD dependency).
**Guideline:** Spotify-style for music, YouTube-style for video — used as a north star, kept
simple. Collections remain the single, flexible abstraction for organizing content; playlists
are just a playback view over an **ordered** collection.

## Problem

1. **Music is a list of cards.** Songs play one at a time inside `InferenceRequestCard` with
   native `<audio>` controls. No continuous playback, no queue, no "play all", nothing
   persists across navigation. Generating a 3-minute song and listening to it shouldn't
   require staying on one page.
2. **Video is the same.** Each video plays inline in its card. No watch page, no up-next, no
   autoplay-through-a-playlist.
3. **Collections are unordered in practice.** `CollectionItem.position` exists
   (`backend/apps/inference/models.py:678-737`) but every add writes `position=0`, there is
   no reorder API, and the UI has no ordering affordance. A playlist without order isn't a
   playlist.
4. **No visual identity for audio.** Songs and playlists have no artwork; music pages are
   walls of text. We have a production image-generation pipeline sitting right there.

## Decisions (proposed defaults)

- **Collections stay generic.** No `kind` field. A collection's playback affordances are
  derived from its contents: contains MUSIC → "Play" as a music playlist; contains VIDEO →
  "Play" as a video playlist; mixed → both, filtered per mode. The list/manage view is
  unchanged for all collections.
- **Ordering is server-side truth; shuffle is client-side.** Position is persisted; shuffle
  and repeat are player-state only.
- **Cover art reuses the existing pipeline.** The frontend calls `/v1/images/generations`
  (square size) and then links the resulting request as the cover — no new server-side
  generation orchestration. One new FK (`InferenceRequest.cover_request`) for songs;
  `Collection.cover_request` already exists.
- **One global audio player, native video.** Music gets a persistent bottom-bar player backed
  by a single shared `HTMLAudioElement` (Pinia store). Video keeps the native `<video>`
  element inside a YouTube-style watch page; no global video state.

## Approach — five phases, each independently shippable

### Phase 1 — Ordered collections (backend + UI foundation)

Backend (`apps/inference`):
- **Append at end:** `CollectionItemView.post` sets `position = max(position) + 1` instead of
  the default 0. Data migration backfills existing items' positions from `created_on` per
  collection.
- **Reorder endpoint:** `PUT /api/inference/collections/<slug>/items/order/` with body
  `{"request_ids": [...]}` (full ordering, owner-only). Server rewrites positions 0..n-1 in a
  transaction; ids missing from the body keep relative order after the listed ones. Single
  bulk endpoint — no per-item move API.
- Serializer additions on `Collection`: `audio_count`, `video_count`,
  `total_audio_seconds` (annotation over items' requests) so the UI can decide which playback
  affordances to show without fetching items.

Frontend:
- Drag-and-drop reordering on `pages/dashboard/inference/collections/[slug].vue` (owner only)
  with optimistic update + persisted order via the new endpoint. Keyboard/touch-friendly
  move-up/move-down buttons as the fallback affordance (no heavyweight DnD dependency unless
  needed — evaluate native HTML drag events first).
- `useContentSharing.ts`: add `reorderCollection(slug, requestIds)`.

### Phase 2 — Global music player (the Spotify bar)

- **`stores/player.ts` (Pinia):** queue of track objects (derived from `InferenceRequest`
  MUSIC items: id, title from prompt, audio URL, duration, cover URL, owner), `currentIndex`,
  `isPlaying`, `shuffle`, `repeat` (`off | all | one`), volume. Owns one shared
  `HTMLAudioElement`; `ended` advances the queue (respecting shuffle order, which is a
  shuffled index array so un-shuffling restores position).
- **`components/GlobalPlayerBar.vue`** mounted in `layouts/app.vue`, fixed bottom, hidden when
  queue is empty: cover thumbnail, title, prev / play-pause / next, seek bar with elapsed/
  total, shuffle + repeat toggles, volume, queue popover (current queue, click-to-jump,
  remove). Reuses `MusicVisualizer` (it already supports an external element via the shared
  AudioContext in `utils/audio.ts`) as a compact inline visualizer.
- **Media Session API:** title/artwork/next/prev so OS media keys and lock screens work.
- **Play entry points:** play button on MUSIC `InferenceRequestCard`s ("play now" replaces
  queue; ⋯ menu gets "Add to queue"), and on collection detail: **Play** (queue = ordered
  audio items) and **Shuffle** (same queue, shuffle on).
- Card-level `<audio>` elements are removed for MUSIC in favor of routing through the global
  player (STT/TTS cards keep native players — they're utterances, not tracks).
- Works on public pages too (`/[username]/collections/[slug]`, `/s/[token]`): the bar mounts
  in whatever layout hosts those pages.

### Phase 3 — Music home (the Spotify-ish surface)

- **`pages/dashboard/music/index.vue`:** "Your songs" (MUSIC requests, play-all/shuffle-all),
  "Your playlists" (collections where `audio_count > 0`, square cover grid), recently played
  (client-side localStorage list — no backend history table yet).
- **Playlist view:** collection detail gains a music mode — large square cover + name +
  owner + total duration header, Play/Shuffle buttons, compact track-row list (index, title,
  duration, ⋯ menu) instead of full request cards. Toggle between "Playlist" and "Manage"
  (existing card list with remove/reorder).
- Navigation: "Music" entry in `AppSidebar`.

### Phase 4 — Video watch experience (the YouTube-ish surface)

- **`pages/dashboard/watch/[id].vue`:** large native `<video>` player (autoplay on navigate),
  title/prompt, owner, stars/bookmark/share via existing `RequestActionBar`, generation
  params in a collapsible detail row.
- **Playlist mode via query params**, YouTube-style: `/dashboard/watch/<id>?list=<slug>` shows
  an up-next panel (the collection's ordered video items) on the right (below on mobile),
  with autoplay-next on `ended`, shuffle toggle, and current-item highlight. Prev/next
  navigate within the list.
- Collection detail with `video_count > 0` gets a **Play** button → watch page at the first
  video with `?list=`. VIDEO cards get a play overlay linking to their watch page.
- Public variant for shared/public collections (`/[username]/...` → public watch route or the
  same page with public data fetch), respecting per-item visibility exactly as
  `_collection_with_items` already does.

### Phase 5 — Cover art generation

Backend:
- `InferenceRequest.cover_request` FK (nullable, SET_NULL, same shape as
  `Collection.cover_request`) + expose `cover_image_url` on request serializers.
- Writable `cover_request_id` on collection PATCH and on a small request-update endpoint
  (validate: owner of both, cover request is an IMAGE type with an OUTPUT_IMAGE asset).

Frontend:
- **`components/GenerateCoverDialog.vue`**, launched from a song's ⋯ menu or a collection's
  edit menu: pre-filled prompt derived from the song prompt/lyrics or collection
  name/description ("square album cover art, …"), optional one-click "Improve with AI"
  (LLM rewrite, same pattern as `useMusicAssist`), model picker (image models), generates
  1024×1024 via existing `useImageGeneration`, shows result, **Set as cover** links it.
  Re-roll keeps previous results visible (they're normal IMAGE requests — nothing is lost).
- Covers render everywhere: player bar, queue, track rows, playlist headers, music home
  grid, Media Session artwork. Fallback: existing gradient/icon treatment.

## Out of scope (deliberately)

- Server-side play-history/scrobbling, play counts, recommendations.
- Cross-fade/gapless playback, audio normalization.
- A `kind`/type field on collections (revisit only if derived affordances prove confusing).
- Background video playback / picture-in-picture management (browser default PiP is enough).
- Collaborative playlists (collections are single-owner today; unchanged).

## Cross-cutting

- **i18n:** all new strings in all 7 locales from the start (PRD 02 discipline).
- **Design/e2e (PRD 05):** new routes (`/dashboard/music`, `/dashboard/watch/[id]`) go into
  `e2e/routes.ts`; player bar, track rows, and playlist header get `/design` gallery entries
  including worst-case long-title fixtures; `seed_design_data` gains an ordered collection
  with music + video items and a cover.
- **Perf:** queue building uses URLs already present in list serializers — no extra fetches;
  audio remains lazy (nothing loads until the user presses play); watch page is the only
  place a video autoplays.

## Sequencing & dependencies

Phase 1 is the foundation (2 and 4 consume ordering; can start immediately). Phase 2 and
Phase 4 are independent of each other. Phase 3 builds on 2. Phase 5 is independent after its
small backend FK lands, but lands best after 3 (covers have places to appear). Suggested
order: 1 → 2 → 3 → 4 → 5, with 4 promotable earlier if video demos matter sooner.
