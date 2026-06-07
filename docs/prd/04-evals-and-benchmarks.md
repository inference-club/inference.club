# PRD 04 — Evals & benchmarks (quality + performance)

> **Status:** Draft for review. Not yet implemented.
>
> **Author:** Brian (spec) · drafted with Claude Code.
>
> **Scope:** Make inference.club a great place to **understand how good
> and how fast a model is**, with three layers: **(A)** link out to the
> best external sources (LMArena, SemiAnalysis, Open LLM Leaderboard, …)
> per model; **(B)** surface the **performance data inference.club
> already collects** (tokens/sec, TTFT, latency) as first-class,
> hardware-aware benchmarks — our unique angle; and **(C)** let providers
> **run free/open-source quality evals** (lm-eval-harness, etc.) on
> consumer GPUs (RTX 30/40/50, DGX Spark) through their agent, upload the
> results, and have inference.club **store, aggregate, and visualize**
> them.
>
> **Explicitly out of scope (this PRD):** building a *new* benchmark
> dataset; human-preference/Arena-style pairwise voting (we *link* to
> Arena, we don't rebuild it); paid/closed eval suites; training or
> fine-tuning. We lean entirely on **free, open, runnable-on-consumer-
> hardware** evals.

---

## 1. Summary

Today a model page on inference.club tells you *who serves it* and *how
to call it*, but nothing about **how good** or **how fast** it is. Users
choosing between, say, `qwen/qwen3-30b-a3b` and `llama-3.1-8b` have no
signal beyond the name.

This PRD adds an **evals layer** with a clear division of labor:

1. **Curated external links** — every model page links to its entries on
   **LMArena**, **SemiAnalysis**, the **Hugging Face Open LLM
   Leaderboard**, **LiveBench**, **Artificial Analysis**, etc. Cheap,
   high-trust, ships first. (§4)
2. **Native performance benchmarks** — inference.club already records
   `ttft_ms`, `latency_ms`, `total_tokens` on **every real request**. We
   turn that exhaust into **tokens/sec & TTFT leaderboards sliced by
   model × engine × GPU**. *No one else has this per-real-provider,
   per-consumer-GPU data.* (§5)
3. **Provider-run quality evals** — a provider opts in; their **agent**
   runs an open eval harness (lm-evaluation-harness / lighteval) against
   one of their own served models; results upload to inference.club via
   the existing manifest/heartbeat channel; we **store, dedupe,
   aggregate across providers, and visualize**. (§6–§8)

The throughline: **quality** comes from open community/official sources
(linked or community-run harnesses); **performance** is *our* native
superpower because we already meter every call on real, diverse
hardware.

---

## 2. Current state (grounded in code)

- **Models are first-class.** `inference.CatalogModel` (one row per
  poolable model `slug`, with `hf_repo_id`, `architecture`,
  `native_context_length`, `input/output_modalities`,
  `supported_features`, `metadata` JSON). Frontend `pages/models/`
  renders these. **This is where eval data attaches.**
- **Per-deployment specifics live on `ProviderService` / `ProviderModel`**
  — `engine` (vLLM, LM Studio, …), `service_type` (llm/stt/tts/image),
  `declared_features`, `served_context_len`. So the same model on two
  GPUs/engines is distinguishable.
- **We already measure performance on real traffic.**
  `InferenceRequest` stores `latency_ms`, **`ttft_ms`**,
  `prompt_tokens` / `completion_tokens` / `total_tokens`,
  `audio_seconds`, `image_count`, `status`, plus the `provider` and
  `model_name`. **Tokens/sec = `completion_tokens / (latency_ms/1000)`;
  TTFT is stored directly.** The raw material for performance evals is
  already in the DB.
- **Providers self-register via a manifest + heartbeat.** `Provider`
  posts `POST /api/agent/heartbeat/`; a `ServiceManifest` (`raw_yaml` +
  `parsed` JSON, validated by `manifest_validator.py`) describes
  hosts/services. **This is the exact channel an agent can use to upload
  eval results** — a new manifest/heartbeat field, not a new transport.
- **We already build leaderboards.** `dashboard/leaderboard` +
  `useLeaderboard` aggregate tokens over time windows — proves the
  aggregate-and-chart pattern and gives us a component to clone.
- **Charting:** no chart lib in `frontend` yet (grep finds none) — pick
  one (§8).
- **The agent repo** (`~/git/inference-club-agent`) already runs inference
  engines locally on the provider's GPU — the natural place to *also*
  run an eval harness against `localhost`'s OpenAI endpoint.

**Implication:** evals are largely an **aggregation + presentation**
problem over data and channels we already have, plus a **new opt-in
agent job** that runs existing open-source harnesses. We are not
inventing benchmarks; we are plumbing and visualizing them.

---

## 3. Goals & non-goals

**Goals**

- Every model page answers "**how good?**" (links + community/our quality
  scores) and "**how fast, on what hardware?**" (our native perf data).
- **Performance leaderboards** sliced by **model × engine × GPU class**
  (e.g. "qwen3-30b on vLLM on an RTX 4090 → ~X tok/s, Y ms TTFT").
- A provider can run a **free, open eval** on a **consumer GPU** with a
  one-command agent job and see their model's score appear.
- Cross-provider **aggregation**: a model's MMLU/IFEval is averaged
  across everyone who ran it (with provenance), not a single claim.
- **Dynamic, honest visualizations** (charts, hardware comparisons),
  generated from stored results — with clear "community-run, unverified"
  labeling.
- Curated **outbound links** to the authoritative external sources.

**Non-goals (this PRD)**

- Rebuilding LMArena / human preference voting.
- A *verified/official* eval program (anti-cheat, sandboxed re-runs) —
  v1 is **trust-but-label**; verification is a fast-follow (§12).
- Evals for closed/hosted models we don't serve.
- Training, fine-tuning, or dataset creation.
- Paid eval compute or guaranteeing reproducibility across every GPU.

---

## 4. Layer A — Curated external links (ships first, cheapest)

Per `CatalogModel`, store a small map of authoritative external
references and render them as a tidy "Benchmarks elsewhere" panel on the
model page.

- **Sources to link** (pick the ones that have the model):
  - **LMArena** (`lmarena.ai`) — human-preference Elo. *(group "arena")*
  - **SemiAnalysis** — systems/hardware analysis & InferenceMAX-style
    perf commentary.
  - **Hugging Face Open LLM Leaderboard** — standardized academic evals
    (IFEval, BBH, MATH, GPQA, MUSR, MMLU-Pro).
  - **LiveBench** — contamination-resistant, monthly-refreshed.
  - **Artificial Analysis** — quality + **speed/price** cross-provider
    (good neighbor to our perf layer).
  - Model's **HF model card** (we already have `hf_repo_id`) and the
    org's official report/paper.
- **Data:** `CatalogModel.metadata["external_evals"] = [{source, url,
  label, group}]`. Seed via a management command that maps `hf_repo_id`/
  `slug` → known URLs; allow admin/community edits later.
- **UI:** a compact link group with source logos/badges; honest framing
  ("external sources, methodologies differ"). **No scraping** of those
  sites' data in v1 — link out, don't copy (ToS-safe and trivially
  shippable). Optional v2: pull *public APIs* where a source offers one.

This layer alone makes model pages dramatically more useful and can ship
in a day.

---

## 5. Layer B — Native performance benchmarks (our superpower)

We already TTFT/latency/token-meter **every real request**. Turn that
into hardware-aware perf benchmarks — the thing **only inference.club
can show** because we sit on real, heterogeneous provider hardware.

### 5.1 Capture GPU/hardware context (small addition)
The agent/manifest already describes services; extend it to declare the
**hardware** a service runs on so perf can be sliced by GPU:
- Add to the manifest `services[].hardware` (or `hosts[].hardware`):
  `{ gpu: "RTX 4090", gpu_count, vram_gb, gpu_arch: "Ada",
  driver, cuda, quant: "fp8"|"awq"|"gguf-q4", engine_version }`.
- Persist on `ProviderService.metadata` (or a thin `Hardware` row).
  Normalize `gpu` to a **GPU class** enum (RTX 3090, 4070, 4080, 4090,
  5090, **DGX Spark / GB10**, A100, H100, …) so we can group.
- This is the one genuinely new collection requirement; everything else
  is already stored.

### 5.2 Derived performance metrics (no new measurement)
Compute from existing `InferenceRequest` fields, per
`(catalog_model, engine, gpu_class, quant)`:
- **Decode throughput** = `completion_tokens / (latency_ms/1000)` (tok/s).
- **TTFT** = `ttft_ms` (already stored) — p50/p95.
- **Prefill throughput** ≈ `prompt_tokens / (ttft_ms/1000)`.
- **End-to-end latency** p50/p95; **STT** real-time-factor =
  `audio_seconds / (latency_ms/1000)`; **TTS** chars/sec; **image**
  sec/image.
- Roll up nightly into a `PerfStat` aggregate table (so charts are cheap
  and we don't scan raw requests live).

### 5.3 Standardized perf probe (optional, opt-in, for apples-to-apples)
Organic traffic is noisy (varied prompt lengths). For clean comparisons,
the agent can run a **synthetic throughput probe** (fixed prompt/gen
lengths, concurrency sweep) on demand — essentially what
`vllm bench`/`llm-perf`/`genai-perf` do — and upload a `PerfRun`. This
gives the canonical "RTX 4090 + vLLM + qwen3-30b-fp8 = N tok/s @ C
concurrency" numbers, reproducibly. (Reuses the §7 upload channel.)

### 5.4 Presentation
- On a **model page**: "Performance by hardware" — a bar/scatter of
  tok/s & TTFT across GPU classes & engines that serve it, from
  `PerfStat`/`PerfRun`.
- A **provider page**: this provider's measured tok/s per model.
- A **hardware page** (`/hardware/rtx-4090`): "what runs well on a 4090"
  — fits the consumer-GPU audience perfectly and is SEO gold.
- Tie into the existing leaderboard component pattern.

---

## 6. Layer C — Provider-run quality evals (open harnesses on consumer GPUs)

The interesting, communal part: let providers **run real quality evals**
on their own GPUs and contribute the scores.

### 6.1 Which harnesses (free & open, the standards)
- **EleutherAI `lm-evaluation-harness`** — the de-facto standard;
  hundreds of tasks; can target an **OpenAI-compatible endpoint**
  (`--model local-completions`/`local-chat-completions`) → points
  straight at the provider's own agent. **Primary harness.**
- **Hugging Face `lighteval`** — lighter, modern, also OpenAI-endpoint
  capable; good alternative/secondary.
- (Mention/allow later: **OpenCompass**, **DeepEval**, task-specific
  harnesses.)

### 6.2 Which tasks (curated, consumer-hardware-friendly)
Default to a **small, fast, meaningful "inference.club Core" suite** that
finishes in minutes-to-an-hour on a single consumer GPU, all
**free/open**:
- **General knowledge/reasoning:** `MMLU` (or fast `MMLU-Pro` subset),
  `ARC-Challenge`, `HellaSwag`, `WinoGrande`.
- **Math:** `GSM8K`, `MATH` (subset).
- **Instruction following:** `IFEval` (cheap, very informative).
- **Truthfulness:** `TruthfulQA`.
- **Code:** `HumanEval` / `MBPP` (small, fast).
- **Contamination-resistant (optional):** a **LiveBench** subset.
- **LLM-as-judge (optional, opt-in):** **MT-Bench**-style — needs a judge
  model; can use a strong model via the platform or a local judge.
  Flagged separate because judge choice affects scores.

Each task carries a **size/time hint** so a 3090-owner picks a suite that
fits. We ship **named presets**: `core-fast` (~10 min), `core` (~1 hr),
`full` (overnight).

### 6.3 Hardware reality (RTX 30/40/50, DGX Spark)
- Evals run **against the already-running inference server** (vLLM/LM
  Studio/etc.) over its OpenAI endpoint — the harness is just an HTTP
  client, so **eval VRAM cost ≈ 0 beyond serving the model**. A model
  that *serves* on a 4090 can be *evaluated* on a 4090.
- This is why consumer GPUs work: we're not loading a second copy; we're
  scoring the live endpoint. DGX Spark (128 GB unified, GB10) extends
  this to larger models others can't fit.
- We publish per-preset rough runtimes per GPU class so expectations are
  set.

---

## 7. Upload channel — reuse manifest/heartbeat (no new transport)

Providers already authenticate and push state via
`POST /api/agent/heartbeat/` + `ServiceManifest`. Eval/perf results ride
the same rails:

- The agent gains an **`evals run <preset> --service <name>`** command
  (and a `perf probe`) that runs the harness against `localhost`'s
  endpoint, then **POSTs a results document** to a new
  `POST /api/agent/evals/` (Bearer-authed like heartbeat).
- Results document (validated by a new schema alongside
  `manifest_validator.py`):
  ```yaml
  harness: lm-eval-harness
  harness_version: "0.4.x"
  preset: core-fast
  service: vllm-qwen3            # → maps to ProviderService
  model: qwen/qwen3-30b-a3b      # → CatalogModel.slug
  hardware: { gpu: RTX 4090, vram_gb: 24, quant: fp8, engine: vllm, engine_version: ... }
  started_at / finished_at / duration_s
  tasks:
    - { task: ifeval,  metric: prompt_level_strict_acc, value: 0.71, n: 541, stderr: 0.02 }
    - { task: gsm8k,   metric: exact_match,             value: 0.83, n: 1319 }
  raw_log_url: null              # optional pointer to full harness output
  ```
- Bind to the authenticated `Provider`/`ProviderModel` server-side so a
  provider can only post for **their own** services (mirrors existing
  heartbeat auth). Idempotent on `(provider, model, harness, preset,
  finished_at)`.

---

## 8. Data model & visualization

### 8.1 Models (new, in `apps.inference` or a small `apps.evals`)
```
EvalSuite        # static catalog of presets/tasks (mostly config/fixtures)
  key            # "core-fast" | "core" | "full" | task-level entries
  tasks          JSON  # [{task, metric, weight, time_hint}]
  harness        # lm-eval-harness | lighteval
  is_quality | is_performance

EvalRun                         # one execution by one provider
  provider        FK(Provider)
  service         FK(ProviderService, null)
  catalog_model   FK(CatalogModel)
  suite           FK(EvalSuite, null)
  harness, harness_version, preset
  hardware        JSON   # normalized gpu_class, quant, engine, versions
  started_at / finished_at / duration_s
  status          enum: RUNNING | COMPLETE | FAILED
  source          enum: PROVIDER_AGENT | INTERNAL   # who ran it
  verified        bool default False   # v1 always False ("community-run")
  raw_log_url     char null

EvalResult                      # one task metric within a run
  run             FK(EvalRun, related_name="results")
  task            char    # "ifeval"
  metric          char    # "prompt_level_strict_acc"
  value           float
  n               int null
  stderr          float null

PerfStat   (nightly aggregate over InferenceRequest — Layer B)
  catalog_model FK · engine · gpu_class · quant
  window        enum (day|week|all)
  tok_s_p50 / tok_s_p95 · ttft_ms_p50 / ttft_ms_p95 · latency_p50/p95
  sample_count
  # for STT/TTS/image: rtf / chars_s / sec_per_image columns or in metadata

PerfRun    (optional synthetic probe — §5.3, same shape as EvalRun for perf)
```
- **Aggregation/provenance:** a model's headline quality score for a task
  = average (or median) of `EvalResult.value` across `COMPLETE` runs,
  **with run count + spread + per-provider breakdown on hover**. Never a
  single anonymous number — always "averaged over N community runs."

### 8.2 Visualization (dynamic, generated by us)
- **Chart lib:** add a lightweight, SSR-friendly option — recommend
  **`unovis`** or **`Chart.js` (vue-chartjs)** (Tailwind-friendly,
  small). Pick in §11.
- **Model page → "Evals" tab:**
  - Quality: a **radar/bar** across the Core suite tasks; per-task
    average + sample count; "community-run" badge; link to per-run
    detail.
  - Performance: **tok/s & TTFT by GPU class** (Layer B) bar/scatter.
  - External: the Layer-A link panel.
- **Compare view** (`/models/compare?a=…&b=…`): two models side by side
  on the same axes — the highest-value page for decision-making.
- **Hardware page** (`/hardware/[gpu]`): leaderboard of models by tok/s
  on that GPU + which Core scores were achieved there.
- All charts read from `PerfStat`/`EvalResult` aggregates (cheap), expose
  the underlying runs for transparency, and carry a methodology
  footnote + "report a problem" link.

---

## 9. Trust, honesty & anti-gaming (v1 = label, don't police)

Community-submitted scores can be wrong or gamed. v1 stance: **be
radically transparent rather than gatekeep.**
- Every score shows **source** (which provider/agent ran it),
  **harness + version**, **hardware/quant**, **date**, **sample count**,
  and a **"community-run, unverified"** badge.
- Show **spread across runs**, not just a mean — outliers are visible.
- Quant matters: an `fp8`/`q4` run can score differently than `fp16`; we
  **always display quant** so comparisons are fair.
- Pin **harness + version + task revision** so results are reproducible
  and stale ones are flagged.
- **v2 verification (fast-follow, §12):** inference.club re-runs a random
  subset on internal/trusted hardware and stamps `verified=True` on
  agreement; divergence flags the run.

---

## 10. Open questions / decisions

1. **Chart library:** `unovis` vs `vue-chartjs` vs `ECharts`. *Lean
   `unovis` (modern, Vue-friendly) or `vue-chartjs` (simplest).*
2. **Default Core suite contents & runtime budget** — confirm the
   task list and the `core-fast`/`core`/`full` cutoffs.
3. **MT-Bench / LLM-judge:** include in v1 (needs a judge model + cost)
   or defer? *Recommend defer to v2; ship dataset-based tasks first.*
4. **Where do internal visualizations / `INTERNAL` runs execute** — do we
   stand up an inference.club eval runner (a GPU box / the agent in a
   trusted mode) for `verified` re-runs? *v2.*
5. **GPU-class normalization list** — finalize the enum (and how to
   detect DGX Spark / GB10, multi-GPU).
6. **Layer-A links:** scrape-free links only in v1 (recommended), or pull
   any source's public API (e.g. Open LLM Leaderboard) where licensing
   allows? *Links only v1.*
7. **Storage of raw harness logs** — keep (object storage) or just the
   parsed metrics? *Parsed metrics + optional external `raw_log_url`.*

---

## 11. Phasing (suggested implementation order)

- **Phase 0 — Layer A links.** `external_evals` on `CatalogModel`, seed
  command, link panel on model page. *Ships in ~a day, immediate value.*
- **Phase 1 — Layer B performance (no agent changes).** `PerfStat`
  nightly aggregate over existing `InferenceRequest`; "Performance by
  hardware" on model/provider pages; add chart lib. *Uses only data we
  already have* (GPU class initially "unknown" until §5.1 lands).
- **Phase 2 — Hardware capture.** Manifest `hardware` field + GPU-class
  normalization, so Phase-1 perf can slice by GPU. Hardware pages.
- **Phase 3 — Provider quality evals.** `apps.evals` models, upload
  endpoint + schema, agent `evals run` command wrapping
  lm-eval-harness against the local endpoint, Core presets,
  aggregation, "Evals" tab + compare view.
- **Phase 4 — Synthetic perf probe + compare polish.** `perf probe`
  agent command, `/models/compare`, methodology pages.
- **Phase 5 (separate) — Verification.** Internal re-runs, `verified`
  badge, anti-gaming.

---

## 12. Acceptance criteria (high level)

- Every `CatalogModel` page renders external-source links for the
  sources that have it; missing sources are simply absent (no broken
  links).
- `PerfStat` nightly job produces correct tok/s & TTFT p50/p95 per
  `(model, engine, gpu_class, quant)` from `InferenceRequest`, and the
  model page charts them.
- A provider can run `agent evals run core-fast --service <name>`,
  results upload, and the model's "Evals" tab shows the new scores
  **averaged with any prior runs**, with provider/hardware/quant
  provenance and a "community-run" badge.
- A provider **cannot** upload eval results for a service they don't own
  (auth enforced like heartbeat).
- The compare view puts two models on shared quality + perf axes.
- The hardware page lists models by measured tok/s on that GPU class.
- All displayed scores show harness+version, quant, sample count, date.

---

## 13. UX & framing notes

- **Be honest about methodology.** Quality numbers carry visible caveats
  (community-run, quant, harness version); we'd rather look modest and
  trustworthy than authoritative and wrong.
- **Performance is the hook for the consumer-GPU crowd** — "what tok/s
  does qwen3-30b get on *my* 4090?" is a question only we answer with
  real data; make that the hero on model/hardware pages.
- Reuse the existing leaderboard component patterns and theme; charts
  respect dark/light + i18n (per PRD 02).
- Make running an eval feel like a **contribution** ("you helped score
  this model on a 4090") — tie into provider profiles/leaderboard for
  reputation.

---

## 14. Touch list (for implementation)

**Backend (`backend/`)**
- `apps/inference` (or new `apps/evals`): `EvalSuite`, `EvalRun`,
  `EvalResult`, `PerfStat`, `PerfRun` models + migrations; aggregation
  service (`build_perf_stats`, `aggregate_model_scores`); results-upload
  schema validator (sibling to `manifest_validator.py`).
- `CatalogModel.metadata["external_evals"]` + seed management command.
- New endpoint `POST /api/agent/evals/` (Bearer auth, owner-scoped);
  read APIs `GET /api/models/<slug>/evals`, `/perf`, `/api/hardware/<gpu>`,
  `/api/models/compare`.
- Manifest extension for `services[].hardware`; persist + normalize GPU
  class; Celery beat entry for nightly `PerfStat`.

**Agent (`~/git/inference-club-agent`)**
- `evals run <preset> --service <name>` wrapping **lm-evaluation-harness**
  (`--model local-chat-completions` at `localhost`), parse → POST.
- `perf probe` synthetic throughput sweep → POST.
- Bundle Core presets (task lists + time hints); doctor check for
  harness install.

**Frontend (`frontend/`)**
- Add chart lib; `EvalsTab`, `PerfByHardwareChart`, `QualityRadar`,
  `ExternalEvalLinks`, `ModelCompare` components.
- Pages: model page "Evals" tab, `pages/models/compare.vue`,
  `pages/hardware/[gpu].vue`; provider page perf section.
- `composables/useEvals.ts`, `usePerf.ts`; i18n strings.

**Docs**
- `/docs`: "Running evals as a provider," "How we measure performance,"
  "Reading the benchmarks (methodology & caveats)."
```
