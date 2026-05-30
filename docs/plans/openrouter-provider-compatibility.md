# OpenRouter provider compatibility

**Intent:** Use [OpenRouter's provider requirements](https://openrouter.ai/docs/guides/community/for-providers)
as guiding principles for what inference.club optimizes for — a reliable, legible,
OpenAI-compatible inference endpoint — **whether or not we ever actually list**.
Where a requirement implies a feature we don't want yet (e.g. payment), we still
capture the *principle* it encodes.

Companion to [`improvement-roadmap.md`](./improvement-roadmap.md). _Last updated: 2026-05-30._

---

## Status at a glance

| # | Requirement | Status |
|---|---|---|
| 1 | List Models endpoint | 🟡 **Partial** — catalog + metadata shipped; richer declared metadata + pricing remain |
| 2 | Payment (auto top-up / invoicing) | 🔴 **Deferred** — needs the economic model |
| 3 | Uptime monitoring & traffic routing | 🟡 **Partial** — 401 semantics done; success-rate + failover remain |
| 4 | Performance metrics | 🟡 **Partial** — TTFT + throughput captured; keep-alives + fail-fast remain |
| 5 | Auto Exacto (tool-calling) | 🔴 **Not started** — needs first-class tool support |

Legend: ✅ done · ☐ remaining.

---

## Framing: inference.club as a single aggregate provider

From OpenRouter's perspective, inference.club would be **one provider** whose
`/v1/*` endpoint is backed by a network of members' home GPUs. So OpenRouter's
per-provider reliability/perf metrics would apply to **the aggregate network**,
not any single node. That has a key consequence: to look like a good provider,
the *router* (inference.club) must paper over flaky individual nodes — failover,
busy-aware routing, and honest health accounting all become load-bearing.

This is the same direction §1 of `post-mvp-roadmap.md` already argues for.

---

## 1. List Models endpoint — 🟡 Partial

**OpenRouter requires:** a models endpoint with rich per-model metadata — `id`,
`name`, `created`, `input/output_modalities`, `quantization`, `context_length`,
`max_output_length`, `pricing` (string USD per token), `supported_sampling_parameters`,
`supported_features`, plus optional `hugging_face_id`, `description`,
`deprecation_date`, `is_ready`, `openrouter.slug`, `datacenters`.

**Done:**
- ✅ OpenRouter-format catalog endpoint `GET /api/inference/provider/models/`
  (emits `{data: [...]}`, deduped across the network).
- ✅ `ProviderModel.metadata` JSON override field (operators can refine any field).
- ✅ Heuristic derivation from the model id: `quantization` (e.g. `NVFP4→fp4`),
  `reasoning` feature, image input modality (e.g. `…-Omni…`).
- ✅ Sensible defaults: modalities, sampling params, zeroed `pricing`, `is_ready`.

**Remaining:**
- ☐ Populate real `context_length` / `max_output_length` (currently null unless
  set via `metadata`).
- ☐ A real metadata pipeline — either a dashboard UI to edit `ProviderModel.metadata`,
  or extend the manifest (agent + backend) so operators declare it in `agent.yaml`.
- ☐ `pricing` with real per-token USD values (blocked on §2).
- ☐ `deprecation_date`, `datacenters` (country codes), `hugging_face_id`,
  `openrouter.slug` support.
- ☐ Make the endpoint **public / OpenRouter-keyed** (currently `IsAuthenticated`).
- ☐ Honor `is_ready` as an operator staging control (stage-but-hide).

---

## 2. Auto top-up or invoicing (payment) — 🔴 Deferred

**OpenRouter requires:** a way to pay the provider, implying **per-token USD
pricing** per model.

**Done:**
- ✅ (principle) Per-request `prompt/completion/total_tokens` columns exist — the
  raw material to compute cost against any rate card.

**Remaining:**
- ☐ Decide the economic model (free / credits / reciprocity).
- ☐ Per-token USD `pricing` per model.
- ☐ Billing infra: collect from OpenRouter + **pay out to members**.
- ☐ Surface cost/value (from the token columns) in dashboards.

---

## 3. Uptime monitoring & traffic routing — 🟡 Partial

**OpenRouter requires:** uptime = **successful ÷ total** (excluding user errors);
routing tiers (≥95% normal, 80–94% degraded, <80% fallback). Counts against
uptime: 401, 402, 404, 500+, mid-stream errors, success-with-error-finish. Does
NOT count: 400, 413, 429, 403.

**Done:**
- ✅ **403 → 401** auth fix (`WWW-Authenticate: Bearer`) — correct auth signal and
  fixes OpenAI clients.
- ✅ Error-code alignment: oversized→413, rate limit→429, upstream fail→502,
  no-provider→404.

**Remaining:**
- ☐ Track **success rate per provider and per model** (derive from `InferenceRequest`
  using OpenRouter's taxonomy: exclude 400/413/429/403).
- ☐ **Health-aware routing tiers** (prefer healthy nodes; demote/fallback flaky).
- ☐ **Failover / retry** to another node on 5xx or mid-stream drop (today
  `_find_provider_for_model` just picks the first online node).

---

## 4. Performance metrics (TTFT & throughput) — 🟡 Partial

**OpenRouter requires/measures:** TTFT and throughput (output tokens ÷ generation
time). Guidance: early 429s under load instead of queueing; stream ASAP; SSE
keep-alive comments for slow/reasoning models.

**Done:**
- ✅ **TTFT** captured on streamed requests (`ttft_ms`).
- ✅ **Throughput** (`tokens_per_second` = completion ÷ generation time), surfaced
  on the request detail page.
- ✅ Streaming passes through as-soon-as-available (no buffering).

**Remaining:**
- ☐ **SSE keep-alive comments** during long pre-first-token waits (reasoning
  models) so upstream doesn't time out / cancel.
- ☐ **Busy / backpressure early-429s** instead of queueing.
- ☐ **Aggregate perf rollups** per provider/model (we store per-request; need
  summaries + public display).

---

## 5. Auto Exacto: tool-calling routing — 🔴 Not started

**OpenRouter requires:** for tool-calling traffic, ranks on throughput, **tool-call
success rate**, and benchmark accuracy.

**Done:** _(nothing yet — tool calls pass through but aren't a first-class concern)_

**Remaining:**
- ☐ Confirm + advertise `tools` / `json_mode` / `structured_outputs` per service
  (depends on engine; declare in metadata/manifest).
- ☐ Track **tool-call success rate** (well-formed tool responses vs errors).
- ☐ Surface it as a perf signal alongside throughput.

---

## Remaining for full compliance (the future-work list)

A single checklist of everything still needed to be a fully-compliant OpenRouter
provider, roughly ordered by leverage:

**Reliability (§3) — highest priority for "looking like a good provider"**
- ☐ Success-rate (uptime) tracking per provider/model from `InferenceRequest`.
- ☐ Health-aware routing + **failover/retry** so the aggregate endpoint hides
  individual node failures.

**Performance (§4)**
- ☐ SSE keep-alives for slow first-token (reasoning) requests.
- ☐ Fail-fast backpressure 429s under load (don't queue).
- ☐ Per-provider/model perf rollups + display.

**Models metadata (§1)**
- ☐ Real `context_length` / `max_output_length` (+ metadata editing UI or manifest
  pipeline).
- ☐ `deprecation_date`, `datacenters`, `hugging_face_id`, `openrouter.slug`.
- ☐ `is_ready` staging control.
- ☐ Make the catalog endpoint public / OpenRouter-keyed.

**Tool calling (§5)**
- ☐ First-class tool / json_mode / structured_outputs support + advertisement.
- ☐ Tool-call success-rate tracking.

**Payment (§2) — the actual gate to listing**
- ☐ Economic-model decision.
- ☐ Per-token USD pricing per model.
- ☐ Billing + member payouts.

**Operational (to actually list)**
- ☐ A stable, monitored aggregate endpoint (uptime + perf dashboards).
- ☐ Fill out OpenRouter's provider form.

Most non-payment items overlap with the **Reliability/routing**, **Observability**,
and **Usage** themes in `improvement-roadmap.md`.
