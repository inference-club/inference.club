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

| Key | What it does |
|---|---|
| `illustrated-story` | Writes a story, splits it into scenes, illustrates each, pauses for review. |
| `image-variations` | Brainstorms `n` image prompts for a subject, renders them all. |
| `storyboard-to-video` | Plans shots, illustrates first frames (gate), animates each into a video. |
| `song-and-cover` | Writes lyrics + music brief, then generates the track and cover art in parallel. |
| `narrated-explainer` | Writes a script, narrates each line with TTS in parallel. |

Templates are **portable** — inference steps declare a modality (`type: image`) but omit the specific model. The engine resolves whichever model you can actually route to at run time.

## `GET /v1/workflows/templates`

Returns all curated templates with their input schemas and step counts. The frontend renders the `inputs` array into a dynamic form.

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

## `GET /v1/workflows/runs`

List your runs, newest first (up to 50).

## `GET /v1/workflows/runs/<id>`

Get the full run: status, context (accumulated outputs), and every step with its status, output, and linked jobs.

```json
{
  "id": "5",
  "name": "My synthwave album",
  "status": "RUNNING",
  "steps": [
    {
      "step_id": "brief",
      "kind": "inference",
      "title": "Write lyrics & brief",
      "status": "DONE",
      "output": { "music_prompt": "...", "lyrics": "...", "cover_prompt": "..." }
    },
    {
      "step_id": "track",
      "kind": "inference",
      "title": "Generate the track",
      "status": "RUNNING"
    },
    {
      "step_id": "cover",
      "kind": "inference",
      "title": "Generate cover art",
      "status": "RUNNING"
    }
  ]
}
```

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

Rejecting a gate fails the gate step and cancels all downstream steps.

## Step kinds

| Kind | Behavior |
|---|---|
| `inference` | Enqueues one job. Accepts `type` (modality) or `endpoint`. |
| `map` | Resolves `over` to a list, enqueues one job per item (fan-out). Capped at `WORKFLOW_MAX_FANOUT` items. |
| `transform` | Inline data step — no job. Operations: `passthrough`, `pluck`, `split_lines`, `join`. |
| `collect` | Gathers all outputs from a `map` step into one list. |
| `gate` | Pauses the run until a human approves or rejects. |

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
| `RUNNING` | Steps are being scheduled or executed. |
| `AWAITING` | A gate step is waiting for human input. No inference steps are running. |
| `DONE` | All steps completed (or were skipped due to upstream failure). |
| `FAILED` | At least one non-skipped step failed and no steps are still running. |
| `CANCELED` | Canceled by the caller. |

## Errors

| `type` | When | HTTP |
|---|---|---|
| `invalid_request` | Missing `spec` or `template`, or missing required inputs | 400 |
| `invalid_spec` | The spec fails DAG validation (duplicate ids, unknown step kinds, bad deps) | 400 |
| `not_found` | Run or step doesn't exist, or doesn't belong to you | 404 |
| `conflict` | Gate action is invalid (wrong state or unknown action) | 409 |
| `async_disabled` | Async is not enabled on this server | 503 |
