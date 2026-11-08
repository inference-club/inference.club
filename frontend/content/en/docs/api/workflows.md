---
title: Workflows
description: Chain inference steps into a DAG with /v1/workflows — fan out, transform, gate for human review.
category: API reference
order: 13
---

# Workflows

A workflow is a **DAG of inference steps** that runs as a single, resumable unit. Each step is one job (or a dynamic fan-out of jobs) tied to the step's dependencies — the engine starts a step only when every step it depends on is done. Steps pass data to each other via `{{ steps.<id>.output... }}` templates.

Workflows run in the same job queue as individual async jobs, so they inherit capacity scheduling, retries, and durability. The live state — step statuses, edges, media thumbnails — is shown as an interactive SVG graph in **Dashboard → Queue**.

## Quick start: run a template

The easiest way to start a workflow is with a curated template. List what's available:

```bash
curl https://api.inference.club/v1/workflows/templates \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

Then start a run:

```bash
curl -X POST https://api.inference.club/v1/workflows/runs \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "template": "illustrated-story",
    "inputs": {
      "topic": "a lighthouse keeper who befriends a whale",
      "scenes": 4,
      "style": "soft watercolor, warm light"
    }
  }'
```

The server returns `202 Accepted` with the run object. Poll `GET /v1/workflows/runs/<id>` to watch it progress.

## Built-in templates

| Key | What it does | Inputs (required in **bold**) |
|---|---|---|
| `illustrated-story` | Writes a story, splits it into scenes, illustrates each, pauses for review (gate). | **`topic`**, `scenes` (1–8, default 4), `style` |
| `image-variations` | Brainstorms `count` image prompts for a subject, renders them all. | **`subject`**, `count` (1–8, default 4), `vibe` |
| `storyboard-to-video` | Plans shots, renders first frames, pauses for approval (gate), animates each into a clip. | **`concept`**, `shots` (1–5, default 3), `size` (256–1024) |
| `miniature-construction-timelapse` | Art-directs a tilt-shift "tiny workers" scene, renders the first frame, animates it. | **`subject`**, `size`, `seconds` (2–12, default 5) |
| `image-to-video` | Directs a shot from a few words (or none), renders a frame, animates it. | `subject`, `size`, `seconds` |
| `song-and-cover` | Writes lyrics + a music brief, then generates the track and cover art in parallel. | **`theme`**, `genre` (default `synthwave`) |
| `narrated-explainer` | Writes a script, narrates each line with TTS. | **`topic`**, `lines` (1–8, default 4) |
| `url-to-video` | Scrapes an article, writes a two-host dialog, voices it with Dia, cleans the audio, illustrates each section, pauses for review (gate), composes a video. | **`url`**, `style`, `voice_seed` |

Number inputs are coerced to integers and clamped to their range; omitted inputs take their defaults. `GET /v1/workflows/templates` is the source of truth.

Templates are **portable** — inference steps declare a modality (`type: image`) but omit the specific model. The engine resolves whichever model you can actually route to at run time.

## `GET /v1/workflows/templates`

Returns `{"data": [...]}` — each template's `key`, `title`, `description`, `icon`, `step_count`, and `inputs` (a list of `{name, label, type, required, default, min, max}` fields).

## `POST /v1/workflows/runs`

Start a run from a template (`template` + `inputs`) or from an inline spec (`spec`).

### From a template

```json
{
  "template": "song-and-cover",
  "inputs": {
    "theme": "late-night drive through neon city rain",
    "genre": "synthwave"
  },
  "name": "My synthwave album"
}
```

### From an inline spec

```json
{
  "name": "My custom pipeline",
  "spec": {
    "steps": [
      {
        "id": "outline",
        "kind": "inference",
        "type": "chat",
        "title": "Write blog post",
        "extract": "json",
        "body": {
          "messages": [{
            "role": "user",
            "content": "Write a 3-section blog post about {{inputs.topic}}. Return JSON: {\"sections\":[{\"title\":\"...\",\"body\":\"...\"}]}"
          }]
        }
      },
      {
        "id": "images",
        "kind": "map",
        "type": "image",
        "title": "Illustrate each section",
        "over": "{{steps.outline.output.sections}}",
        "body": { "prompt": "Blog illustration for: {{item.title}}" }
      }
    ]
  },
  "inputs": { "topic": "the future of distributed AI" }
}
```

Returns `202 Accepted` with the full run object including all step states.

Before anything is queued the engine checks that you can reach a provider for every modality the spec uses. If not, the run is rejected with `409 services_unavailable` and a `missing` list naming the absent services (e.g. `["video generation"]`).

Every step runs as a queued job, so workflow steps share the same per-device [capacity budget](/docs/services/direct-vs-async#capacity) as direct calls and other jobs.

## `GET /v1/workflows/runs`

List your runs, newest first (up to 50).

## `GET /v1/workflows/runs/<id>`

Get the full run: status, inputs, every step (with its output and the jobs it spawned), and the DAG edges.

```json
{
  "id": 5,
  "name": "My synthwave album",
  "status": "RUNNING",
  "inputs": { "theme": "late-night drive", "genre": "synthwave" },
  "error": null,
  "created_on": "2026-06-13T12:00:00Z",
  "started_at": "2026-06-13T12:00:01Z",
  "finished_at": null,
  "steps": [
    {
      "id": 31,
      "step_id": "brief",
      "kind": "inference",
      "title": "Write lyrics & brief",
      "depends_on": [],
      "status": "DONE",
      "output": { "request_id": 812, "type": "LLM", "text": "…", "music_prompt": "…", "lyrics": "…", "cover_prompt": "…" },
      "error": null,
      "jobs": [ { "id": 812, "status": "PROCESSED", "output_text": "…" } ]
    },
    {
      "id": 32,
      "step_id": "track",
      "kind": "inference",
      "title": "Generate the track",
      "depends_on": ["brief"],
      "status": "RUNNING",
      "output": null,
      "jobs": [ { "id": 813, "status": "PROCESSING", "media": [] } ]
    }
  ],
  "edges": [ { "from": "brief", "to": "track" }, { "from": "brief", "to": "cover" } ]
}
```

### Step outputs

| Step | `output` |
|---|---|
| LLM `inference` / `prompt` | `{request_id, type, text, prompt}`, plus the parsed keys when `extract: "json"` (a top-level JSON list lands in `items`). |
| Media `inference` | `{request_id, type, asset_id, url}` for the first output asset. |
| `scrape` | `{request_id, type, text, title, url, asset_id}` — `text` is the markdown. |
| `map` | A list with one of the above per item. |

Each step's `jobs` array holds the full [job objects](/docs/api/jobs), so `jobs[].media[].url` and `jobs[].output_text` work here too.

## Gate steps: human-in-the-loop

A `gate` step pauses the run and sets the run status to `AWAITING`. The step acts as a checkpoint — downstream steps only start once the gate is approved.

### Approve

```bash
curl -X POST https://api.inference.club/v1/workflows/runs/5/steps/review/approve \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

You can also pass an `edit` body to replace the gate's output (e.g. to adjust the upstream step's result before downstream steps see it):

```bash
curl -X POST https://api.inference.club/v1/workflows/runs/5/steps/review/approve \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY" \
  -H "Content-Type: application/json" \
  -d '{ "edit": { "sections": [...adjusted content...] } }'
```

### Reject

```bash
curl -X POST https://api.inference.club/v1/workflows/runs/5/steps/review/reject \
  -H "Authorization: Bearer $INFERENCE_CLUB_KEY"
```

Rejecting a gate fails the gate step; downstream steps are marked `SKIPPED` and the run ends `FAILED`. Gate actions on a step that isn't `AWAITING` return `409 conflict`.

## Re-run a step

`POST /v1/workflows/runs/<id>/steps/<step_id>/rerun` re-runs one inference, map, or prompt step (say, to re-roll an image) against the run's existing context. The step and everything downstream reset to `PENDING` and re-flow; old jobs are kept in your history.

## Step kinds

| Kind | Behavior |
|---|---|
| `inference` | Enqueues one job. Set the modality with `type` or `endpoint` (see below). The request goes in `body`. |
| `map` | Resolves `over` to a list and enqueues one job per item (fan-out). Capped at 64 items by default (`WORKFLOW_MAX_FANOUT`). |
| `prompt` | An LLM step that writes a prompt for a later step (meta-prompting). Always routes to chat. |
| `transform` | Inline data step — no job. `op`: `passthrough`, `pluck`, `split_lines`, `join`, `zip`, `split_sections`, `subtitle`, `chunk`. |
| `collect` | Gathers a `map` step's outputs (`from`) into one list. |
| `gate` | Pauses the run until a human approves or rejects. |

Step `type` values: `chat` / `llm`, `image`, `video`, `music`, `tts`, `voice` / `dia` (Dia voice cloning), `stt` / `transcribe`, `scrape`, `clean` / `enhance` (audio cleanup), and `compose` / `render` (FFmpeg video assembly, runs on the platform's own worker). Or give an `endpoint` such as `/v1/images/generations`. Steps never name a model unless you put `model` in the body — the engine picks one you can reach.

Add `response_schema` (a JSON Schema object) to an LLM step to request structured output; it implies `extract: "json"`.

## Templating

Step bodies are rendered against a **scope** object:

| Path | Value |
|---|---|
| `{{ inputs.<name> }}` | A run input field. |
| `{{ steps.<id>.output }}` | The full output of a completed step. |
| `{{ steps.<id>.output.<field> }}` | A field within that output. |
| `{{ item }}` | Inside a `map` step — the current list item. |
| `{{ index }}` | Inside a `map` step — the 0-based index. |

A template that is exactly one expression (`{{ steps.outline.output.sections }}`) resolves to the raw value (which may be a list or object). Templates embedded in a larger string stringify the value.

## LLM JSON extraction

Add `"extract": "json"` to an `inference` step with a chat model. The engine parses the LLM's text response and merges the resulting object into `steps.<id>.output`. Downstream steps can then template on `{{ steps.<id>.output.<key> }}` directly — no manual JSON parsing.

Tip: include `" Respond with ONLY valid JSON, no prose, no code fences."` in your prompt to improve reliability.

## Run statuses

| Status | Meaning |
|---|---|
| `PENDING` | Created; no step has started yet. |
| `RUNNING` | Steps are being scheduled or executed. |
| `AWAITING` | A gate step is waiting for human input and nothing else is running. |
| `DONE` | Every step is `DONE` (or `SKIPPED`). |
| `FAILED` | A step failed (or a gate was rejected) and nothing is still running or waiting. |

Steps use the same labels plus `SKIPPED` (pruned because an upstream step failed). There's no run-level cancel endpoint; cancel a run's queued jobs individually with [`POST /v1/jobs/<id>/cancel`](/docs/api/jobs).

## Saved workflows

Reusable definitions live under `/v1/workflows`: `GET`/`POST /v1/workflows` (list / create from `{name, description, spec}`), `GET`/`PATCH`/`DELETE /v1/workflows/<id>`, `POST /v1/workflows/<id>/runs` (launch with `inputs`), `POST /v1/workflows/from-template/<key>` and `POST /v1/workflows/from-run/<run_id>` (fork into an editable copy). The visual builder in the dashboard edits the same objects.

## Errors

| `type` | When | HTTP |
|---|---|---|
| `invalid_request` | Missing `spec` or `template`, or missing required inputs | 400 |
| `invalid_spec` | The spec fails DAG validation (duplicate ids, unknown step kinds, bad deps) | 400 |
| `not_found` | Run doesn't exist or doesn't belong to you | 404 |
| `conflict` | Gate or rerun action is invalid (wrong state or unknown action) | 409 |
| `services_unavailable` | You can't reach a provider for a modality the spec needs (`missing` lists them) | 409 |
| `async_disabled` | Async is not enabled on this server | 503 |
