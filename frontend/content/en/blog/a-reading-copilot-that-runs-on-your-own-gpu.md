---
title: "A reading copilot that runs on your own GPU"
description: "The inference.club web app is great until you're reading an article somewhere else and want it summarized — then you're back to copy-paste. So we built a browser extension: a side panel that summarizes and answers questions about whatever you're reading, extracted locally with the Firefox Reader Mode engine and sent only to your own cluster. No third-party AI reading what you read."
publishedAt: "2026-06-24"
author: briancaffey
tags: [browser-extension, privacy, llm-inference, announcements]
image: /images/blog/a-reading-copilot-that-runs-on-your-own-gpu.png
image_prompt: "Wide cinematic abstract illustration: an open book or document on the left dissolving into clean streams of cyan and violet light that flow rightward into a small glowing house containing a GPU, a translucent side panel of light floating beside the page, sense of reading and comprehension flowing home rather than to the cloud, dark moody futuristic, soft glow, no text, no words, no letters"
---

The most common thing I do on inference.club is also the most embarrassing. I'm reading something — a long postmortem, a dense arXiv abstract, release notes for a tool I half understand — and I want it summarized or want to ask a question about it. So I select the text, copy it, switch tabs to inference.club, paste it into the playground, and type my prompt. Then I switch back. Then I do it again for the next paragraph that confused me.

The infrastructure to answer the question is sitting right there on my own hardware. The models are served, the API is up, the tunnel is warm. The only friction is *me*, ferrying text between two tabs with my clipboard.

So we built the thing that removes the clipboard. It's a browser extension — a side panel that docks next to whatever you're reading and lets you summarize it or ask about it in place, streamed live from *your* cluster through the inference.club API. It's open source: [`inference-club/browser-extension`](https://github.com/inference-club/browser-extension).

## The five-second version

```
┌─ the page you're reading (any site) ──────────┐
│  content script:                              │   you click the toolbar icon
│   Readability(document) → {title, text}       │ ──────────────────────────┐
│   (runs in YOUR browser, only on a click)     │                           │
└────────────────────────────────────────────────┘                          │
                 │ chrome messaging (extracted article)                      ▼
┌─ side panel (a small Vue app, extension origin) ───────────────────────────┐
│  • shows the article title + [Summarize ▾] [Ask]                           │
│  • token read from chrome.storage.local — never touches the page           │
│  • fetch() → https://api.inference.club/v1/chat/completions  (Bearer token)│
│  • streams the SSE response straight into the panel                        │
└─────────────────────────────────────────────────────────────────────────────┘
                 │ Authorization: Bearer ic-…
                 ▼
       your inference.club cluster — your 4090s, your Spark, your models
```

There is no inference.club server in the middle that's new. The extension is a *thin client* of the same OpenAI-compatible API the playground already uses. The article never leaves your browser until you click an action, and when it does, it goes to exactly one place: the base URL you configured, authenticated as you. Nobody else's AI reads what you read.

That last sentence is the whole point of the thing, so let me dwell on it.

## Why this had to be local-first

There is no shortage of "summarize this page" extensions. They are mostly funnels into somebody's cloud model. You install a browser add-on, and now every article you summarize — every paywalled investigation, every internal wiki page, every draft you're reviewing — flows through a third party's inference stack, gets logged, maybe gets trained on. The convenience is real and the trade is quietly enormous: you hand your reading list to a company whose business is knowing things.

inference.club exists because a lot of us already own capable hardware and would rather run our own models than rent someone's. The web app proves the models work. But reading happens *out there* — on Hacker News, on a journal site, on a half-broken corporate intranet — not inside our app. If the copilot only lives where the article isn't, you don't use it, or you paste your reading into a cloud box and lose the entire reason you built a home lab.

So the extension's only allegiance is to your cluster. The trust boundary is identical to typing into the site yourself: same token, same `/v1` endpoints, same machines under your desk. The difference is it meets you on the page instead of making you come to it.

::blog-note{type="note"}
The extension requires an inference.club account and an API token — the same token your account already has, shown in `/dashboard/settings`. There's nothing to sign up for separately. If you self-host the whole platform, point the base URL at your own deployment and it works exactly the same.
::

## What it does today

The first release is deliberately small and sharp. Two surfaces, two actions.

**A side panel** (`chrome.sidePanel`), because a popup is the wrong shape for reading. Popups close the instant you click back into the page — useless when the whole task is *reading the page while the summary updates beside it*. The side panel docks to the edge of the window and stays put while you scroll. There's also a small toolbar **popup** for quick actions and an "open panel" button, but the panel is where the work happens.

**Summarize**, with a style menu — because "summarize" means different things at different moments:

- **Bullets** — 5–8 tight, information-dense points.
- **TL;DR** — two or three sentences for the "do I even need to read this" decision.
- **Takeaways** — the key points plus anything actionable.
- **ELI5** — explained simply, for when the article assumes background you don't have.

Each style is just a different instruction in front of the same article text; the output streams token-by-token into the panel as the model produces it.

**Ask** — a chat box pinned to the article. "What does this say about X?" "Does it mention benchmarks?" "Summarize only the methodology section." The article is held as context across turns, so you can interrogate it without re-pasting anything. The system prompt tells the model to answer from the article and to *say so* when it's reaching beyond it — a reading assistant that admits the article didn't cover something is far more useful than one that confabulates.

Connecting is a one-time paste: open the panel, drop in your API token, and it verifies by calling `GET /v1/models` and populating a picker with whatever your cluster is actually serving. Pick the model you want for reading work — a fast 8B for snappy summaries, something heavier for the gnarly stuff — and that choice is remembered. The base URL defaults to `https://api.inference.club` and is editable, so a local dev backend or your own domain both work without any code change.

## How the capture actually works

The interesting engineering is in *getting clean text out of a messy web page without sending anything anywhere*. Two facts about extensions make this both possible and private.

**The page is read in your browser, by you.** When you click the icon, the extension injects a tiny content script into the active tab and runs Mozilla's [Readability](https://github.com/mozilla/readability) on a clone of the DOM — the exact library behind Firefox's Reader Mode. It returns `{title, byline, text, excerpt}`: the article stripped of nav bars, cookie banners, and "related stories" rails. Because it runs inside the page as *you*, it works on the pages you actually read — including ones a server-side scraper could never reach: articles behind a login you're already authenticated to, an internal doc, a paywalled piece you legitimately have access to.

Here's the part I like. That extraction is wired so the extension never asks for broad permissions:

```ts
// content.ts — registered at "runtime", NOT in the manifest.
export default defineContentScript({
  registration: 'runtime',
  matches: ['https://inference.club/*'], // required by the API, unused for our injection
  main() { /* listen for EXTRACT_ARTICLE / GET_SELECTION */ },
});
```

The content script isn't declared to run on `<all_urls>`. It's injected on demand into the one tab you're looking at, which the `activeTab` permission grants *only* after you click the toolbar button. So the manifest's permission list reads, in full: `activeTab`, `scripting`, `storage`, `sidePanel`. No "read and change all your data on all websites" scare prompt, because the extension genuinely can't do that. It sees the tab you point it at, when you point it at it, and nothing else.

**CORS doesn't get in the way — and we don't make it our problem.** Browsers normally block a page from calling another origin's API. An extension that lists a host in `host_permissions` is exempt for its own extension-context fetches. So the API calls happen from the side panel, not from the content script, and the only hosts in `host_permissions` are the inference.club origins (plus localhost for dev). The server needed *zero* changes to support this — no CORS config, no new endpoint, no special extension auth. The token you have and the endpoints that already exist are the entire contract.

When you trigger an action, the panel sends the extracted text and your prompt to `/v1/chat/completions` with `stream: true` and reads the `ReadableStream` frame by frame, parsing the same OpenAI SSE shape the web playground does and appending deltas as they land:

```ts
const delta = json?.choices?.[0]?.delta?.content;
if (delta) yield delta;
```

That's the whole transport. A thin typed client (`lib/api.ts`) owns the contract, a streaming generator (`lib/chat.ts`) yields tokens, and the prompts live in their own file (`lib/prompts.ts`) so they're easy to tune without touching anything else. The extension has no backend of its own, no analytics, no telemetry — there's nowhere for your reading to go except your cluster.

## A note on context windows

Real articles are long, and the cluster's default reading model has a modest context window, so the extension caps article text at 24k characters and flags when it's truncated rather than silently dropping the tail. This is honest about a real limit instead of pretending a 30,000-word longread fits into an 8B model's window. As the catalog grows toward longer-context models, that cap loosens on its own — pick a bigger model in the picker and the same article goes in whole.

::blog-note{type="tip"}
The model picker reads from your live `/v1/models`, so it reflects whatever your fleet is serving *right now*. If you bring up a long-context model on a box this afternoon, it shows up in the panel this afternoon. The extension never assumes a specific model exists.
::

## Built with WXT and Vue

The stack is [WXT](https://wxt.dev) (Manifest V3, Vite under the hood) with Vue 3 and Tailwind v4. WXT was the right call for the same reason Tailscale was the right call for [the routing layer](/blog/tailscale-and-tsnet): it makes the boring, treacherous part — the manifest, the cross-browser differences, the build pipeline — someone else's solved problem, so the code we wrote is almost entirely the parts that are actually ours. File-based entrypoints, HMR while developing, and one codebase that targets Chrome, Edge, and Firefox. Vue because it matches the muscle memory from the main Nuxt app, and Tailwind because the bundle cost is negligible in an extension and the panel ends up looking like a piece of the product instead of a bolt-on.

The repo is small enough to read in a sitting: `entrypoints/` has the background worker, the content script, the popup, and the side panel; `lib/` has the API client, the Readability wrapper, the SSE stream parser, and the prompts. That's it.

## Where this goes next

Summarize and ask are the foundation, not the ceiling. The reason to build this on inference.club specifically — rather than as yet another wrapper around one chat endpoint — is that the cluster already serves far more than chat. The roadmap is about handing the article you're reading to the rest of the platform, in place:

- **Research** — instead of answering only from the article, hand it plus your question to the [Playground Agent](/blog) (`/v1/agent`), which can web-search, scrape related links, and synthesize across sources, rendering its tool calls as cards in the panel.
- **Narrate** — listen to an article, or its summary, as audio: a quick single-voice read, or a polished multi-voice Studio episode, played right in the side panel for the commute.
- **Illustrate** — generate a cover image or a diagram for whatever you're reading, from the title and summary.

Each of those is an endpoint your cluster can already serve. The extension's job is to point them at the page in front of you. I'll write those up as they land rather than promise dates here.

## Try it

The extension is open source at [`inference-club/browser-extension`](https://github.com/inference-club/browser-extension). You can clone it and `npm run dev` to load it unpacked today; a Chrome Web Store listing is on the way for the no-build path. You'll need an inference.club account and your API token — and, of course, a cluster to point it at. If you don't have hardware on the network yet, the [run-an-agent](/docs/providers/run-an-agent) guide gets your GPU serving in a few minutes, and then your reading copilot runs on it.

The thing I keep coming back to: the most personal data stream most of us produce is *what we choose to read*. It's reasonable to want that to stay home. This is the smallest possible client that lets it.
