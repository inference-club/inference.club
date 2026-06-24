---
title: Direct vs async
description: When to call the API and wait, and when to queue the work as a job, batch, or workflow.
category: Services
order: 2
---

# Direct vs async

There are two ways to run inference on inference.club. The **direct** path is a normal API call: you send a request and the response comes back on the same connection. The **async** path queues the work and returns immediately with a job you poll. Same models, same providers, same results — different control flow.

## The direct path

This is the default and what every OpenAI client does. The platform authenticates you, picks an online provider, forwards the request over the tailnet, and streams the answer straight back. For chat it streams token by token; for media it returns the bytes (or a URL) when generation finishes.

Use it for anything interactive — chat, quick images, transcriptions — where you want the result now and the call finishes in a reasonable time.

::callout{type="warning" title="Direct calls fail fast"}
If the chosen provider is offline or errors, a direct call fails — there's no automatic retry or failover to another provider. For anything slow or flaky (video, large batches), prefer async.
::

## The async path

Add `"async": true` to any JSON-bodied generation request and instead of waiting you get a **job** back immediately:

```json
{ "id": "42", "object": "inference.job", "status": "QUEUED" }
```

A background worker picks the job up, runs it against a provider, and stores the result. You poll `GET /v1/jobs/42` until the status is terminal (`PROCESSED`, `FAILED`, or `CANCELED`), then read `result_url` / `result`. Jobs can be listed, canceled, and retried. An `Idempotency-Key` header deduplicates retries so a network hiccup never enqueues the same work twice.

Why this exists: long-running generations (video especially) outlast a comfortable HTTP request, and async lets you fire many of them without holding connections open. It also gives the platform a place to **retry** failures and to **respect capacity** instead of overwhelming a GPU.

::callout{type="note" title="The dispatcher is a heartbeat, not a cron you configure"}
Async is powered by a Celery worker plus a beat tick that fans queued jobs out to providers as capacity frees up — concurrency is bounded per service (and per shared resource group) so a single GPU isn't asked to do five things at once. You don't schedule anything; you enqueue, and the dispatcher drains the queue. Async is opt-in per deployment — a server without a broker returns `503 async_disabled`, and you fall back to direct.
::

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

Each step runs as a queued job, so it inherits the same capacity limits, retries, and durability as a standalone async job. The live run renders as an SVG graph in **Dashboard → Queue**, and you can author workflows visually in the [Workflow Studio](/docs/playground/overview#workflows).

## Which should I use?

| Want to… | Use |
|---|---|
| Chat, or get a quick image/transcription now | **Direct** |
| Generate video, or anything that takes a while | **Async job** |
| Run the same operation over many inputs | **Batch** |
| Chain steps where output feeds the next, or need human review | **Workflow** |

For request shapes and every endpoint, see the [async jobs](/docs/api/jobs), [batches](/docs/api/batches), and [workflows](/docs/api/workflows) references.
