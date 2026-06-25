---
title: "The debt we built: a state-of-the-codebase post"
description: "An honest accounting of the technical debt in inference.club after a year of shipping. Every new inference modality currently costs a copy-paste in three places — a backend view, a backend rerun runner, and a frontend page. Here's the architecture gap behind that, mirrored on both sides of the wire, and the sequenced plan to pay it down."
publishedAt: 2026-06-25
author: briancaffey
tags: [engineering, refactoring, deep-dive, architecture]
image_prompt: "Wide cinematic abstract illustration: a tangle of glowing parallel wires running left to right, many of them near-identical and redundant, slowly converging into a single clean bright cyan-and-violet conduit at the right edge, sense of consolidation and order emerging from sprawl, dark moody futuristic, soft glow, no text, no words, no letters"
---

inference.club serves a lot of different things now. Chat completions, embeddings, audio transcription, text-to-speech, voice cloning, music, video, image generation, 3D mesh. Each one is a real modality with real models behind it on real home GPUs, and shipping that breadth in under a year is the thing I'm proudest of.

It's also the thing that built the debt.

This is a post I'd normally keep in a private doc, but the whole premise of inference.club is that the code is open — [`inference.club`](https://github.com/inference-club/inference.club) and [`inference-club-agent`](https://github.com/inference-club/inference-club-agent) — so the honest version is the only version worth writing. If you clone the repo today and go looking for the dispatch layer or the API client, you won't find them, and you should know why before you judge the rest.

The short version: **every new modality costs a copy-paste in three places.** A backend view, a backend "rerun" runner, and a frontend page with its own composable. That's not three unrelated problems. It's the *same* missing abstraction, mirrored on both sides of the wire. Velocity was the right call — you don't discover the right shape of a dispatch layer until you've hand-written the eighth one — but the duplication is now the tax we pay on every feature, and it's time to pay it down instead.

## The five-second version

```
                    ADD ONE MODALITY (e.g. music)
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
  backend VIEW          backend RERUN          frontend PAGE
  (live request)        runner (retry/async)   + composable
        │                     │                     │
  select provider       select provider        read csrftoken cookie
  requests.post(        requests.post(         interpolate apiBase
    verify=False,         verify=False,        pick a fetch idiom
    proxies=…)            proxies=…)           re-fetch /v1/models
  persist Inference     persist Inference      hand-write poll/abort
    Request               Request                loop

   ── same loop, 14×  ──  ── same loop, 12× ──  ── same loop, 6 pages ──

        WHAT IT SHOULD BE (one primitive per side of the wire):

   backend:  dispatch.run(model, payload)  ◄── views AND runners call it
   frontend: useApiFetch() + useGenerationJob()  ◄── every page calls it
```

The through-line for the whole post is that one shared primitive on each side of the wire collapses most of this. There's no clever rewrite hiding here, no framework migration, no rejected-PR drama. Just a missing seam that I kept not cutting because shipping the next modality was always more urgent than refactoring the last one.

::blog-note{type="disclaimer"}
This is a self-audit of a fast-moving, mostly-solo project, not a postmortem of an outage. Nothing here is on fire. The point is to name the residue of shipping fast while it's still cheap to clean up, and to do it in public because that's the deal with an open codebase.
::

## Finding 1: the backend has no dispatch layer

Here's the shape of the backend. Four files carry most of the inference app:

```
openai_views.py   3,984 lines
views.py          3,064 lines
models.py         1,682 lines
serializers.py    1,442 lines
                 ──────
                 10,172 lines in 4 files
```

Inside `openai_views.py`, the same loop is hand-rolled fourteen times. Select a provider that serves the model, `POST` to it over the tailnet, persist an `InferenceRequest`. Concretely, it's this, copied with small variations:

```python
resp = requests.post(
    upstream_url,
    json=payload,
    proxies=_tailnet_proxies(),
    verify=False,
    timeout=...,
)
# ... then build and save an InferenceRequest
```

You can find that body, near-identical, in `_ChatOrCompletionsProxy.post` (`openai_views.py:551`), `AudioTranscriptionsView` (`:788`), `AudioSpeechView` (`:1170`), `VoiceGenerationsView` (`:1782`), `MusicGenerationsView` (`:2045`), `VideoGenerationsView` (`:2289`), `ImageGenerationsView` (`:2607`), and `Mesh3DGenerationsView` (`:3044`), among others. Eight modalities, eight hand-rolled copies of the proxy-and-persist loop, plus a few more for the variants.

Then the *whole thing is duplicated again*. Async jobs and retries need to re-run a request without an HTTP view in front of them, so there are twelve parallel `_rerun_*` runners — `_rerun_llm` (`:3398`) through `_rerun_video` (`:3815`) — each one a second copy of the same select-post-persist logic that the live view already implements. A live request and its retry are literally two different code paths to the same provider, and they drift. Fix a timeout in the view, forget the runner, and async requests for that modality keep the old behavior.

The closest thing to a dispatcher is a module-private dict at the bottom of the file:

```python
_RETRY_RUNNERS = {
    "llm": _rerun_llm,
    "image": _rerun_image,
    # ...
}
```

`openai_views.py:3896`. That dict is the seam — it's the one place that says "given a modality, here's how to run it" — but it only covers the rerun half, it's private, and it lives 3,900 lines deep in a view module. The core helpers everything needs (`_find_provider_for_model`, `_model_slug`, `_tailnet_proxies`) live in that same file too. So when nine other modules want to dispatch a request, they reach *back into the view module* with deferred in-function imports:

```python
def enqueue(...):
    from .openai_views import _RETRY_RUNNERS   # jobs.py:388
    ...
```

The same `from .openai_views import ...` appears in `jobs.py:388`, `agent_tools.py:244`, `narration.py:308`, `chat_threads.py:74`, and `agent.py:72`. The import is *inside the function* on purpose — at module load time it would be a circular import, because `openai_views` imports half of those modules right back. There are 147 of these in-function imports across the inference app. Each one is a small confession that the module graph has a cycle in it and we're routing around it one function at a time.

And in all twenty-two of those proxy call sites, `verify=False` is hardcoded. That's defensible today — the upstream is a tailnet hostname reached through a SOCKS proxy, so TLS verification against a MagicDNS name wouldn't mean much anyway (the [Tailscale post](/blog/tailscale-and-tsnet) explains why the mesh is the perimeter). But "defensible because of an invariant enforced somewhere else entirely" is exactly the kind of thing you want asserted in *one* place, not copy-pasted twenty-two times where any future edit can silently get it wrong.

The fix is a single `dispatch` service module. Provider resolution, tailnet proxying, and `InferenceRequest` persistence move into one function that both the live views and the rerun runners call:

```python
# dispatch.py  (the seam that doesn't exist yet)
def run(model, payload, *, user, modality, async_=False):
    provider = resolve_provider(model)
    resp = _post_to_provider(provider, payload)   # verify=False lives HERE, once
    return persist(InferenceRequest, ...)
```

A view becomes "parse request, call `dispatch.run`, serialize". A runner becomes "load the row, call `dispatch.run`". The `_RETRY_RUNNERS` dict and the fourteen-times loop both collapse into it. And because `dispatch.py` doesn't import any views, the nine modules that currently reach into `openai_views` import *it* instead — at the top of the file, like a normal module — and a big chunk of the circular-import tangle just dissolves.

`models.py` has a parallel problem worth naming in the same breath: it's a 26-class god-module, and some of those models do real work in overridden `save()` methods. `InferenceRequest.save` resolves the host and GPU for a request inline at `models.py:822` — a network-shaped side effect hiding in an ORM hook. Splitting `models.py` by domain (requests, providers, catalog, social) and moving that resolution into the dispatch path is the same move: give the side effect a name and a home instead of a hook.

## Finding 2: the frontend has no API client

Cross the wire and it's the same story in TypeScript.

There is no API client. There's no `useApiFetch`, no endpoint map, no shared catalog. Every composable that talks to the backend re-derives how to talk to the backend. The most literal example is the CSRF token. This exact line is copy-pasted across 26 composables, 19 of them byte-for-byte identical:

```ts
const csrftoken = document.cookie
  .split('; ')
  .find(c => c.startsWith('csrftoken='))
  ?.split('=')[1]
```

The base URL is interpolated inline at 38 call sites — `${config.public.apiBase}/v1/...` typed out by hand each time, with no map saying which endpoints exist. And there's no house rule for *how* to fetch, so the codebase uses four idioms at once: raw `fetch`, `$fetch` (20 times), `useFetch` (16 times), and a barely-used `useApi` (twice). Each has its own error-handling shape. Auth is by convention — `credentials: 'include'` plus a manually attached `X-CSRFToken` header — which means the failure mode is silent: forget the header on one new call and it 403s in a way that looks like a permissions bug, not a missing-line bug.

The catalog is the most wasteful instance. `/v1/models` is fetched and re-filtered independently in 13 composables. Thirteen network round-trips for the same list, thirteen slightly different client-side filters deciding what counts as a "chat" model versus a "music" model, with no shared cache and no single definition.

And then the pages. Six playground pages — chat, image, music, video, voice, mesh — total 3,838 lines, and each one re-declares the same state machine from scratch: `loading`, `error`, the model list, the result, and a hand-written poll-and-elapsed-and-abort loop for long-running generations. The video page's polling logic and the music page's polling logic are the same idea typed twice, and they've drifted in the details (one resets elapsed time on abort, one doesn't).

Three primitives collapse all of it:

```ts
useApiFetch(path, opts)   // base URL + CSRF + credentials + error
                          // normalization, in ONE place
useModelCatalog()         // fetch /v1/models once, cache it,
                          // expose typed filters by modality
useGenerationJob(opts)    // submit → poll → elapsed → abort,
                          // the playground state machine, once
```

`useApiFetch` is the mirror image of the backend's `dispatch.run`: the one place that knows how to make a request, so the 26 copies of the cookie-reader and the 38 inline base URLs each become a single call. `useModelCatalog` turns thirteen fetches into one cached store. `useGenerationJob` turns six bespoke poll loops into one tested primitive, and the playground pages shrink to "render the form, render the result."

::blog-note{type="tip"}
If you're building the client side of something like this, write the fetch wrapper *before* the second endpoint, not the twentieth. The cost of the missing wrapper isn't visible at call site #2 — it's invisible right up until the day you change auth or error handling and have to touch 38 files. A wrapper you can extend in one place is the cheapest insurance in frontend work.
::

## Finding 3: a thin safety net over an open-by-default config

The third finding is the one that makes the first two scarier than they need to be: the code that's riskiest to refactor is the code with the least test coverage.

There are **zero frontend behavioral tests.** What exists is Playwright *visual* specs — the overflow harness, screenshot baselines, the design-quality captures from [PRD 05](/blog/from-docker-sprawl-to-k3s). Those are genuinely useful and they catch layout regressions, but they assert nothing about behavior. `@nuxt/test-utils` is already in `package.json`; it's just never been used to test what a composable *does*. So the dispatch logic and the poll loops — exactly the code I most want to consolidate — are the code I can least safely touch, because nothing will tell me if I break it.

Then there's the config, which fails *open* instead of closed. In `settings.py`:

```python
SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-...")  # :39
DEBUG = os.environ.get("DEBUG", "True") == "True"                 # :44
ALLOWED_HOSTS = ["*"]                                             # :46
```

Read those three together. A deploy that's missing its environment — a broken secret manager, a typo'd env file, a fresh box someone brought up by hand — doesn't crash. It comes up with a real literal `SECRET_KEY` baked into the source, `DEBUG=True`, and `ALLOWED_HOSTS` wide open. The failure mode of a misconfiguration is "running and exposed," which is the worst possible default for the failure mode of a misconfiguration. Security-relevant settings should refuse to start outside dev rather than paper over their own absence.

And a couple of small hygiene items, named so they actually get fixed: there's production `console.log` of auth and token state in `useToken.ts` and `useAuth.ts` (token state should never reach a browser console on a deployed build), and there's a stray `audio.wav` — 796 KB — committed at the repo root from some long-ago test. Neither matters much. Both are the kind of thing that, left alone, teaches everyone who reads the repo that this is the standard.

The fix here is ordering, not heroics: make the security envs required (raise on absence outside dev), strip the debug logging, delete the wav. Then make the *first* things covered by new tests be the new dispatch layer and the new API client — the highest-leverage, highest-risk code gets the safety net first, so the consolidation in Findings 1 and 2 happens on top of tests instead of under them.

## The plan, in order

None of this is a rewrite, and that's the point. It sequences:

1. **Make the config fail closed.** Required security envs, strip debug logging, delete the stray binary. Smallest diff, removes the scariest failure mode, unblocks nothing — do it first because it's free.
2. **Land `useApiFetch` and write its tests.** One wrapper: base URL, CSRF, credentials, error normalization. Migrate the 26 cookie-readers and 38 inline base URLs onto it incrementally — it coexists with the old idioms, so there's no big-bang switch.
3. **Add `useModelCatalog`.** Collapse 13 fetches into one cache. Falls out almost for free once `useApiFetch` exists.
4. **Extract `dispatch.run` on the backend, with tests.** Provider resolution + tailnet proxy + persistence in one module that views and runners both call. This is where the circular imports die and `verify=False` becomes a single line.
5. **Collapse the rerun runners and the playground pages.** With `dispatch.run` and `useGenerationJob` in place, the twelve `_rerun_*` functions and the six bespoke poll loops delete themselves.

The test for whether this worked is concrete and falsifiable: **adding the next modality should touch a config map and a form, not three copy-pasted code paths.** Today the marginal cost of a modality is a backend view plus a rerun runner plus a frontend page, each a fresh copy of a loop we've already written eight times. When it's a registry entry plus a render, the debt is paid.

The reason I'm not worried about it is the same reason the debt exists in the first place. The duplication isn't scattered randomly — it's the *same* missing seam in eight backend views, twelve runners, and six pages, and the *same* missing wrapper in 26 composables. Regular debt is expensive to pay down because it's everywhere and different. This debt is everywhere and identical, which means one good primitive on each side of the wire retires most of it at once. That's the best kind of debt to find when you finally sit down to read your own codebase honestly: a lot of lines, one idea.

If you want to read along, it's all in the open — [`inference.club`](https://github.com/inference-club/inference.club) and [`inference-club-agent`](https://github.com/inference-club/inference-club-agent) — and the line numbers above are from `main` as of this writing. By the time you read this, hopefully some of them no longer point at what they point at now.
