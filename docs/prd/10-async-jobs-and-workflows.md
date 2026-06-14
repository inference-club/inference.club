# PRD 10 — Async jobs, batches & media workflows

> **Status:** V0–V2 implemented (2026-06-13) — backend + frontend. Jobs,
> batches, the workflow DAG engine, and the live DAG viewer all ship; covered
> by `apps/inference/tests/test_async_jobs.py` (17 tests; suite total 354).
> Async is opt-in and dark unless a Redis broker is configured
> (`ASYNC_ENABLED`); synchronous inference is unchanged.
>
> **Implementation (keep in sync):**
> - models: `InferenceRequest` async/queue fields + `FAILED`/`CANCELED`
>   statuses; `Batch`, `Workflow`, `WorkflowRun`, `WorkflowStepRun`,
>   `ResourceGroup`; `ProviderService.max_concurrent` + `resource_group`
>   (migration `0026`).
> - execution: `apps/inference/jobs.py` (enqueue, `dispatch_due_jobs` with
>   capacity gating, `run_job`, retry/backoff, cancel, reaper, **self-driving
>   `kick_dispatch`** so the worker drains the queue without depending on beat,
>   `auto_model_for` for portable steps) reuses the existing
>   `openai_views._RETRY_RUNNERS` as the request-less executor;
>   `apps/inference/workflows.py` (spec validate, templating, DAG advance,
>   fan-out, transform/collect, human gate, run-time model auto-resolution);
>   `apps/inference/workflow_templates.py` (curated, seed-with-inputs sample
>   workflows); `backend/celery.py` + beat tick (heartbeat surfaced as
>   `worker_stalled` in the queue summary). Beat is a safety net (retry backoff
>   + reaper); the common path is driven by the worker.
> - API: `async: true` on `/v1/chat/completions|images|videos|music|audio/speech`;
>   `/v1/jobs[/<id>[/cancel|/retry]]`, `/v1/batches[/<id>]`,
>   `/v1/workflows/runs[/<id>[/steps/<step>/<action>]]`,
>   `/api/inference/queue/summary/`; manifest validator accepts
>   `max_concurrent` + `resource_groups`.
> - frontend: `composables/useAsyncJobs.ts`, `components/workflow/WorkflowDag.vue`
>   (SVG DAG + live media), `pages/dashboard/queue/index.vue` +
>   `pages/dashboard/queue/runs/[id].vue`; nav + i18n.
> - infra: `celery-worker` + `celery-beat` in dev compose and the prod template.
>
> **V0 scope notes / deferrals:** async submission covers the JSON-bodied
> modalities (LLM/IMAGE/VIDEO/MUSIC/TTS); file-input modalities
> (STT/MESH/VOICE/image-edits) stay synchronous (and retry-able) for now and
> participate in workflows only via stored input assets. Capacity is enforced
> by live Postgres counts (per provider+service_type and per resource group)
> rather than Redis slot counters — simpler and race-free; the Redis-counter
> optimization in §5.3 is unneeded. Async submission validates routability at
> submit time (a provider for the model must be online), then late-binds to a
> free provider at run time; "queue for an entirely offline model" is the one
> deferred capability. Notifications are poll-based (the queue page + summary
> endpoint); SSE/email deferred to V3.
>
> **Author:** Brian (spec) · drafted & implemented with Claude Code.
>
> **Scope:** Add an opt-in **asynchronous / queued** execution path for
> inference, so a human, an API client, or an agent can submit *more
> work than the cluster can run at once* and trust that it will all
> eventually run and be saved. Three layers, each built on the one
> below: **jobs** (one queued inference request), **batches** (a list of
> independent jobs submitted together), and **workflows** (a dependency
> graph of steps that pass data between modalities — e.g. turn an
> article into narrated audio + images + video + music). Capacity is
> declared per service in `agent.yaml` (including the "two services on
> one GPU, only one runs at a time" case). Celery + Redis become the
> execution engine; Postgres stays the source of truth.
>
> **Explicitly out of scope:** designing any *specific* media pipeline
> (the article→media flow is the motivating example, not a deliverable);
> changing live/synchronous inference behavior (see §2); payments or
> per-job billing (PRD 03 territory); cross-provider load balancing
> beyond "pick a free slot."

---

## 1. Summary

Today every inference request is **synchronous**: the backend proxies
to an agent over the tailnet and the client blocks until the agent
responds (`openai_views.py`, 300 s upstream timeout). That's perfect for
the playground and for one-off API calls, and it isn't going away. But
it can't express:

- "Generate these 40 images; I only have one image box, drain it over
  the next hour."
- "Run this batch and let me close my laptop — I'll find the results in
  my library."
- "Take this article, have the LLM split it into sections, narrate each
  with TTS, check the narration with ASR, then generate an image and a
  short video per section, then a music bed — and wire the output of
  each step into the next."

This PRD adds a **queue** in front of the existing proxy and a **graph**
on top of the queue. The atomic unit is a **job**: exactly today's
inference request, but created in a `QUEUED` state and executed later by
a worker when a capacity slot frees up. A **batch** is a list of jobs
submitted in one call. A **workflow** is a DAG of steps whose edges are
data dependencies, with support for dynamic fan-out (one LLM step emits
N sections → N image jobs) and human-in-the-loop gates.

The execution engine is **Celery** (workers + beat), with **Redis** as
broker and as the home for live concurrency counters. **Postgres remains
the source of truth** for every job's state, payload, and result — so
the whole system is inspectable with a SQL query and survives a worker
restart. The work is mostly *addition*: a new execution path that reuses
the existing routing, provider selection, proxy, metering, and content
model wholesale.

---

## 2. What does NOT change (live inference & the sandbox)

This is the load-bearing promise. **Synchronous inference is untouched.**

- `POST /v1/chat/completions`, `/v1/images/generations`,
  `/v1/videos/generations`, `/v1/audio/transcriptions`, `/v1/audio/speech`,
  `/v1/3d/generations`, `/v1/music/generations`, `/v1/voice/generations`
  with **no async flag** behave exactly as they do today: route, proxy,
  block, return the result inline.
- **SSE streaming** for chat/completions stays synchronous — you can't
  meaningfully "queue" a token stream, and the playground depends on it.
- The **playground / sandbox** is unchanged by default. It keeps doing
  live calls; the queue is opt-in (a "send to queue" affordance, §5.7,
  is additive).
- **Routing, provider selection, auth, manifests, metering, the content
  model** (`InferenceRequest`, visibility, collections, stars) are all
  reused, not forked. An async job is the same `InferenceRequest` row it
  always was — just created `QUEUED` and run by a worker instead of the
  web process.
- No new required infra for anyone running sync-only: if Celery workers
  aren't deployed, sync still works; only the async path is dark.

Async is **strictly opt-in.** A request becomes a queued job only when
the caller asks (`async: true`, or by submitting a batch/workflow).

---

## 3. What this enables

- **Submit more than capacity.** Queue 100 images against one GPU; they
  drain in order, respecting the box's concurrency limit, until done.
- **Survive disconnect.** Close the browser / drop the connection — the
  job keeps running on the worker and the result lands in your library.
  (Today a client disconnect can orphan the agent's work and mark the
  request errored.)
- **Batch submit.** One API call enqueues many requests across
  modalities; one id to poll.
- **Express the "only one at a time on this box" reality.** A provider
  declares that two services share a GPU and only one may run; the
  dispatcher honors it automatically.
- **Build media as a graph.** Humans and agents author workflows that
  chain modalities with data flowing between steps and dynamic fan-out —
  the motivating article→media pipeline becomes *expressible* without
  the platform hardcoding it. Agents are first-class authors: a workflow
  spec is plain JSON an agent can emit.
- **Retry & idempotency.** Transient failures (agent offline, 5xx,
  timeout) retry with backoff; idempotency keys make resubmits safe.

---

## 4. Current state (grounded in code)

| Concern | Where | Today |
| --- | --- | --- |
| Request execution | `apps/inference/openai_views.py` (the proxy views) | Fully synchronous; backend POSTs to `http://{tailnet_hostname}:{agent_port}/v1/…`, blocks ≤ 300 s (`UPSTREAM_TIMEOUT_SECONDS`). |
| Request record | `InferenceRequest` (`apps/inference/models.py:486-630`) | Has a `status` field whose choices already include **`QUEUED`** and **`SAVED`** — *defined but unused*. Real states used: `PROCESSING → PROCESSED`, or `REQUESTED` on error. Stores `payload`, `results`, metering, visibility. |
| Provider / service | `Provider`, `ProviderService` (`models.py:74-251`) | `is_online` (last_seen ≤ 120 s), `accepting_requests` kill switch. **No concurrency or capacity fields.** |
| Routing | `_find_provider_for_model()` (`openai_views.py:363-397`) | Returns the first online match (own-nodes-first per routing preference). No load balancing, no "is it busy" check. |
| Manifest | `manifest_validator.py` | `services[]` declare `type/engine/url/features/models`. **No `max_concurrent`, no resource groups.** |
| Celery | `pyproject.toml` (`celery ^5.5.2`), `flower` in lockfile | **Dependency present, never wired** — no app, no config, no tasks, no broker. `probe_providers` is a management-command loop, explicitly "no Celery / Redis broker." |
| Redis | `settings.py:230-243` | Used only as the Django **cache** backend (throttling). No broker, no queues. |
| Client disconnect | proxy `finally` blocks | Socket close mid-proxy raises → status `REQUESTED` (error); agent may keep running with no cancel signal. |
| Timeouts | proxy 300 s; gunicorn 600 s; Caddy default | Constrain long sync requests; **irrelevant to async** (web returns 202 immediately). |

**Four facts that shape the design:**

1. `InferenceRequest.status` already has `QUEUED`/`SAVED` — the model is
   half-ready for a state machine; we formalize it.
2. The proxy logic (route → POST → parse → save → meter) is the same
   work a worker must do. Refactor it into a callable the **web process
   and the Celery worker both invoke**, so sync and async share one path.
3. There is no capacity concept anywhere; it must be introduced at the
   manifest (declaration) and at a live counter (enforcement).
4. Celery is already a dependency — wiring it is expected, not a new bet.

---

## 5. Design

### 5.1 The job (an async `InferenceRequest`)

A job **is** an `InferenceRequest`. No parallel model. Add fields:

```python
# InferenceRequest additions
is_async        = BooleanField(default=False)   # created QUEUED, run by a worker
queued_at       = DateTimeField(null=True)
started_at      = DateTimeField(null=True)
finished_at     = DateTimeField(null=True)
attempts        = PositiveIntegerField(default=0)
max_attempts    = PositiveIntegerField(default=3)
priority        = SmallIntegerField(default=0)   # higher runs first
idempotency_key = CharField(null=True, db_index=True)  # unique per user
error           = JSONField(null=True)           # last failure detail
canceled_at     = DateTimeField(null=True)
# graph linkage (null for standalone jobs)
batch           = ForeignKey("Batch", null=True, related_name="jobs")
step_run        = ForeignKey("WorkflowStepRun", null=True, related_name="jobs")
```

**Status machine** (formalize the existing field):

```
QUEUED ──claim──▶ PROCESSING ──ok──▶ PROCESSED
   ▲                  │  └──fail, attempts<max──▶ QUEUED  (retry, backoff)
   │                  └──fail, attempts=max────▶ FAILED
   └──── (created) ───┘
QUEUED|PROCESSING ──cancel──▶ CANCELED
```

Add `FAILED` and `CANCELED` to the choices; reuse `QUEUED`/`PROCESSING`/
`PROCESSED`. The legacy `REQUESTED` error state is migrated to `FAILED`
(data migration; the sync error path also moves to `FAILED`, which is
clearer). `SAVED` is retired.

A **synchronous** request stays `is_async=False` and runs inline exactly
as today (it may write `PROCESSING`→`PROCESSED` without ever touching the
queue). The shared executor (fact #2) is the only code that proxies.

### 5.2 Capacity & resource groups (declared in `agent.yaml`)

Extend the manifest schema (`manifest_validator.py`, `schema_version`
bump) so providers declare how much can run at once:

```yaml
services:
  - type: image
    url: http://flux:8000
    max_concurrent: 1
    resource_group: gpu0        # shares a slot pool with...
  - type: video
    url: http://ltx:8001
    max_concurrent: 1
    resource_group: gpu0        # ...this one — only one of the two runs

resource_groups:                # optional; caps a shared pool
  gpu0:
    max_concurrent: 1           # the GPU can host only one job at a time
```

Semantics:

- `max_concurrent` on a **service** caps that service's own in-flight
  jobs (default `1` if omitted — conservative and correct for a single
  GPU worker; a vLLM box that batches can declare more).
- `resource_group` names a shared pool. Services in the same group draw
  from `resource_groups.<name>.max_concurrent` (default `1`). This is how
  you say "image and video live on the same card; never both at once."
- A job needs **both** a free service slot **and** a free group slot to
  start. No group → service slot only.

Persist these on the backend: add `max_concurrent` to `ProviderService`,
and a small `ResourceGroup` table (`provider`, `name`, `max_concurrent`)
populated from the manifest on registration/refresh. Validation:
`resource_group` must reference a declared group (or be standalone);
`max_concurrent ≥ 1`.

### 5.3 Dispatcher: Celery + beat + Redis slots, Postgres = truth

Three moving parts:

1. **Postgres is the durable queue.** Jobs are `QUEUED` rows. Nothing is
   lost on a worker/broker restart; recovery = re-scan Postgres.
2. **Celery beat dispatcher tick** (every ~1–2 s, the one periodic task)
   does the *scheduling decision*:

   ```sql
   SELECT … FROM inference_inferencerequest
   WHERE status = 'QUEUED' AND is_async
   ORDER BY priority DESC, queued_at ASC
   FOR UPDATE SKIP LOCKED
   LIMIT N;
   ```

   For each candidate: resolve its provider/service (reuse
   `_find_provider_for_model`), check the **live slot counters** for that
   service and its resource group. If a slot is free *and* the provider
   `is_online` and `accepting_requests`: atomically `INCR` the slot
   counter(s) in Redis, mark the row `PROCESSING`/`started_at`, and
   enqueue a Celery task `run_job(job_id)`. Otherwise leave it `QUEUED`
   for a later tick. `SKIP LOCKED` makes the tick safe to run
   single-instance (it will be) and harmless if it ever double-fires.
3. **Celery worker task `run_job(job_id)`** does the actual work via the
   shared executor (§5.1, fact #2): proxy to the agent, parse, save
   `results`, meter, set `PROCESSED`/`finished_at`. In a `finally`, it
   **releases the Redis slot(s)** so the next tick can schedule more.

**Redis slot counters** are keyed `slot:{provider_id}:{service_id}` and
`slot:{provider_id}:group:{name}`, with a TTL/lease (e.g. job timeout +
margin) so a crashed worker that never releases can't deadlock the pool —
a reaper (in the beat tick) reconciles counters against actual
`PROCESSING` rows. Postgres is authoritative; Redis is the fast hint.

> **Why not "agent pulls work"?** Considered (the agent knows its own GPU
> best). Rejected for V0 because it needs changes in the agent repo and a
> results-upload path. Backend-side slots reuse the existing
> backend→agent proxy unchanged and keep all logic in one repo. The
> manifest already declares capacity, so the backend has enough to
> schedule well. Revisit if declared limits drift from reality.

### 5.4 Batches

A `Batch` groups jobs submitted together:

```python
class Batch(models.Model):
    user        = ForeignKey(CustomUser, related_name="batches")
    label       = CharField(blank=True)
    created_at  = DateTimeField(auto_now_add=True)
    # status derived from member jobs: QUEUED|RUNNING|DONE|PARTIAL|FAILED
```

`POST /v1/batches` accepts a list of requests, each naming an endpoint +
body, creates one `QUEUED` job per item in a transaction, returns the
batch id and per-job ids. `GET /v1/batches/{id}` returns aggregate
status + each job's status/result. Cancel a batch → cancel its
non-terminal jobs.

```jsonc
POST /v1/batches
{ "label": "hero shots",
  "requests": [
    { "endpoint": "/v1/images/generations", "body": { "prompt": "…" } },
    { "endpoint": "/v1/videos/generations", "body": { "prompt": "…" } }
  ] }
→ 202 { "batch_id": "batch_…", "jobs": [ { "id": "job_…", "status": "QUEUED" }, … ] }
```

### 5.5 Workflows: execution graphs (the ambition)

This is what makes "build interesting media" possible. A **workflow** is
a DAG declared as data (JSON/YAML — emittable by an agent), separating
the *definition* from a *run*:

```python
class Workflow(models.Model):       # the reusable definition
    user, name, spec (JSONField), created_at, …

class WorkflowRun(models.Model):    # one execution
    workflow (FK, null for ad-hoc), user, status, inputs (JSON),
    context (JSON: accumulated step outputs), created_at, …

class WorkflowStepRun(models.Model):  # one step within a run
    run (FK), step_id (str from spec), status,
    depends_on (list of step_ids), output (JSON), error (JSON)
    # the jobs this step spawned point back via InferenceRequest.step_run
```

**Step kinds** (small, composable — not modality-specific):

- `inference` — run one `/v1/*` request (becomes one job). Body is
  templated from upstream outputs.
- `map` / fan-out — given a list from an upstream step, spawn one job
  **per item** (dynamic width: LLM returns 8 sections → 8 image jobs).
- `transform` — a pure data step (split/format/collect), run by the
  worker without an agent; e.g. chunk LLM text into TTS-sized pieces.
- `gate` — **human-in-the-loop**: the run pauses; a `GET` shows the
  pending output, a `POST .../approve|reject|edit` resumes or alters it.
- `collect` — join fan-out results back into one list for the next step.

**Data flow** is by templating against the run `context`, e.g.
`{{ steps.split.output.sections[i].text }}`. The dependency edges are
the `depends_on` references; the engine runs a step when all its deps are
`PROCESSED`. Fan-out steps create child `WorkflowStepRun`s.

**Engine** = the same dispatcher. A workflow run is a recurring
reconcile: the beat tick (or an event on each job completion) asks "which
steps now have all deps satisfied?" and **enqueues their jobs as normal
queued jobs**. So workflows get capacity scheduling, retries, and
durability *for free* — a workflow is just a job factory that reads the
graph. No separate execution engine.

The motivating example (article → narrated media), expressed — *as an
illustration of expressiveness, not a deliverable*:

```jsonc
{
  "inputs": { "article": "…", "voice_id": "…" },
  "steps": [
    { "id": "outline", "kind": "inference", "endpoint": "/v1/chat/completions",
      "body": { "model": "…", "messages": [{ "role": "user",
        "content": "Split into narrated sections + image prompt each:\n{{inputs.article}}" }] } },
    { "id": "narrate", "kind": "map", "over": "{{steps.outline.output.sections}}",
      "endpoint": "/v1/audio/speech",
      "body": { "voice": "{{inputs.voice_id}}", "input": "{{item.text}}" } },
    { "id": "check", "kind": "map", "over": "{{steps.narrate.output}}",
      "endpoint": "/v1/audio/transcriptions", "body": { "file": "{{item.audio}}" } },
    { "id": "review", "kind": "gate", "depends_on": ["narrate", "check"] },
    { "id": "images", "kind": "map", "over": "{{steps.outline.output.sections}}",
      "endpoint": "/v1/images/generations", "body": { "prompt": "{{item.image_prompt}}" } },
    { "id": "clips", "kind": "map", "over": "{{steps.images.output}}",
      "endpoint": "/v1/videos/generations",
      "body": { "image": "{{item.url}}", "prompt": "{{item.motion}}" } },
    { "id": "music", "kind": "inference", "endpoint": "/v1/music/generations",
      "body": { "prompt": "ambient bed for {{inputs.article|summary}}" } }
  ]
}
```

We are **not** designing this pipeline now. V0/V1 ship jobs + batches;
V2 ships the workflow engine; the point of this section is to prove the
primitives are sufficient and the API agent-authorable.

### 5.6 Retries, idempotency, cancellation, timeouts

- **Retry** only transient failures (connection refused / agent offline /
  upstream 5xx / timeout) — backoff `min(60·2^n, 600)` s, up to
  `max_attempts`. Deterministic rejections (4xx, bad payload, model not
  found) fail immediately — retrying won't help.
- **Idempotency:** optional `Idempotency-Key` header (or body field),
  unique per user; a duplicate submit returns the existing job instead
  of creating a second. Critical for agents that resubmit on flaky
  networks.
- **Cancellation:** `POST /v1/jobs/{id}/cancel` → `CANCELED` if `QUEUED`;
  if `PROCESSING`, mark intent and best-effort signal the worker (and,
  later, the agent — V0 may just let the in-flight job finish but not
  retry). Releases slots.
- **Timeouts:** per-job, per-modality (video > image > chat), set on the
  worker — **not** bounded by the web/gunicorn timeout since the HTTP
  request returned at submit. A timed-out job follows the retry rule.

### 5.7 Surfaces (UI & agents)

- **API:** `async: true` on any existing `/v1/*` body → `202 {job_id}`
  instead of the inline result. Plus the new job/batch/workflow
  endpoints (§6). This is the agent-facing surface.
- **Dashboard `/dashboard/queue`:** your jobs (status, modality, age,
  attempts), filter by batch/workflow, **cancel** and **retry** buttons,
  live-ish via polling. Completed media links into the existing library.
- **Playground:** additive "Queue instead of run" affordance for the
  expensive modalities (video/3D/music) so a busy box doesn't block the
  tab. Default behavior unchanged.
- **Notifications:** a poll-based "N jobs finished" badge in the
  dashboard chrome (reuses the existing session/auth poll). SSE/email
  deferred.

---

## 6. API summary (new/changed)

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `POST /v1/*` with `async: true` | Bearer/session | Enqueue instead of run inline → `202 {job_id}`. |
| `GET /v1/jobs/{id}` | owner | Job status + result (or error). |
| `POST /v1/jobs/{id}/cancel` | owner | Cancel a queued/running job. |
| `POST /v1/jobs/{id}/retry` | owner | Re-queue a `FAILED` job. |
| `POST /v1/batches` | Bearer/session | Submit a list of requests → batch + job ids. |
| `GET /v1/batches/{id}` | owner | Aggregate + per-job status/results. |
| `POST /v1/workflows/runs` | Bearer/session | Start a run from an inline spec or saved `Workflow` id + inputs. |
| `GET /v1/workflows/runs/{id}` | owner | Run status, per-step status, outputs. |
| `POST /v1/workflows/runs/{id}/steps/{step}/(approve\|reject\|edit)` | owner | Resolve a `gate` step. |
| `GET /api/queue/summary` | session | Counts for the dashboard badge. |
| `PUT /api/inference/agent/manifest/` | IsFullMember | Now accepts `max_concurrent` + `resource_groups`. |

(All `/v1/*` async endpoints honor the same auth/throttle as their sync
twins; anonymous accounts inherit PRD 08's gating unchanged.)

---

## 7. Infra & ops

- **New containers:** `celery-worker` (one or more) and `celery-beat`
  (exactly one — it owns the dispatcher tick), added to the compose
  stack and the production deploy. Both run the Django code image
  (reuse the backend image; `command` differs), so a backend code change
  requires rebuilding them too (same "compose bakes code" gotcha as the
  backend).
- **Redis** is promoted from cache-only to **broker + result backend +
  slot counters**. `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` default
  to the existing `REDIS_URL` (separate logical DB). If `REDIS_URL` is
  unset, async is disabled and `async:true` returns a clear 503 — sync
  still works.
- **Settings:** a `backend/backend/celery.py` app + `CELERY_*` config;
  beat schedule with the dispatcher tick; per-modality timeout map;
  `ASYNC_ENABLED` flag.
- **Observability:** Flower (already in the lockfile) for worker/queue
  visibility in dev; the `/dashboard/admin` activity view gains async
  counters (queued depth, running, failed/24h) for staff.
- **Graceful shutdown:** workers finish or requeue in-flight jobs on
  SIGTERM; the slot reaper handles the rest.

---

## 8. Rollout

| Milestone | Contents | Gate |
| --- | --- | --- |
| **V0 — Jobs** | Refactor proxy into a shared executor; `InferenceRequest` async/queue fields + status machine migration; Celery app + worker + beat + Redis broker; manifest `max_concurrent`/`resource_groups` + `ResourceGroup` model + slot counters; dispatcher tick; `async:true`; `GET/cancel/retry /v1/jobs`. | One async image job runs end-to-end and respects a 1-slot box. Sync path provably unchanged (existing suite green). |
| **V1 — Batches & UI** | `POST/GET /v1/batches`; `/dashboard/queue` page (list/cancel/retry); queue-instead-of-run in playground for video/3D/music; poll badge + staff async counters. | Queue 40 images against one GPU, close the tab, find them in the library. |
| **V2 — Workflows** | `Workflow`/`WorkflowRun`/`WorkflowStepRun`; spec parser + dependency engine on the dispatcher; `inference`/`map`/`transform`/`collect`/`gate` step kinds; output templating; run/step API + gate resolution; minimal run viewer UI. | The article→media example runs to completion with one human gate. |
| **V3 — Polish** | Saved workflow templates/library; cross-user fairness/priority on the queue; scheduled runs (beat cron); SSE notifications; agent-pull dispatch revisit. | As needed. |

Each milestone ships alone. V0 is invisible to most users (the queue
exists but only `async:true` callers see it); V1 makes it tangible; V2
is the headline.

---

## 9. Open questions (fine to decide at implementation)

1. **Default `max_concurrent`** when a manifest omits it — `1` (safe for
   a single-GPU box) vs. inferring from engine type (vLLM batches).
   Lean: `1`, override in the manifest.
2. **In-flight cancellation of the agent.** V0 can mark intent and skip
   retry but let the agent finish (no cancel protocol exists). Worth a
   future agent-side `DELETE /v1/jobs/{upstream_id}`? Lean: defer.
3. **Where do `transform`/`gate` outputs and large intermediate media
   live** — reuse the GCS media pipeline + `results` JSON, or a scratch
   space per run? Lean: reuse GCS + `context` JSON references.
4. **Fairness:** should one user's 500-job batch be able to starve
   another's single job on a shared community box? Priority + per-user
   round-robin in the tick (V3) vs. FIFO (V0/V1). Lean: FIFO now,
   note it.
5. **Workflow spec format** — JSON only, or YAML too (agents emit JSON
   easily; humans like YAML)? Lean: accept both, store canonical JSON.
6. **Should the dispatcher tick be beat-driven (~1–2 s polling) or
   event-driven (enqueue-next on each completion)?** Lean: both — beat
   as the heartbeat/floor, completion events to react instantly.
