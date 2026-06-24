# PRD 15 — Discord Integration

> **Status:** Drafted (2026-06-24), not yet implemented. A Discord presence for
> inference.club: a community server that doubles as a front door, plus a bot
> that lets people **generate and share media without leaving Discord** by
> calling the existing `/v1/*` runners and the Playground Agent (PRD 14).
>
> **Server:** `inference.club` · invite `https://discord.gg/4fVcmJq4X` ·
> Discord login is **not** added (we link accounts with a one-time code instead,
> §4.5 — revisit "Login with Discord" only if onboarding friction demands it).
>
> **Builds on:** PRD 14 Playground Agent (`/v1/agent` SSE loop, tool registry,
> the modality runners it reuses), PRD 10 async jobs (`InferenceRequest` +
> Celery, for slow video/music/voice followups), PRD 08 anonymous access (the
> bot's unlinked requests run as a shared **guest** user; `IsFullMember` gates
> compute), PRD 01 content sharing (opaque `public_id` share links + public
> media on GCS), and PRD 07 cluster visualization (`/cluster/state` for
> `/status`).
>
> **Author:** Brian (product direction) · drafted with Claude Code.

---

## 1. Summary

inference.club produces shareable media (images, video, music, voice) on public
GCS URLs — and Discord renders all of those **natively**: images and `.mp4`
inline, audio as playable cards, links as Open-Graph preview cards. That makes a
Discord server an unusually good fit for the product: it is simultaneously the
place generated content gets *shown off*, the support/community channel, and
plausibly the **first entrypoint** many people have to the site.

This PRD covers three layers, shippable independently:

1. **Community + link unfurling** — channel structure, an onboarding/welcome
   flow, and correct Open-Graph tags on public share pages so that *any* pasted
   `inference.club` link becomes a rich card. Near-zero backend code, highest
   ratio of impact to effort.
2. **A bot** — slash commands (`/image`, `/music`, `/video`, `/voice`, `/ask`)
   that call our existing generation + agent APIs and post results inline, plus
   read-only `/status` and an auto-poster that drips new *public* generations
   into `#showcase` so the server populates itself.
3. **Account linking** — a `/link` one-time-code flow mapping a Discord user to
   a `CustomUser`, so bot requests attribute to the real user (ownership,
   gallery, collections, quota) — the lightweight alternative to OAuth.

The genuinely new infrastructure is **one bot service** and **a handful of
Django endpoints** it calls; the model routing, generation runners, async jobs,
media handling, and share links already exist.

---

## 2. What does NOT change (load-bearing promises)

- **The web app is untouched.** The bot is a *client* of the same public-ish
  HTTP surface the frontend uses; no generation logic is duplicated. Turning the
  bot off loses Discord features and nothing else.
- **Bot requests run as a real account, never escalated.** Unlinked usage runs
  as a single shared **Discord guest** user (PRD 08), with that account's
  routing, rate limits, and visibility. Linked usage runs as the linked
  `CustomUser`. A Discord command can never do more than that user could do in
  the app.
- **Media stays pointers, not blobs.** The bot posts GCS URLs (or uploads the
  file it fetched from one); it never becomes a media store. Outputs are normal
  `MediaAsset` / `InferenceRequest` rows owned by the acting user.
- **Generation reuses the existing runners.** `/image` → the image runner,
  `/ask` → `/v1/agent` — identical paths to the playground and async jobs. No
  Discord-only generation code.
- **No new auth provider.** We do *not* add "Login with Discord." Identity is
  linked via a one-time code (§4.5); the website's GitHub/guest auth is
  unchanged.

---

## 3. Building blocks (what we already have)

| Capability | Where | Use here |
|---|---|---|
| **Image/video/music/voice generation** | `/v1/{images,videos,music,voice}/generations` + per-modality runners (`_RETRY_RUNNERS`, PRD 10) | the bot's `/image` etc. call these as the acting user |
| **Agent loop** | `POST /v1/agent` SSE (PRD 14) | `/ask` — search + multi-modal tool use from a single command |
| **Async jobs** | `InferenceRequest` + Celery (PRD 10) | slow video/music/voice → ack now, post result on completion |
| **Public media + share links** | GCS public URLs + opaque `public_id` (PRD 01/13) | inline rendering & unfurled cards in Discord |
| **Anonymous access** | guest users + passcodes, `IsFullMember` gating (PRD 08) | the shared "Discord guest" identity for unlinked use |
| **Cluster state** | `/cluster/state`, activity/history endpoints (PRD 07) | `/status` command, `#cluster-status` posts |
| **Public content feed** | logged-out showcase feed (project_logged_out_experience) | the `#showcase` auto-poster source |

**Consequence:** layers 1–2 mostly *wire existing endpoints to Discord*. The new
code is the bot process, a thin set of bot-facing endpoints (with a service
token), and the Open-Graph tags.

---

## 4. Design

### 4.1 Discord's two interaction models (the architecture fork)

Discord exposes bot behavior two ways, and we will likely want **both**:

- **HTTP Interactions** — Discord POSTs slash-command invocations to a public
  HTTPS endpoint (Ed25519-signed). *No persistent connection.* Fits our Django
  deploy cleanly (a signed webhook view), survives restarts, scales with the
  web tier. **Limitation:** request/response only — no gateway events, so no
  "watch the channel and auto-post," no reactions, no presence.
- **Gateway (websocket) bot** — a persistent process logged into Discord. Needed
  for the **auto-poster**, reactions, and any proactive messaging. This is a
  small always-on service.

**Decision:** start with **HTTP Interactions in Django** for all slash commands
(no new always-on service for the headline use case), and add a **tiny gateway
worker** only when we want the auto-poster / proactive posts (layer 2b). The
gateway worker, when it exists, also just calls our internal endpoints — it
holds no business logic.

### 4.2 The 3-second / 15-minute rule → sync vs async

Every slash command must be **acknowledged within 3 seconds**, after which we
have a **15-minute** window to edit/follow-up the message. This maps directly
onto our sync/async split:

- **Sync (fast: image, text/`/ask`, voice line):** `defer` immediately → call
  the runner / `/v1/agent` synchronously → **edit** the deferred message with the
  result (image attachment or URL card), all inside 15 minutes.
- **Async (slow: video, full music track):** `defer` → create an
  `InferenceRequest` (Celery) → **store the Discord followup token + channel** on
  the job → on completion, a callback posts the result via the Discord webhook
  followup. This reuses PRD 10's job lifecycle; the only new field is the Discord
  delivery target.

> Discord's followup webhook is valid for 15 minutes; for jobs that may exceed
> that we fall back to a fresh **channel message** (bot must be in the channel)
> rather than an interaction followup. The job stores enough to do either.

### 4.3 Media in Discord (what renders)

| Modality | Delivery | Renders as |
|---|---|---|
| Image | upload attachment **or** GCS URL | inline image |
| Video | GCS `.mp4` URL (preferred) or upload if under size limit | inline player |
| Music / voice | audio URL or upload | playable audio card |
| Text / agent answer | message content (+ embeds for tool cards) | formatted text |
| Share link | the `public_id` URL | Open-Graph preview card (§4.6) |

Uploading vs. linking: prefer **upload** for images and short audio (instant,
no dependence on OG scraping), prefer **link** for video (size limits) and
whenever we want the click-through to the site. The bot fetches the GCS object
and re-uploads when attaching.

### 4.4 Slash commands (layer 2a)

| Command | Path | Sync? | Notes |
|---|---|---|---|
| `/image <prompt>` | image runner | sync | the proof command — fast, reliable, fully sync |
| `/ask <prompt>` | `POST /v1/agent` | sync | search + tools + media via the agent; stream collapsed to one edited message |
| `/voice <text> [voice]` | voice runner | sync | short lines render as audio cards |
| `/music <prompt>` | music runner | **async** | ack → job → followup |
| `/video <prompt>` | video runner | **async** | ack → job → followup |
| `/status` | `/cluster/state` | sync | embed: online services, GPUs, current load |
| `/link` | §4.5 | sync | issues a one-time code to connect a site account |
| `/me` | account summary | sync | usage/quota for a linked user (ephemeral reply) |

Each command resolves the acting user (linked `CustomUser` or the shared guest),
enforces that user's gates (`IsFullMember`, rate limits), and posts the result.
Errors come back as an ephemeral message the invoker sees.

### 4.5 Account linking (`/link`, layer 3)

No OAuth. Two directions, pick one to ship (recommend code-from-site):

1. **Code from site:** user clicks "Connect Discord" in
   `/dashboard/settings` → we mint a short-lived code → they run `/link <code>`
   in Discord → bot calls an internal endpoint that binds `discord_user_id` ↔
   `CustomUser`.
2. **Code from Discord:** `/link` (no args) replies with a code to paste into
   settings.

A new `DiscordIdentity` model (`discord_user_id` unique, FK `CustomUser`,
linked_at). Once linked, all of that Discord user's commands attribute to the
real account — outputs land in their gallery/collections and respect their
quota. Unlinking is a settings toggle; unlinked users transparently fall back to
the shared guest identity.

### 4.6 Open-Graph unfurling (layer 1 — do first)

Audit and fix `og:*` / `twitter:card` tags on the **public share pages** (the
`public_id` routes) so a pasted link renders a card with title, description, and
the media preview:

- images → `og:image`
- video → `og:video` (+ `og:image` poster) and `twitter:player` where possible
- music/voice → `og:image` (cover art) + `og:audio`

This is the cheapest, highest-leverage win: every link anyone shares in any
Discord (or Slack, iMessage, X…) becomes a preview. Verify with Discord's
embed behavior + the standard OG validators.

### 4.7 Bot-facing API surface

The bot authenticates to Django with a **service token** and passes the acting
Discord user id; Django resolves identity server-side (never trusts the bot to
assert a `CustomUser`). Options: reuse the existing `/v1/*` endpoints with a
service-token + on-behalf-of header, or add thin `/api/discord/*` wrappers that
adapt request/response to Discord shapes. Recommend thin wrappers so Discord
quirks (defer tokens, attachment fetching) live in one place.

---

## 5. API surface (incremental)

| Endpoint | Phase | Purpose |
|---|---|---|
| public share pages emit `og:*` | V0 | rich unfurling (no new endpoint, template work) |
| `POST /api/discord/interactions` | V1 | signed Discord HTTP-interactions webhook (all slash commands) |
| `POST /api/discord/link` | V1 | bind `discord_user_id` ↔ `CustomUser` via one-time code |
| `GET /api/discord/status` | V1 | cluster-state summary shaped for an embed (or reuse `/cluster/state`) |
| job → Discord followup delivery | V2 | async job completion posts to the stored Discord target |
| gateway worker | V2 | persistent bot for `#showcase` auto-posting / proactive messages |

---

## 6. Rollout

| Phase | Headline | Gate / proof of success |
|---|---|---|
| **V0** | Community + unfurling | Channel structure (`#welcome` / `#showcase` / `#support` / `#cluster-status` / `#ideas`) + pinned onboarding; pasted `inference.club` share links render as rich cards in Discord across all modalities. No bot yet. |
| **V1** | Bot: `/image`, `/ask`, `/voice`, `/status`, `/link` | Signed HTTP-interactions endpoint live; `/image cat in a spaceship` posts an inline image within seconds, owned by the shared guest (or linked user); `/link` connects a site account. Well tested (signature verification, identity resolution, error paths). |
| **V2** | Async media + auto-poster | `/music` and `/video` ack instantly and follow up when the Celery job lands; a small gateway worker drips new public generations into `#showcase`. |
| **V3 (optional)** | Polish & reach | reactions to save a generation to a collection (linked users); per-channel default models; richer `/me`; consider "Login with Discord" only if onboarding friction warrants. |

> **Explicitly out of scope (for now):** Discord as an auth provider; voice-channel
> live audio; bot-initiated DMs; cross-posting to other platforms.

---

## 7. Infra & ops

- **Where it runs:** V1 slash commands are a **Django view** (no new always-on
  service) — Discord POSTs signed interactions to the public domain via Caddy.
  V2's auto-poster is a **small gateway worker** added to the Hetzner compose
  stack (a long-lived process holding the websocket; restart-safe, holds no
  business logic).
- **Secrets:** Discord application public key (for Ed25519 verification), bot
  token, application id, and an internal service token for bot↔Django, via env
  (compose secrets / GitHub Actions), same pattern as existing keys.
- **Identity & gating:** the bot never asserts a `CustomUser`; Django maps
  `discord_user_id` → linked account or the shared guest, then applies that
  user's `IsFullMember` gates and rate limits. Metering is automatic: every
  command that generates is a normal `InferenceRequest`, so existing dashboards
  cover Discord usage.
- **Cluster reachability:** unchanged — the bot calls Django, Django reaches the
  cluster over the tailnet exactly as today.
- **Abuse:** the shared guest identity is the blast radius for unlinked use;
  rate-limit by Discord user id at the bot layer in addition to the account's
  own limits, and keep guest compute conservative (PRD 08 defaults).

---

## 8. Open questions

1. **HTTP-interactions vs. gateway scope:** confirm V1 needs *only* interactions
   (no reactions/auto-post). If reactions-to-save is wanted early, the gateway
   worker moves up to V1.
2. **Upload vs. link per modality:** measure Discord size limits vs. our typical
   asset sizes to finalize the upload/link policy in §4.3 (esp. video).
3. **Unlinked attribution:** one shared guest for the whole server, or one guest
   per Discord user (better metering/limits, more accounts). Lean shared for V1,
   revisit if abuse or attribution needs grow.
4. **Followup beyond 15 min:** confirm the channel-message fallback for jobs that
   exceed the interaction-followup window (bot membership in the channel).
5. **Link direction:** code-from-site vs. code-from-Discord for `/link` — pick
   one for V1 (recommend code-from-site, keeps the secret on our origin).
6. **Login with Discord:** keep deferred unless onboarding data shows the
   one-time-code link is too much friction.
