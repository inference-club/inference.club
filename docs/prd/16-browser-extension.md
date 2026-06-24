# PRD 16 — Browser Extension ("Clip")

> **Status:** Drafted (2026-06-24), not yet implemented. A Chrome/Edge/Firefox
> browser extension that turns inference.club into a reading copilot: capture the
> article you're viewing, then **summarize / ask / research / narrate / illustrate**
> it using your own cluster — without copy-pasting into the site.
>
> **Lives in its own repo:** `inference-club/browser-extension` (standalone; the
> only contract with this repo is the public HTTP API). This PRD is filed here so
> it's discoverable alongside the other PRDs; implementation does not touch the
> Django/Nuxt monorepo (V0 needs **zero** server changes — see §9).
>
> **Builds on:** the OpenAI-compatible API (`/v1/*`) + DRF Bearer-token auth that
> already exist (verified §3), PRD 14 Playground Agent (`/v1/agent` for research),
> PRD 12 Narration Studio (`/v1/episodes/from-text` for studio narration), and the
> per-modality runners behind `/v1/{audio/speech,voice,images}/generations`.
>
> **Author:** Brian (product direction) · drafted with Claude Code.

---

## 1. Summary

You read a lot online and constantly copy article text into inference.club to
summarize, question, research, or narrate it. This extension removes the
copy-paste: a toolbar button opens a **side panel** docked next to the page; it
extracts the readable article from the current tab (locally, like Reader Mode),
and gives you actions that call **your** cluster through inference.club's API:

- **Summarize** — TL;DR / bullets / key takeaways (streamed).
- **Ask** — chat against the article ("what does this say about X?").
- **Research** — hand the article + your question to the Playground Agent, which
  can web-search, scrape related links, and synthesize.
- **Narrate** — turn the article (or a summary) into audio: a quick single-voice
  read (`/v1/audio/speech`) or a polished multi-voice **Studio episode**
  (`/v1/episodes/from-text`), played right in the panel.
- **Illustrate** — generate a cover image / diagram for the article.

The headline technical fact: **inference.club's API is already OpenAI-compatible
and authenticates with `Authorization: Bearer <token>`** — the same token your
account already has. So the extension is a thin, well-designed *client*. There is
no new backend for V0; the work is the extension itself.

---

## 2. How browser extensions work (the 5-minute primer)

Since this is your first extension, here's the whole mental model. A Chrome
extension (Manifest V3, the current standard) is a small web app made of a few
cooperating pieces, declared in a **`manifest.json`**:

| Piece | What it is | Runs where | We use it for |
|---|---|---|---|
| **Manifest** | JSON declaring name, permissions, and which files are which piece | — | config |
| **Background service worker** | An event-driven script with no DOM; the extension's "backend." Can `fetch` cross-origin to hosts you list in `host_permissions`. Sleeps when idle. | extension origin | open the side panel on click; (optionally) hold the token & make API calls |
| **Content script** | JS injected *into the web page*, sharing its DOM. Can read the page's HTML/text. Subject to the page's CORS. | the page | extract the article text from the DOM |
| **Popup / Side Panel** | Extension HTML/JS UI (our Vue app). Popup is a small bubble that closes on blur; **Side Panel** is a persistent dock that stays open as you read. | extension origin | the whole UI: actions, streamed output, audio player |
| **`chrome.storage`** | Small persistent key-value store | — | store your API key + settings |
| **Messaging** | `chrome.runtime.sendMessage` / ports — how the pieces talk | — | content script → panel hands over extracted text |

**Two facts that make our life easy:**

1. **CORS doesn't block us.** Browsers normally block a page from calling another
   origin's API. But an extension that declares `host_permissions` for a host
   (e.g. `https://inference.club/*`) is *exempt* — its extension-context fetches
   (service worker, side panel, popup) bypass CORS for that host. So **we make
   API calls from the side panel / service worker, not from a content script**,
   and the server needs no CORS changes for us. (Content-script fetches *would*
   be subject to the page's CORS — so we don't fetch from there.)
2. **The page's content never needs a server round-trip to capture.** A content
   script already lives inside the page and can read its DOM directly. We run
   Mozilla's **Readability.js** (the exact library Firefox Reader Mode uses) on
   that DOM to get clean `{title, byline, text, html}`. This works on pages the
   server *couldn't* reach — logged-in dashboards, paywalled articles you have
   access to, intranet pages — because it runs in *your* browser as *you*.

That's the whole architecture. Everything below is detail.

---

## 3. What already exists (verified in this repo)

| Capability | Endpoint / fact | Source |
|---|---|---|
| **Bearer-token auth** | `BearerTokenAuthentication` (DRF `TokenAuthentication`, keyword `Bearer`) is a default authenticator; every `/v1/*` view is `IsAuthenticated`. | `apps/accounts/authentication.py`, `backend/settings.py` `DEFAULT_AUTHENTICATION_CLASSES` |
| **A per-user token already exists** | One DRF `Token` is auto-created per user (signal + social-auth pipeline) and returned by the profile serializer; there's an endpoint to regenerate/list it. | `apps/accounts/{signals,pipeline,serializers,views}.py` |
| **Chat (summarize/ask)** | `POST /v1/chat/completions` (streaming, OpenAI shape) | `openai_urls.py:60` |
| **Agent (research)** | `POST /v1/agent` (SSE: web_search/scrape/browse + media tools) | PRD 14, `openai_urls.py:70` |
| **Quick narration** | `POST /v1/audio/speech` (returns audio bytes + `X-Asset-Url` header) | `openai_urls.py:74` |
| **Voice / Studio narration** | `POST /v1/voice/generations`, `POST /v1/episodes/from-text` (+ `studio/voices`) | `openai_urls.py:92,105` |
| **Illustrate** | `POST /v1/images/generations` | `openai_urls.py:80` |
| **Scrape fallback** | `POST /v1/scrape` (Firecrawl: URL → markdown) | `openai_urls.py:94` |
| **Model list** | `GET /v1/models` (populate the model picker) | `openai_urls.py:58` |
| **Async jobs** | `/v1/jobs/*` (poll long video/studio renders) | PRD 10, `openai_urls.py:125` |

**Consequence:** V0–V2 add **no endpoints**. The extension authenticates with the
token you already have and calls endpoints that already work.

---

## 4. Stack decision

| Choice | Pick | Why |
|---|---|---|
| Manifest | **MV3** | required by Chrome; the only option going forward |
| Framework | **WXT** (wxt.dev) | the modern extension framework — Vite-based, TS-first, file-based entrypoints, HMR while developing, and **one codebase → Chrome + Edge + Firefox** (handles the manifest differences). Removes ~all of the painful extension boilerplate. |
| UI library | **Vue 3 + `<script setup>`** | matches your Nuxt/Vue muscle memory; WXT has first-class Vue support |
| Language | **TypeScript** | API request/response types, fewer footguns |
| Styling | **Tailwind** | matches the main app; tiny in an extension |
| Article extraction | **`@mozilla/readability`** + DOMPurify | the Reader Mode engine; battle-tested across the messy web |
| Primary surface | **Chrome Side Panel** (`chrome.sidePanel`) | stays open while you read/scroll, room for streamed text + an audio player + chat — a popup would close every time you click the page |

> Alternatives considered: **Plasmo** (similar to WXT, React-leaning — WXT wins on
> Vue + Vite alignment) and a **bookmarklet / userscript** (no install, but can't
> hold a token safely, no side panel, no audio UI — too limited).

---

## 5. Architecture & data flow

```
┌─ web page (any site) ─────────────┐
│  content script:                   │   1. you click the toolbar button
│   Readability(document) → article  │ ─────────────────────────────────┐
└────────────────────────────────────┘                                   │
                 │ chrome messaging (extracted text)                      ▼
┌─ Side Panel (our Vue app, extension origin) ───────────────────────────────┐
│  • shows article title + actions [Summarize] [Ask] [Research] [Narrate] …  │
│  • holds NOTHING secret in the page; token read from chrome.storage         │
│  • fetch() directly to https://inference.club/v1/* with Bearer token        │
│    (host_permissions ⇒ no CORS problem), streams SSE into the panel         │
│  • <audio> plays narration; images render inline; "open in inference.club"  │
└─────────────────────────────────────────────────────────────────────────────┘
                 │ Authorization: Bearer <token>
                 ▼
        inference.club  /v1/{chat/completions, agent, audio/speech,
                              episodes/from-text, images/generations, models}
```

**Capture strategy (important design point).** Two tiers:

1. **Primary — local Readability** on the current tab's DOM. Fast, free, works on
   authed/paywalled pages, nothing leaves the browser until you pick an action.
2. **Fallback — `/v1/scrape`** (Firecrawl) when local extraction is poor (heavy
   SPA, blocked DOM) or when you want to research a *different* URL you're not
   currently viewing. The panel offers "Re-extract with Firecrawl."

**Auth/onboarding.** First run, the panel shows "Connect your account": a field
to paste your API token (with a deep link to where it's shown in
`/dashboard/settings`) and a base-URL field (defaults to `https://inference.club`,
editable so you can point at `localhost:8000` in dev or a self-host). We verify by
calling `GET /v1/models`. Token is stored in `chrome.storage.local` (per-profile,
not synced by default; see §7). No "Login with Discord/GitHub" needed in V0 — the
token *is* the credential.

**Streaming.** `/v1/chat/completions` and `/v1/agent` stream. The side panel reads
the `fetch` `ReadableStream` and appends tokens live (same SSE parsing the web
playground already does — we can port that logic). For research, we render the
agent's `tool_call` / `tool_result` events as collapsible cards, just like PRD 14.

**Audio.** `/v1/audio/speech` returns audio bytes → we make a Blob URL and play it
in an `<audio>` element with a download + "save to inference.club" link (the
`X-Asset-Url` header). Studio narration (`/v1/episodes/from-text`) may be async —
we create it, then poll `/v1/jobs/<id>` and play when ready (with a progress row),
or just deep-link into the Studio page for heavy edits.

---

## 6. Features → endpoint mapping

| Action in panel | Calls | Notes |
|---|---|---|
| **Summarize** (TL;DR / bullets / ELI5 — a preset menu) | `POST /v1/chat/completions` (stream) | system prompt + article as context; preset = different prompt |
| **Ask / chat** | `POST /v1/chat/completions` (stream), article pinned as context | multi-turn; reuse playground SSE parsing |
| **Research** | `POST /v1/agent` (SSE) | article + your question; agent web-searches & scrapes; tool cards |
| **Narrate (quick)** | `POST /v1/audio/speech` | single voice; pick "full text" or "summary first" |
| **Narrate (Studio)** | `POST /v1/episodes/from-text` → poll `/v1/jobs/<id>` | multi-voice episode; deep link to Studio to refine |
| **Illustrate** | `POST /v1/images/generations` | cover image / diagram from title+summary |
| **Selection actions** | any of the above on **selected text** only | content script reads `window.getSelection()` |
| **Model picker** | `GET /v1/models` | remember per-action default in storage |

A small **context-menu** (right-click) mirror — "Summarize selection",
"Narrate selection" — is a cheap, high-utility add (V1).

---

## 7. Permissions & privacy

- **Permissions requested:** `activeTab` + `scripting` (read the current page only
  when you invoke us), `storage` (token + settings), `sidePanel`, `contextMenus`
  (V1). **`host_permissions`:** just your inference.club origin(s) — *not* `<all_urls>`
  for network; activeTab covers page reading on demand. Minimal, reviewable.
- **Data flow promise (state it in the store listing):** page content stays in
  your browser until *you* click an action; then it goes **only** to your
  configured inference.club base URL over HTTPS, authenticated as you. No
  third-party analytics, no other servers. The extension is the same trust
  boundary as typing into the site yourself.
- **Token storage:** `chrome.storage.local` by default (not `sync`, to avoid the
  token traversing Google's sync). Offer a "clear credentials" button. Document
  that anyone with your token can use your quota — same as the API key it is.

---

## 8. Repo layout (`inference-club/browser-extension`)

```
browser-extension/
  wxt.config.ts            # manifest, permissions, targets (chrome/firefox)
  package.json
  entrypoints/
    background.ts          # service worker: open side panel on action click
    content.ts             # Readability extraction + selection capture
    sidepanel/             # the Vue app (App.vue, components, composables)
      App.vue
      components/{ActionBar,StreamView,AgentCards,AudioPlayer,Onboarding}.vue
      composables/{useApi,useArticle,useStream,useSettings}.ts
  lib/
    api.ts                 # typed client for /v1/* (one place for the contract)
    extract.ts             # Readability wrapper + sanitization
    sse.ts                 # SSE/stream parser (ported from the web playground)
  assets/ , icons/
  README.md                # install (dev + store), how to get your token
```

Standard tooling: `pnpm`, ESLint/Prettier, `wxt` dev/build/zip scripts, a GitHub
Action to build + attach a zip on tag (store submission stays manual at first).

---

## 9. Server-side changes (minimal, and none block V0)

- **V0: none.** Extension-context fetches with `host_permissions` bypass CORS, and
  the token + endpoints already exist.
- **Nice-to-haves (small, in the main repo, do later):**
  1. **"Your API key" affordance** in `/dashboard/settings` — a copy button + a
     "set up the browser extension" blurb + deep link. (The token is already in
     the profile serializer; this is UI only.)
  2. If we ever want to call the API from a **content-script context** (we plan
     not to), add the extension origin to `CORS_ALLOWED_ORIGINS` — avoid by
     design.
  3. Optional later: a **scoped/named token** model (revocable, labeled "browser
     extension") instead of the single account token, so revoking the extension
     doesn't nuke other API usage. Worth it once there are multiple clients.

---

## 10. Rollout

| Phase | Headline | Proof of success |
|---|---|---|
| **V0** | Scaffold + capture + **Summarize** | Load unpacked in Chrome; on any article, the side panel shows the extracted title and streams a summary from `/v1/chat/completions` using a pasted token. End-to-end on one real article. |
| **V1** | **Ask + Research + selection + context menu** | Multi-turn chat against the article; "Research this" runs `/v1/agent` with tool cards; right-click "Summarize selection" works; model picker wired to `/v1/models`. |
| **V2** | **Narrate (quick + Studio) + Illustrate + audio player** | `/v1/audio/speech` plays in-panel; "Narrate as Studio episode" creates `/v1/episodes/from-text` and plays when the job completes; illustrate renders an image. |
| **V3** | **Polish + distribution** | Firefox build via WXT; onboarding/settings page; "save to inference.club" links on outputs; Chrome Web Store + AMO listing with the privacy disclosure; the dashboard copy-key affordance (§9). |

> **Out of scope (for now):** offline/local model fallback; auto-summarize-on-load
> (privacy + cost — keep it click-to-act); a full reading-history/library inside
> the extension (deep-link to the site instead); mobile (extensions are desktop).

---

## 11. What I need from you / open questions

1. **Repo name & access:** confirm `inference-club/browser-extension` (or a name
   you prefer), and that I should `git init` it locally for you to push to the org.
2. **Surface:** Side Panel as primary (recommended) — or do you want a classic
   popup too?
3. **Token UX:** paste-token onboarding for V0 (fastest). A one-click
   "authorize the extension" flow (open a site page that hands the token back) is
   nicer but is itself a mini-feature — defer to V3?
4. **Base URL default:** ship pointing at `https://inference.club`, with the field
   editable for `localhost` dev and self-hosters — confirm.
5. **Studio narration sync:** `/v1/episodes/from-text` — is it sync or
   job-based today? Determines whether V2 polls `/v1/jobs` or plays immediately.
   (I'll verify in the code before building V2.)
