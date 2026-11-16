---
title: Direct vs async
description: When to call the API and wait, and when to queue the work as a job, batch, or workflow.
category: Services
order: 2
---

# Direct vs async

There are two ways to run inference on inference.club. The **direct** path is a normal API call: you send a request and the response comes back on the same connection. The **async** path queues the work and returns immediately with a job you poll. Same models, same providers, same results — different control flow.

## The direct path

This is the default and what every OpenAI client does. The platform authenticates you, picks an online provider, forwards the request over the tailnet, and streams the answer straight back. For chat it streams token by token; images come back as URLs; audio and video come back as raw bytes — or as JSON with URLs if you send `"delivery": "url"`.

Use it for anything interactive — chat, quick images, transcriptions — where you want the result now and the call finishes in a reasonable time.

::callout{type="warning" title="Direct calls fail fast"}
If the chosen provider is offline or errors, a direct call fails — there's no automatic retry or failover to another provider. If the device is busy, a direct media call waits ~20 seconds for a slot and then returns `429 at_capacity`. For anything slow or contended (video, bulk work), use async — or `"async": "auto"`.
::

## The async path

Add `"async": true` to an async-capable request (chat, completions, images, video, music, speech, scrape) and instead of waiting you get a **job** back immediately:

```json
{ "id": "42", "object": "inference.job", "status": "QUEUED", "poll_url": "/v1/jobs/42", "queued_reason": "requested" }
```

A background worker picks the job up, runs it against a provider, and stores the result. You poll `GET /v1/jobs/42` until the status is terminal (`PROCESSED`, `FAILED`, or `CANCELED`), then read `output_text` (text results) or `media[].url` (media). Jobs can be listed, canceled, and retried. An `Idempotency-Key` header deduplicates retries so a network hiccup never enqueues the same work twice.

Why this exists: long-running generations (video especially) outlast a comfortable HTTP request, and async lets you fire many of them without holding connections open. It also gives the platform a place to **retry** transient failures and to **respect capacity** instead of overwhelming a GPU.

## `"auto"`: the best of both

`"async": "auto"` runs the request directly when a GPU slot is free (you get the normal `200` response) and queues it as a job (`202`, `queued_reason: "at_capacity"`) when the device is busy. If the model is known but its provider has blipped offline, `auto` queues it too (`queued_reason: "no_provider"`, waits up to an hour) instead of failing with `404`. This is the recommended mode for agents and scripts — see the [agent quickstart](/docs/quickstart-agents).

::callout{type="note" title="The dispatcher is a heartbeat, not a cron you configure"}
Async is powered by a Celery worker plus a beat tick that fans queued jobs out to providers as capacity frees up. You don't schedule anything; you enqueue, and the dispatcher drains the queue. Async is opt-in per deployment — a server without a broker returns `503 async_disabled`, and you fall back to direct.
::

## Capacity

Every provider service declares how many requests it can run at once — `max_concurrent`, default **1** — and services that share one GPU can join a **resource group** with a single shared budget (operators set these; see [Providers → Capacity](/docs/providers/kubernetes-agent#capacity)). There is **one budget per device**, shared by every path that can reach it: direct `/v1` calls, async jobs, batch items, workflow steps, playground agent tools, and retries. A device never receives more concurrent requests than its operator declared, no matter how the work arrives.

| You send | Device has a free slot | Device is full |
|---|---|---|
| Direct (no `async`) | Runs now | Waits ~20s for a slot, then `429 at_capacity` + `Retry-After` |
| `"async": "auto"` | Runs now | Queued → `202` (`queued_reason: "at_capacity"`) |
| `"async": true` | Queued → `202`, dispatched immediately | Queued → `202`, dispatched when a slot frees |

The `429` body is distinct from a rate-limit 429:

```json
{ "error": { "type": "at_capacity", "message": "Every GPU slot serving 'ltx-2' is busy right now…", "retry_after": 30 } }
```

`retry_after` (and the `Retry-After` header) is a hint based on the model's recent latency, between 5 and 120 seconds. A per-account rate limit instead returns `{"detail": "Request was throttled…"}`.

**LLM chat is the exception on the direct path.** LLM servers (vLLM, LM Studio, NIM) batch concurrent requests internally and a stream can last minutes, so direct chat calls aren't gated. Async LLM jobs still respect `max_concurrent`.

`GET /v1/capacity` reports the live state for each model you can reach — `in_flight`, `max_concurrent`, `queued`, `resource_group`, and `available` — so a client can schedule around busy devices. Be a good neighbor: keep at most two media requests in flight per device and let the queue absorb the rest.

## Batches

A **batch** submits up to **256** async requests as one atomic unit — handy for bulk generation (a hundred thumbnails, a dataset of transcriptions). Every item is validated up front: one malformed entry rejects the whole batch before anything is created. Each item becomes a normal job you can inspect individually, and the batch aggregates their statuses.

## Workflows

A **workflow** is a DAG of steps — the right tool when one step's output feeds the next. Steps reference each other with `{{ steps.<id>.output }}` templates, and the engine queues each step as its dependencies complete. Step kinds:

- **inference** — call one model.
- **map** — fan out over a list, one job per item.
- **transform** — a pure data step (split, pluck, join) with no model call.
- **collect** — gather a fan-out's outputs back into one list.
- **gate** — pause and wait for a human to approve (or edit) before continuing.
- **prompt** — a meta-prompting LLM step that writes the prompt for a later step.

Each step runs as a queued job, so it inherits the same capacity budget, retries, and durability as a standalone async job. The live run renders as an SVG graph in **Dashboard → Queue**, and you can author workflows visually in the [Workflow Studio](/docs/playground/overview#workflows).

## Which should I use?

| Want to… | Use |
|---|---|
| Chat, or get a quick image/transcription now | **Direct** |
| Generate video, or anything that takes a while | **Async job** (or `"async": "auto"`) |
| Script or agent calling any media model | **`"async": "auto"`** |
| Run the same operation over many inputs | **Batch** |
| Chain steps where output feeds the next, or need human review | **Workflow** |

For request shapes and every endpoint, see the [async jobs](/docs/api/jobs), [batches](/docs/api/batches), and [workflows](/docs/api/workflows) references.
