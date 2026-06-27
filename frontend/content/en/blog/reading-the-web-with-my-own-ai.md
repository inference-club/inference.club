---
title: "Reading the web with my own AI: the extension, a month in"
description: "A couple of weeks ago I shipped a deliberately tiny reading copilot — a side panel that summarizes and asks about whatever you're reading, on your own cluster. Then I kept building. This is the tour: vision attachments, a speed reader, per-URL history, ten themes, an advanced mode that shows you exactly what was sent — and where it goes next."
publishedAt: "2026-06-26"
author: briancaffey
tags: [browser-extension, privacy, llm-inference]
image: /images/blog/reading-the-web-with-my-own-ai.png
image_prompt: "Wide cinematic abstract illustration: a translucent vertical side panel of cyan and violet light docked beside a softly glowing page of flowing abstract particles, one bright focal point isolated in a beam as the stream rushes past it (a speed-reading motif), a small glowing house containing a GPU in the distance feeding light into the panel, faint shimmering bands of different color palettes along one edge, dark moody futuristic, soft glow, no text, no words, no letters"
---

I read a lot on the web — long articles, documentation, research write-ups, the
occasional rabbit hole. The friction was always the same: when I wanted to *do*
something with what I was reading — summarize it, ask a question, double-check a
claim — I had to copy text out of the page, paste it into some other tab, and
lose my place. So a couple of weeks ago I [shipped the smallest possible fix](/blog/a-reading-copilot-that-runs-on-your-own-gpu):
a browser extension that docks a side panel next to the page and summarizes or
answers questions about it, streamed from **my own
[inference.club](https://inference.club) cluster** — my models, my data, nothing
in the middle.

That first release was deliberately small: two surfaces, two actions. Then I
kept going. This is a tour of what it has become — what it does now, how it
works, and where I want to take it next. It's still
[open source](https://github.com/inference-club/browser-extension) and it's
still a thin client of the [`/v1` API](https://github.com/inference-club/inference.club)
the playground already uses; the server hasn't gained a single line of code on
its behalf.

## What it is

The extension is a thin, open client for an OpenAI-compatible inference endpoint
— in my case my inference.club account, but it points at anything that speaks the
same API, including a model running on `localhost`. You paste an API token once,
and from then on every article you open gets a little AI workbench docked to its
side.

The important framing hasn't changed since the [first post](/blog/a-reading-copilot-that-runs-on-your-own-gpu),
and it's still the whole point: **it's a copilot for the page in front of you,
not a data funnel.** The page is read locally in your browser, nothing is sent
anywhere until you click an action, and when it is sent it goes only to the
endpoint you configured. No analytics, no third parties, no servers of mine in
the middle.

::blog-note{type="note"}
You need an inference.club account and an API token — the same token already on
your account in `/dashboard/settings`. There's nothing to sign up for
separately. If you self-host the whole platform, point the base URL at your own
deployment and everything below works identically.
::

## How it works

Under the hood it's deliberately simple, which is part of why it's pleasant to
use:

- **Local extraction.** When the panel is open it reads the *readable* version
  of the current tab using Mozilla's
  [Readability](https://github.com/mozilla/readability) — the same engine behind
  Firefox's Reader Mode. You get the article text, title, byline, and metadata,
  with the page's nav, ads, and chrome stripped away. This happens entirely on
  your machine.
- **Streaming chat.** Actions turn that text into a prompt and stream the
  response back token-by-token over the OpenAI-compatible
  `/v1/chat/completions` endpoint. You watch the answer appear instead of
  staring at a spinner.
- **Your endpoint, your rules.** The base URL and token are yours. Swap in a
  different model, or point it at a self-hosted backend, and nothing else
  changes.
- **Built to stay out of the way.** It's a Manifest V3 extension (built with
  [WXT](https://wxt.dev) + Vue 3 + TypeScript + Tailwind) whose primary surface
  is the Chrome **side panel**, so the AI sits *beside* what you're reading
  rather than covering it.

Everything you generate stays on your device: preferences and chat history live
in local browser storage, never synced off the machine.

## The features

### Summarize, your way

One click turns the page into a **TL;DR**, **bullet points**, **key takeaways**,
or a plain-language **ELI5** explainer. Great for triaging whether a long piece
is worth your full attention.

### Ask — a real conversation about the page

Ask follow-up questions and get answers grounded in the article. It's
**multi-turn**: "summarize this," then "expand on point 3," then "is that claim
actually supported?" — it remembers the thread. Answers render as proper
**Markdown**, so headings, lists, tables, and code come out formatted instead of
as a wall of text.

### Attach images from the page

Sometimes the interesting part of a page is a chart, a diagram, or a screenshot.
A **＋** button scans the current page for images and lets you pick a few to
attach to your question — they're sent to the model as vision input. "What does
this graph show?" finally has an obvious answer.

::blog-note{type="tip"}
Vision needs a multimodal model, and the picker reads from your live
`/v1/models` — so whether image attachments do anything depends on what your
fleet is serving right now. Bring up a vision model on a box this afternoon and
the ＋ button starts paying off this afternoon. The extension never assumes a
specific model exists.
::

### Speed reader

This is my favorite. Any article *or* any AI response can be sent to an
immersive **speed reader** that flashes one word at a time (RSVP), with an
optimal-recognition-point highlight to keep your eyes still. Play, pause,
resume, scrub through the text, and tune the words-per-minute, font, size,
color, and how many context words to show around the focus word. It turns "I'll
read this later" into "I'll read this now, in two minutes."

### Persistent history, organized by site

Every conversation is **saved per page URL** and browsable in a History view,
grouped by website and filterable by text. Jump back to a past thread, or click
straight through to the original source page. Your reading and your questions
become a little searchable knowledge trail instead of disappearing when you
close the tab.

### It follows you as you browse

Switch tabs or navigate to a new article and the panel **automatically
re-reads** the page in front of you. No re-clicking, no stale content — the
copilot is always about whatever you're actually looking at.

### Themes that are easy on the eyes

Ten hand-tuned light and dark palettes — Daylight, Paper, Mist, Midnight, Nord,
Dracula, Solarized, Gruvbox, Forest, Rosé — plus "match system." The theme
picker shows a **live preview** of each one, so you can pick something
comfortable for a long reading session in dim light.

### Advanced mode for the curious

Flip on Advanced mode and each response reveals what happened under the hood:
time to first token, total time, token usage, finish reason, and request size —
plus full page metadata. You can even expand the exact **system prompt and
article context** that was sent to the model, so there's no mystery about what
the AI was actually given.

::blog-note{type="note"}
Advanced mode is the honest version of the privacy promise: instead of asking
you to trust that nothing weird is being sent, it shows you the literal bytes
that left your browser. The trust boundary is the same as typing into the site
yourself, and now you can verify it per request.
::

### Streaming toggle

Streaming is on by default, but you can switch to "show the whole reply at once"
if you prefer a cleaner, all-at-once result.

## How it actually changes my browsing

A few habits have genuinely shifted:

- **I triage before I commit.** A quick bullet summary tells me whether a
  4,000-word piece deserves my next twenty minutes.
- **I interrogate what I read.** Instead of passively trusting an article, I ask
  it to check claims, define jargon, or compare two sections — right there, in
  context.
- **I read faster when I want to.** The speed reader gets me through a backlog of
  "save for later" tabs that I'd otherwise never reopen.
- **My reading leaves a trail.** Because every thread is saved by URL, I can come
  back weeks later and find both the source and what I asked about it.
- **It's mine.** Running on my own cluster means I'm not feeding a third party my
  reading habits, and I can use whatever model I want.

The throughline is that the web stops being a one-way stream of text and becomes
something I can *converse with*, on my terms, without leaving the page.

## Next steps

Plenty I want to build from here:

- **Narration / text-to-speech.** Listen to an article or its summary read
  aloud, with the speed reader's word highlighting synced to the audio — reading
  and listening at once, perfect for walks or tired eyes.
- **Image generation.** Generate diagrams, hero images, or
  "explain-this-as-a-picture" visuals from the page or a summary, and drop them
  right into the thread.
- **Research mode.** Let the model go beyond the single page — web search plus
  synthesis across multiple sources via an agent loop, with citations, so a
  question can pull in context the article didn't have.
- **Selection-aware actions.** Highlight a paragraph and act on just that —
  "explain this," "translate this," "steelman this argument."
- **Smarter image handling.** Auto-downscale attached images to keep payloads
  small, and let me draw a box on the page to capture a region instead of
  picking whole images.
- **Keyboard-first flow.** Shortcuts to open the panel, summarize, start the
  speed reader, and send a follow-up — never touch the mouse.
- **Export and share.** Save a thread (and its source link) to Markdown, or push
  it to a notes app, so insights flow out into the rest of my tools.
- **Search across my history.** Semantic search over every conversation I've had
  — "what was that article about retrieval caching, and what did I ask about
  it?"
- **More browsers and surfaces.** A Firefox build, and maybe a mobile companion.

Several of those — narration, image generation, research — already have
endpoints my cluster serves today; the extension's job is just to point them at
the page in front of me. The fun part is that the foundation — local extraction,
your own model, a calm side panel — makes all of these feel like natural
extensions rather than bolt-ons. The web is the input; the copilot is whatever I
decide to make of it next.

If you want to try it: the extension is open source at
[`inference-club/browser-extension`](https://github.com/inference-club/browser-extension)
— clone it and run it unpacked today. You'll need an inference.club account and
your API token, and a cluster to point it at. If you don't have hardware on the
network yet, the [run-an-agent](/docs/providers/run-an-agent) guide gets your GPU
serving in a few minutes, and then your reading copilot runs on it.
