# PRD 01 — Content sharing, visibility & curation

> **Status:** Implemented (2026-06-04) — backend + frontend.
> Decisions taken at implementation: existing rows backfilled to **PUBLIC**;
> a 4th **SECRET** ("Only me") level was added; per-share prompt redaction
> (`hide_prompt_on_share`) was **deferred**. Backend covered by
> `apps/inference/tests/test_content_sharing.py` (35 tests).
>
> **Author:** Brian (spec) · drafted with Claude Code.
>
> **Scope:** Give users control over who can see each inference
> request, the ability to share individual requests by link, and
> lightweight curation primitives (stars, bookmarks, collections) on top
> of the existing public-profile surface. **Explicitly out of scope:**
> comments, notifications, follows, feeds, or any social graph. Keep it
> simple.

---

## 1. Summary

Today every inference request is effectively all-or-nothing: it is
private to the owner, *and* it already shows up (consumed/served) on
that user's unauthenticated public profile at `/[username]`. There is no
per-request visibility control, no shareable link, and no way to
favorite, save, or group content.

This PRD introduces:

1. **Per-request visibility** — `PUBLIC` / `UNLISTED` / `PRIVATE`, with a
   per-account default (defaults to **unlisted**).
2. **Edit-visibility modal** — change a request's visibility from the
   detail page and from the card.
3. **Stars** — a like/popularity signal; view "my starred"; sort your
   own content by most-starred. Aggregate counts only (never *who*
   starred).
4. **Bookmarks** — save a request to surface it on your **public
   profile**.
5. **Collections** — group requests into zero, one, or many named
   collections.
6. **Public-profile master switch** + a default-visibility setting on
   the settings page.

---

## 2. Current state (grounded in code)

| Concern | Where | Today |
| --- | --- | --- |
| Request model | `backend/apps/inference/models.py:386` (`InferenceRequest`) | `user` FK, `inference_type`, `status`, `payload`/`results`, metrics. **No visibility field.** |
| Owner attribution | `OwnerAttributionMixin` (serializers) | adds `owner`, `github_login`, `is_owner`. Reuse everywhere. |
| Detail access | `RetrieveInferenceRequestView` (`IsAuthenticated`) | **Any authenticated member can view any request.** Delete is owner-only. |
| Public profile | `PublicUserProfileView` + `PublicUserRequestsView` (`AllowAny`) at `/api/users/<login>/[/requests]` | unauthenticated; lists consumed/served requests. |
| Settings (access) | `frontend/pages/dashboard/settings/access/index.vue` → `ProviderService.access_policy` | controls **node** access (PRIVATE/AUTHENTICATED/RESTRICTED), not request visibility. |
| Detail page | `frontend/pages/dashboard/inference/requests/[id].vue` | full payload/results; delete if `is_owner`. |
| Card | `frontend/components/InferenceRequestCard.vue` | slim card; `showOwner`, `linkable` props. |
| Profile page | `frontend/pages/[username].vue` | Consumed / Served tabs + image strip. |
| User model | `backend/apps/accounts/models.py:9` (`CustomUser`) | `email`, `profile_setup_complete`, `routing_preference`. **No profile/visibility prefs.** |

**Two facts that shape the design:**

- **Existing requests are already public** (visible on the unauthenticated
  profile). Introducing visibility *adds* restriction where none existed —
  so data migration is a real product decision (§11).
- **Request URLs use the sequential integer PK.** "Unlisted" and any
  link-based "private" access cannot rely on an enumerable id — we need an
  unguessable share token (§5.1, §10 / security).

---

## 3. Goals & non-goals

**Goals**
- One clear visibility concept per request, with sane defaults and a
  one-tap editor.
- Shareable links that work for the right audience and nothing more.
- Lightweight curation: star (popularity), bookmark (curate to profile),
  collections (organize).
- Clean, low-friction UX — every affordance reachable from the card and
  the detail page.

**Non-goals**
- Comments, reactions beyond a single star, notifications, following,
  activity feeds.
- Showing *who* starred/bookmarked. Aggregate counts only.
- Team/org sharing or per-user ACLs on a request (the node-level
  `RESTRICTED` allowlist already covers that need elsewhere).

---

## 4. Visibility model

### 4.1 Levels

A new field `visibility` on `InferenceRequest`, mirroring the
`ProviderService.access_policy` choices pattern:

| Level | Anonymous (no login) | Authenticated member | Listed on owner's public profile | Indicator |
| --- | --- | --- | --- | --- |
| `PUBLIC` | ✅ via link & profile | ✅ | ✅ | globe |
| `UNLISTED` | ✅ **via link only** | ✅ via link | ❌ | link / "unlisted" |
| `PRIVATE` | ❌ | ✅ (any member) | ❌ | lock |

The **owner always sees their own** requests regardless of level.

> **Note on `PRIVATE` semantics:** per spec, private = "only
> authenticated users can see it" — i.e. any logged-in inference.club
> member, *not* owner-only. This matches today's behavior where any
> member can already retrieve any request. See §11 open question Q3 about
> whether to also add an owner-only `SECRET`/"Only me" level.

### 4.2 Per-account default

`CustomUser.default_request_visibility` — choices identical to the field
above, **default `UNLISTED`**. Applied at request-creation time when the
client doesn't specify a visibility. Editable on the settings page (§9).

### 4.3 Editing visibility

A small **visibility modal** (Shadcn `Dialog` + `Select`), reachable from:
- the **detail page** header (`[id].vue`), near the owner badge; and
- the **card** (`InferenceRequestCard.vue`) overflow/quick-action, shown
  only when `is_owner`.

The modal shows the three levels with one-line explanations, a copy-link
button, and (for non-private) a "this link is shareable" hint. Saving
PATCHes the request. Non-owners never see the control.

---

## 5. Shareable links & access

### 5.1 Share token (security-critical)

Add `share_token` (random, URL-safe, e.g. 22-char base62 from
`secrets.token_urlsafe`) to `InferenceRequest`, unique, indexed,
generated on create and **rotatable** (rotating invalidates old links).

- Public/unlisted/private link routes resolve by `share_token`, **not**
  by integer PK, so unlisted content can't be enumerated.
- Existing in-app dashboard views may continue to use the PK for the
  owner's own content; anonymous/link access uses the token.

### 5.2 Public access endpoint

New `AllowAny` route, e.g. `GET /api/inference/shared/<share_token>/`:
- `PUBLIC` / `UNLISTED` → returns the detail serializer to anyone.
- `PRIVATE` → 404 to anonymous; full detail to any authenticated member.
- Always 404 (not 403) for tokens that exist but aren't visible to the
  caller, to avoid confirming existence.

Frontend share URL: a public, SSR-friendly route such as
`/s/<share_token>` (renders the detail read-only, with correct OG tags —
see §15). The in-dashboard `/[id]` page links here for "copy link".

### 5.3 Redaction on shared views (recommended)

System prompts and uploaded input audio may contain sensitive content.
Reuse the existing `MediaAsset.PUBLIC_KINDS` gating for media, and add a
per-request `hide_prompt_on_share` boolean (default off) that strips the
input/system prompt from anonymous shared responses. See §11 Q4.

---

## 6. Stars (popularity)

A **star** is a like + the popularity signal.

- **Model:** `Star(user, request, created_on)`, unique-together
  `(user, request)`. (M2M through-model — the inference app currently has
  no M2M, so this establishes the pattern.)
- **Counts only:** expose `star_count` (denormalized on the request for
  cheap sorting) and `is_starred` (for the current user) on serializers.
  Never expose the list of who starred.
- **My starred:** `GET /api/inference/requests/starred/` (auth) — the
  current user's starred requests, respecting each item's visibility.
- **Sort by popular:** the owner's own request list (`index.vue`) gains a
  sort option `-star_count`.
- **Toggle:** `POST/DELETE /api/inference/requests/<id>/star/`. A user can
  star any request they're allowed to view (including their own).
- **UI:** a star button with count on the card and detail page.

---

## 7. Bookmarks (curate to profile)

A **bookmark** saves a request to surface it on the user's **public
profile** — distinct from a star (private favorite/like signal).

- **Model:** `Bookmark(user, request, created_on)`, unique-together.
- **Toggle:** `POST/DELETE /api/inference/requests/<id>/bookmark/`.
- **Public surface:** a **"Bookmarks" tab** on `/[username]` alongside
  Consumed / Served. Critically, only render bookmarked items the viewer
  is allowed to see — i.e. respect each item's own `visibility` (a
  bookmarked `PRIVATE`/`UNLISTED` item owned by someone else is hidden
  from anonymous viewers).
- **My bookmarks (manage):** `GET /api/inference/requests/bookmarked/`
  (auth) for the dashboard list.

> **Star vs bookmark — keep the distinction crisp in copy:** ⭐ *Star* =
> "I like this / count it" (private which, public count). 🔖 *Bookmark* =
> "show this on my profile" (a curation choice). They are independent;
> either, both, or neither can be set.

---

## 8. Collections

Group requests for organization. A request belongs to **zero, one, or
many** collections (uncategorized = in none).

- **Model:** `Collection(user, name, slug, description, visibility,
  created_on, modified_on)` + through `CollectionItem(collection,
  request, position?)`, unique-together `(collection, request)`.
- **Visibility:** collections get the same `PUBLIC/UNLISTED/PRIVATE`
  field. A public collection appears on the profile; items inside still
  respect their own visibility when an anonymous viewer opens them.
- **CRUD:** `GET/POST /api/inference/collections/`,
  `GET/PATCH/DELETE /api/inference/collections/<slug>/`,
  add/remove item `POST/DELETE
  /api/inference/collections/<slug>/items/<request_id>/`.
- **UI:**
  - Dashboard: a Collections page (list + create), a collection detail
    page (cards within), and an "Add to collection" control in the card
    overflow + detail page (multi-select of the user's collections).
  - Public: a **Collections tab** on `/[username]` listing public
    collections; collection detail reachable by slug.
- **Cover:** optional `cover_request` FK or auto-pick the first image
  asset for a thumbnail (nice-to-have).

---

## 9. Settings

Extend the existing settings area (sibling to
`dashboard/settings/access/`):

- **Default request visibility** — `Select` (Public / Unlisted /
  Private), writes `CustomUser.default_request_visibility`. Copy: "New
  inference requests use this visibility unless you change them."
- **Public profile** — master on/off `Switch`
  (`CustomUser.public_profile_enabled`, default **on**). When **off**,
  `/[username]` and the public profile/requests endpoints return 404
  (or a "this profile is private" stub) regardless of individual item
  visibility. Place under "General".

New/changed user settings endpoint: extend the existing account/me
serializer to read/write `default_request_visibility` and
`public_profile_enabled`.

---

## 10. Data model changes (concrete)

`InferenceRequest` (new fields):
```python
visibility = CharField(max_length=12, choices=VISIBILITY_CHOICES,
                       default="UNLISTED", db_index=True)
share_token = CharField(max_length=32, unique=True, db_index=True)  # token_urlsafe
hide_prompt_on_share = BooleanField(default=False)
star_count = PositiveIntegerField(default=0, db_index=True)  # denormalized
# (bookmark_count optional if a "most bookmarked" sort is ever wanted)
```

New models (inference app):
```python
class Star(BaseModel):       user, request (unique_together)
class Bookmark(BaseModel):   user, request (unique_together)
class Collection(BaseModel): user, name, slug, description, visibility, cover_request?
class CollectionItem(BaseModel): collection, request, position (unique_together collection+request)
```

`CustomUser` (new fields):
```python
default_request_visibility = CharField(default="UNLISTED", choices=VISIBILITY_CHOICES)
public_profile_enabled = BooleanField(default=True)
```

- Define `VISIBILITY_CHOICES` once (shared constant) so request,
  collection, and the account default all agree.
- Migrations land in `backend/apps/inference/migrations/` (currently at
  `0014_…`) and `backend/apps/accounts/migrations/`.
- Keep `star_count` correct via signals on `Star` create/delete (or
  `F()` increment) to avoid count drift; reconcile in a management
  command if needed.

---

## 11. Open questions / decisions

1. **Existing-data backfill (Q1).** Today's requests are already publicly
   visible on profiles. On migration, set existing rows to **`PUBLIC`**
   (preserve current behavior) or **`UNLISTED`** (privacy-by-default,
   silently de-lists existing content)? *Recommendation: `PUBLIC` to
   avoid surprising behavior change, and announce the new default for
   future requests.*
2. **Default default (Q2).** Spec says new-account default = **unlisted**
   — confirmed. Keep.
3. **Owner-only level (Q3).** Add a 4th `SECRET` ("Only me") level, or is
   member-visible `PRIVATE` enough? Spec lists only three; flagging
   because "private that all members can read" surprises some users.
4. **Prompt redaction (Q4).** Ship `hide_prompt_on_share` in v1 or defer?
   Relevant because shared payloads can leak system prompts.
5. **Star == bookmark?** They overlap conceptually. Confirm both are
   wanted (spec asks for both). Kept distinct here: star=like/stat,
   bookmark=profile curation.
6. **Collection visibility** — inherit a simple Public/Private only, or
   full three-level? Proposed: full three-level for consistency.

---

## 12. Phasing (suggested implementation order)

- **Phase 1 — Visibility core:** `visibility` + `share_token` fields,
  account default, default-visibility setting, public-profile master
  switch, `/s/<token>` read-only page + shared endpoint, visibility modal
  on detail & card, profile listing respects visibility. *This alone
  delivers the headline feature.*
- **Phase 2 — Stars:** model, toggle, counts, "my starred", sort-by-popular.
- **Phase 3 — Bookmarks:** model, toggle, Bookmarks tab on profile.
- **Phase 4 — Collections:** models, CRUD, add-to-collection, dashboard +
  public collection surfaces.

Each phase is independently shippable and independently valuable.

---

## 13. Acceptance criteria (high level)

- A new request defaults to the account's default visibility (unlisted
  out of the box).
- Owner can change a request's visibility from both card and detail in
  ≤2 taps; non-owners never see the control.
- An unlisted link works for anyone with the link but the request never
  appears on the profile and is not enumerable by id.
- A private request 404s for anonymous and renders for any logged-in
  member.
- Turning the public profile off makes `/[username]` inaccessible to
  anonymous visitors regardless of item visibility.
- Star/bookmark toggles are idempotent; counts are aggregate-only; "who
  starred" is never exposed by any endpoint.
- Bookmarked items shown on a profile respect the item's own visibility.

---

## 14. UX notes

- Visibility indicator (globe / link / lock) appears on the card and
  detail header for the owner; show the **unlisted** icon prominently per
  spec.
- Star and bookmark are visually distinct (filled star vs filled
  bookmark) with counts next to the star only.
- "Copy link" lives in the visibility modal and the share/overflow menu;
  show a toast on copy.
- Empty states: "No starred requests yet", "No collections yet — create
  one to organize your work."

---

## 15. Additional ideas worth folding in (my suggestions)

These are small, on-theme additions that make sharing actually land:

1. **Social/OG preview cards.** The single highest-leverage add for
   sharing: server-render OpenGraph/Twitter meta on `/s/<token>` and
   `/[username]` so shared links unfurl with a title, model name, and
   (for image gen) the generated image as the preview. Without this,
   shared links look broken in chat apps.
2. **Unguessable share tokens (already in §5.1)** — calling it out again
   because it's a correctness/security requirement, not a nice-to-have:
   unlisted must not be enumerable via the integer PK.
3. **Per-share redaction (§5.3)** — a "hide prompt on public view" toggle
   prevents leaking system prompts/PII in publicly shared requests.
4. **Featured / pinned request** on the public profile — let a user pin
   one request (e.g. their best image) to the top of their profile. Cheap
   given bookmarks already exist (a `is_featured` flag or single pin).
5. **"Most popular" on the public profile**, not just the dashboard — a
   sort toggle so visitors can see a user's best work, powered by the
   same denormalized `star_count`.
6. **Copy-as / export from a shared view** — download the generated
   image/audio or copy the response; makes shares useful to recipients.
7. **Collection cover + share** — collections become great shareable
   "galleries" (e.g. "My favorite landscapes"); auto-thumbnail from the
   first image asset.
8. **Embeds (later)** — an `/embed/<token>` iframe + oEmbed endpoint so a
   shared request can be dropped into a blog. Out of scope for v1, but the
   `share_token` design makes it free later.
9. **Lightweight abuse guard** — since `PUBLIC` exposes content to
   anonymous users, a minimal "report" mailto/flag and an admin
   force-private switch. Keep it boring; no moderation queue.
10. **Profile-off / item-visibility precedence rule** — document and test
    that the profile master switch overrides item visibility (off = no
    public surface at all), to avoid a confusing partial-exposure state.

---

## 16. Touch list (for implementation)

**Backend**
- `apps/inference/models.py` — new fields + `Star`, `Bookmark`,
  `Collection`, `CollectionItem`; `VISIBILITY_CHOICES` constant.
- `apps/inference/serializers*` — add `visibility`, `share_token`,
  `star_count`, `is_starred`, `is_bookmarked`; collection serializers.
- `apps/inference/views.py` + `urls.py` — shared-by-token endpoint,
  star/bookmark toggles, starred/bookmarked lists, collection CRUD; make
  `PublicUserRequestsView` filter by visibility and honor the profile
  switch.
- `apps/accounts/models.py` + account serializer/view — default
  visibility + `public_profile_enabled`.
- Migrations in both apps.

**Frontend (Nuxt)**
- `components/InferenceRequestCard.vue` — visibility badge, star/bookmark
  buttons, overflow actions (edit visibility, add to collection).
- `pages/dashboard/inference/requests/[id].vue` — visibility modal, share
  button, star/bookmark.
- `pages/dashboard/inference/requests/index.vue` — sort-by-popular.
- New `pages/s/[token].vue` (public read-only share view, with OG tags).
- New dashboard pages: starred list, collections list + detail.
- `pages/[username].vue` — Bookmarks + Collections tabs; respect
  visibility + profile switch.
- New `pages/dashboard/settings/` general section — default visibility +
  public-profile switch (mirror the existing `settings/access/` page).
- Pinia store + composables for stars/bookmarks/collections/visibility.
