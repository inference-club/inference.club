# PRD 11 — Workflow Studio: authoring, meta-prompting & multimodal compositing

> **Status:** V0 + V1 implemented (2026-06-14) — backend + frontend. V2–V4 are
> roadmap. Builds directly on PRD 10 (async jobs, batches, DAG engine). PRD 10
> gave us an engine that can *run* a graph of inference steps; PRD 11 gives
> users the ability to *author* those graphs, to use an LLM to write and edit
> them, and extends the node vocabulary from "generate assets" to "edit and
> assemble finished media."
>
> **V0+V1 implementation (keep in sync):**
> - backend (no migration — authoring data lives in the existing
>   `Workflow.spec` JSONField; `spec.layout`/`spec.inputs` are engine-ignored):
>   `Workflow` CRUD + run-saved + `from-template`/`from-run` fork +
>   single-step `rerun` in `job_views.py`; `workflows.validate_spec_shape`
>   (permissive draft save), `prompt` step kind + `_prompt_body` presets,
>   `_maybe_structured` (`response_schema` → `response_format` passthrough),
>   `rerun_step` (re-roll + downstream re-flow, detaches old jobs);
>   `workflow_templates.clean_inputs` shared helper. URLs in `openai_urls.py`
>   (rerun path precedes the generic gate `<action>`). Serializers
>   `WorkflowSerializer`/`WorkflowListSerializer`. Tests:
>   `tests/test_workflow_authoring.py` (15).
> - frontend: `components/workflow/WorkflowBuilder.vue` (editable Vue Flow
>   canvas, palette, inspector, validation, save/run), `builder/BuilderNode.vue`,
>   `builder/NodeInspector.vue` (per-kind forms, meta-prompting, response_schema,
>   `{{ }}` insert chips); `composables/useWorkflowSpec.ts` (spec⇆graph + client
>   validation); authoring API in `composables/useAsyncJobs.ts`; pages
>   `/dashboard/workflows` (library), `/new`, `/[id]/edit`; single-step re-run +
>   "Save as workflow" fork on the run page; nav + i18n (`workflows.*`).
>
> **Author:** Brian (product direction) · drafted & implemented with Claude Code.

---

## 1. Why

PRD 10 shipped a production-grade DAG engine, but the user-facing surface is
narrow:

- Workflows can only be **launched from 6 curated templates** via a form. The
  `Workflow` model already carries a user-owned `spec` JSONField — **the data
  layer for "save your own workflow" exists, but there is no create/edit
  endpoint and no builder UI.** The Vue Flow canvas (`WorkflowGraph.vue`) is
  read-only.
- The node vocabulary (`inference`/`map`/`transform`/`collect`/`gate`) can
  **generate** assets but cannot **assemble** them. You can produce a voiceover,
  four images, and a video clip — but nothing in the graph stitches them into a
  single captioned, scored, finished video. That final "editing" step is the
  whole point of a media tool, and it's missing.
- Prompting is implicit. The `illustrated-story` template uses an LLM to outline
  and then fans out image generation — that *is* meta-prompting — but it's baked
  into a template. Users can't compose "use a model to write the prompts for the
  next step" themselves, and there's no structured contract so downstream steps
  consume an LLM's output reliably.

The goal of PRD 11 is to turn Workflows from a **gallery of fixed recipes** into
a **studio**: design your own graph (by hand or by describing it to an LLM),
use models to write prompts for other models, and assemble multi-modal assets
into finished media — voice + image + video + 3D + animated subtitles.

### Enablers we already have
- **Vue Flow + dagre** are installed and rendering the DAG — we extend the
  existing canvas to be editable rather than adopting a new library.
- **`Workflow.spec` JSONField + portable templating** — saving a graph is mostly
  a serialize-the-canvas-to-spec problem; the engine already runs arbitrary specs.
- **STT with word-level timestamps already ships** (`timestamp_granularities:
  ["word"]` → `words: [{word, start, end}]`). Animated subtitles are an
  assembly problem, not a new model.
- **Content sharing** (visibility/stars/collections, PRD 01) — publishing and
  forking workflows can reuse it rather than reinventing it.
- **An LLM is one of our own modalities** — "describe a workflow → spec" and
  "edit this workflow" are just schema-constrained inference calls against the
  platform itself.

---

## 2. Principles

1. **The spec is the source of truth.** The builder, the AI author, and the
   templates all produce the same validated `spec` JSON the PRD 10 engine
   already runs. We never fork the execution path.
2. **Author once, run many.** A saved `Workflow` is a reusable, parameterized,
   shareable artifact — versioned, forkable, runnable with different inputs.
3. **Portable by default.** Steps keep omitting concrete models where possible
   (`auto_model_for`), so a workflow authored on one person's cluster runs on
   another's.
4. **Generation and editing are the same graph.** A "render" node is just
   another step kind; finished video is just another asset in the run context.
5. **Validate early, fail legibly.** Every new capability ships with spec
   validation and node-level error surfacing, not silent breakage at runtime.
6. **Async-first, capacity-aware.** New heavy nodes (render, transcribe) go
   through the same queue + resource-group gating as inference.

---

## 3. Roadmap at a glance

| Phase | Theme | Headline deliverable |
|------|-------|----------------------|
| **V0** | Authoring foundations | Editable Vue Flow builder + `Workflow` CRUD; save/fork/run your own graph |
| **V1** | Better nodes & meta-prompting | Node inspector, structured-output LLM contracts, dedicated **Prompt** node, single-node re-run, node logs |
| **V2** | AI workflow authoring | "Describe → workflow" and "Edit with AI" — schema-constrained spec generation |
| **V3** | Multimodal compositing | New node kinds: `transcribe`, `subtitle`, `compose`/`render`, `concat`/`overlay`/`mix`; file-input modalities enter workflows; finished video out |
| **V4** | Library, sharing & triggers | Publish/fork gallery, versioning, scheduled & webhook-triggered runs, cost/capacity preview, run analytics |

Each phase is independently shippable and useful on its own.

---

## 4. V0 — Authoring foundations (Workflow Builder MVP)

**Outcome:** a user can open a blank canvas (or fork a template/past run), drag
in nodes, connect them, fill in each node's config, validate, and **save it as
their own named workflow** — then run it with inputs, repeatedly.

### Backend
- **`Workflow` CRUD API** — `GET/POST /v1/workflows`, `GET/PUT/PATCH/DELETE
  /v1/workflows/<id>`. POST/PUT bodies carry `{name, description, spec, inputs_schema}`
  and run through the existing `validate_spec()` plus a new **`inputs_schema`**
  validator (the form-field descriptors templates already use).
- **Spec ⇆ graph contract** — formalize the node/edge shape the frontend
  serializes: `steps[]` already encode `depends_on` (edges) and per-kind config;
  add optional `position {x,y}` per step so a saved layout round-trips. The
  engine ignores `position`; the builder reads it.
- **Fork helpers** — `POST /v1/workflows/from-template/<key>` and
  `POST /v1/workflows/from-run/<run_id>` materialize an editable `Workflow` the
  user owns. Templates become *starting points*, not dead ends.
- **Run a saved workflow** — `POST /v1/workflows/<id>/runs` (sibling of the
  existing `/v1/workflows/runs`), snapshotting the saved spec exactly as today.

### Frontend
- **Editable canvas** — extend `WorkflowGraph.vue` (or split out a
  `WorkflowBuilder.vue`) for add/connect/move/delete. Vue Flow already supports
  connection handles, drag, and selection — we enable them and wire change
  events to a local `spec` store.
- **Node palette** — a sidebar to drag in the existing kinds; each new node
  seeds a valid default config.
- **Node inspector panel** — selecting a node opens a form bound to its config
  (modality/type, model override or "auto", prompt/body fields, fan-out source,
  transform op, gate label). This is the same dynamic-form machinery
  `TemplateLauncher.vue` already builds from input schemas, repointed at a step.
- **Inline validation** — call the validator on edit; mark offending nodes/edges
  (missing deps, cycles, unresolved `{{ }}` references) before save/run.
- **`/dashboard/workflows`** — a "my workflows" list (saved graphs) distinct
  from `/dashboard/queue` (runs). Save / Save as / Fork / Run.

**V0 risk:** keeping builder output and hand-written template specs identical so
both validate and run through one path. Mitigation: a single shared
`spec_schema` (JSON Schema) used by both the API validator and the frontend.

---

## 5. V1 — Better nodes & meta-prompting

**Outcome:** nodes are richer to configure and debug, and "use a model to write
the input for another model" becomes a first-class, reliable pattern.

- **Structured-output LLM contracts.** Let an `inference`/LLM step declare a
  `response_schema` (JSON Schema). The engine requests structured output and
  publishes a typed object into the run context, so a downstream `map` can fan
  out over `{{ steps.plan.output.scenes }}` without brittle line-splitting.
  (Today `illustrated-story` leans on `split_lines`; this makes it robust.)
- **Dedicated `prompt` node (meta-prompting).** A purpose-built node that takes
  a user's seed/brief + a system "prompt-writer" preset and emits one prompt
  (or, with fan-out, N prompts) shaped for a target modality. Ships with presets
  (cinematic image, SFX-rich music brief, narration script) and is the
  on-ramp to meta-prompting without hand-wiring an LLM step.
- **Variable & reference helper.** Inspector autocomplete for `{{ steps.* }}` /
  `{{ inputs.* }}` / `{{ item.* }}` paths, so templating is discoverable instead
  of memorized.
- **Single-node re-run & pinning.** Re-run one step against the existing context
  (re-roll an image without re-running the whole graph); pin an upstream output
  so iterating downstream is cheap. Backend already isolates step execution —
  this is a targeted `advance`/`_start_step` entry point.
- **Node logs & error inspector.** Per-step request/response/timing surfaced in
  the node detail drawer; structured `error.kind` already exists on jobs.
- **Conditional gate / branch.** Extend `gate` with an optional predicate so a
  graph can route (e.g. "regenerate if quality LLM-judge score < 7") — reusing
  the human-gate plumbing for an automated decision.

---

## 6. V2 — AI workflow authoring

**Outcome:** the workflow itself can be written and edited by an LLM — the
graph-level expression of meta-prompting.

- **Describe → workflow.** A prompt box ("a faceless-narrator short: script →
  voiceover → b-roll images → animate → captions → final cut") calls an LLM with
  the `spec_schema` as a structured-output contract and the node catalog as
  context. Output is validated, laid out (dagre), and dropped onto the builder
  canvas for review — never auto-run.
- **Edit with AI.** Natural-language edits against an existing graph ("add a
  music bed and a 3-second title card") returned as a spec diff, previewed as
  highlighted node/edge changes before apply.
- **Explain & suggest.** "What does this workflow do?" and inline next-node
  suggestions ("you generated clips but never assemble them — add a `compose`
  node?").
- **Guardrails.** All AI output passes the same validator as hand authoring;
  invalid specs are repaired-or-rejected, not run. This is why V0's shared schema
  matters.

---

## 7. V3 — Multimodal compositing (the new frontier)

**Outcome:** the library expands from *generating* assets to *editing and
assembling* them — combining voice, image, video, 3D, and **animated subtitles**
into a finished deliverable. This is the largest engineering lift.

### Bring file-input modalities into workflows
PRD 10 left STT / MESH / VOICE / image-edits synchronous. V3 lets them run as
workflow steps that consume upstream **assets** (not just JSON), generalizing the
existing `_maybe_attach_image` asset-materialization trick into a reusable
"feed upstream asset into this step's input" mechanism.

### New node kinds
- **`transcribe`** — STT over an upstream audio/video asset → `words[]` with
  start/end (the timestamp feature already ships) + plain transcript.
- **`subtitle`** — turn `words[]` into a subtitle asset: SRT/VTT, or a styled
  **animated** caption track (karaoke word-highlight, pop-on). Driven by a Python
  captioning/`ffmpeg`+ASS path; this is the "animated subtitles" you asked for,
  and it's an assembly step, not a new model.
- **`compose` / `render`** — the keystone. A timeline/layer node: stack video +
  image + audio + subtitle tracks with positions, durations, and transitions,
  and render one output video. Backed by a new **render worker** (ffmpeg, or an
  HTML/▶ HyperFrames-style compositor) exposed as a new `service_type: render`
  so it queues and capacity-gates like any modality.
- **`concat` / `overlay` / `mix`** — lighter assembly primitives (join clips,
  picture-in-picture / watermark, duck-and-mix an audio bed under narration) for
  graphs that don't need the full timeline.

### Worker & infra
- A **render/edit service** in the home cluster (or a dedicated container)
  advertising `service_type: render` in its manifest with `max_concurrent` /
  `resource_group`, so the PRD 10 dispatcher schedules it unchanged.
- Asset I/O reuses the existing GCS media pipeline (PRD: GCS media).

### Example end-to-end graph this unlocks
`brief → (prompt node) script → voiceover (TTS/voice-clone) →
transcribe → animated subtitle → b-roll images (map) → image-to-video (map) →
compose(video tracks + subtitles + music bed) → finished .mp4`

— authored visually, or by describing it to the V2 AI author.

---

## 8. V4 — Library, sharing & triggers

**Outcome:** workflows become a living, shared, automatable catalog. Folds in the
items PRD 10 explicitly deferred to "V3+".

- **Publish & fork gallery.** Reuse content-sharing (visibility/stars/
  collections) so users publish workflows, browse a community gallery, and fork
  any public workflow into their own builder. The curated templates become the
  seed of this gallery.
- **Versioning.** Saving edits creates immutable versions (the engine already
  snapshots spec per run); show a version history and "restore".
- **Scheduled & triggered runs.** Cron-scheduled runs and webhook/API triggers
  (PRD 10 §9 deferred). "Every morning, generate today's illustrated digest."
- **Cost & capacity preview.** Before running, estimate node count / fan-out
  size / queue depth and warn on big fan-outs (`WORKFLOW_MAX_FANOUT`).
- **Run analytics.** Per-workflow success rate, median duration, spend — closing
  the loop for authors iterating on their graphs.
- **SSE/live updates.** Replace polling on the run page (PRD 10 deferred).

---

## 9. Open questions / decisions to make

- **Render engine:** ffmpeg-filtergraph (fast, server-native, harder timelines)
  vs. an HTML/HyperFrames-style compositor (expressive animated captions &
  transitions, heavier render). Could support both behind the `render`
  service_type. **Recommendation: start ffmpeg+ASS for subtitles/concat/mix in
  V3, evaluate HTML compositor for richer motion.**
- **Builder scope creep:** how much timeline UI lives in the node graph vs. a
  dedicated timeline editor for `compose` nodes. Likely a sub-editor opened from
  a compose node's inspector.
- **AI-author safety:** rate limits / cost ceilings on "describe → workflow"
  since it can fan out large graphs.
- **Versioning model:** new `WorkflowVersion` rows vs. spec history on
  `Workflow`. Lean to a lightweight version table.

---

## 10. Suggested sequencing & quick wins

The highest-leverage first move is **V0 + the structured-output and Prompt-node
slices of V1**, because:
1. The data model (`Workflow.spec`) and the engine already exist — V0 is mostly
   UI + thin CRUD, not new infrastructure.
2. It immediately delivers "design / edit / save your own workflow," your
   primary ask.
3. It unblocks V2 (AI authoring needs the builder canvas + shared schema as the
   target) and V3 (new node kinds need an editor to place them).

V3 (compositing) is the marquee capability but the heaviest — it needs a new
render worker. Recommend it directly after V0/V1 so the studio has something
visually impressive to assemble, with V2 (AI authoring) landing in parallel
since it's mostly prompt + schema work on top of V0.
