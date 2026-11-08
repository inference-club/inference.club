---
title: Use inference.club from AI agents
description: Install the inference.club skill (Claude Code, Hermes) or connect the remote MCP server, so any agent can generate images, video, music, speech and text with your API key.
category: Getting started
order: 4
---

# Use inference.club from AI agents

There are two ready-made integrations. Both authenticate with your regular API key
(**Dashboard → Settings → Token**) and both are **capacity-aware**: they send
`"async": "auto"`, so a busy GPU queues the request instead of getting overloaded, and
they wait for the job and hand back media URLs.

| | Skill + CLI | Remote MCP server |
|---|---|---|
| Best for | Agents with a shell (Claude Code, Hermes, Codex, OpenClaw…) | Clients without a shell (Claude Desktop, claude.ai, Cursor) or MCP-first agents |
| Saves files locally | Yes (`-o out.png`) | No — returns URLs |
| Install | Copy a folder | Add one URL + header |
| Lives in | `integrations/skills/inference-club/` in the repo | `https://api.inference.club/mcp` |

## Option 1 — the skill (recommended for coding agents)

The skill is a `SKILL.md` plus `ic.py`, a dependency-free Python CLI that wraps the
whole API. Each command prints one JSON object, so agents parse results reliably.

```bash
git clone https://github.com/inference-club/inference.club && cd inference.club
integrations/skills/install.sh                    # Claude Code → ~/.claude/skills/
integrations/skills/install.sh --hermes           # Hermes default profile
integrations/skills/install.sh --hermes minimal   # a specific Hermes profile
```

The installer also links the CLI as `~/.local/bin/inference-club`. Then give the agent
your key:

- **Claude Code**: `export INFERENCE_CLUB_API_KEY=...` in the shell you launch `claude` from.
- **Hermes**: add `INFERENCE_CLUB_API_KEY=...` to `~/.hermes/.env` (or the profile's `.env`).
  The skill declares it under `required_environment_variables`, so Hermes passes it to the
  terminal tool.

Self-hosting or local dev? Also set `INFERENCE_CLUB_BASE_URL` (e.g. `http://localhost:8101`).

Now just ask: *"generate an image of a lighthouse at sunset with inference club and save
it as lighthouse.png"*. You can also use the CLI yourself:

```bash
inference-club doctor                     # checks the key (masked) + connectivity
inference-club models --type image
inference-club image "a watercolor fox" -o fox.png
inference-club video "slow dolly shot through a misty forest" -o forest.mp4
inference-club music "lofi hip hop, mellow piano" --duration 60 -o song.mp3
inference-club speech "Welcome to the show." -o hello.wav
inference-club chat "Explain diffusion models in two sentences"
inference-club job 123 --wait -o out/     # resume a queued job
inference-club capacity                   # live GPU load
```

## Option 2 — the remote MCP server

`POST https://api.inference.club/mcp` speaks the Model Context Protocol (Streamable
HTTP, stateless JSON responses) with Bearer auth.

**Claude Code**

```bash
claude mcp add --transport http inference-club https://api.inference.club/mcp \
  --header "Authorization: Bearer $INFERENCE_CLUB_API_KEY"
```

**Hermes** (`config.yaml`)

```yaml
mcp_servers:
  inference-club:
    url: https://api.inference.club/mcp
    headers:
      Authorization: "Bearer ${INFERENCE_CLUB_API_KEY}"
```

**Any other client**: add a remote/HTTP MCP server with that URL and an
`Authorization: Bearer <key>` header.

Tools: `list_models`, `get_capacity`, `generate_image`, `generate_video`,
`generate_music`, `generate_speech`, `chat`, `scrape_url`, `get_job`, `list_jobs`,
`cancel_job`, `list_workflow_templates`, `run_workflow`, `get_workflow_run`.

A generation tool waits up to ~45 seconds. If the job hasn't finished by then
(typical for video), it returns `status: "QUEUED"` with a `job_id`; the agent calls
`get_job` later. Results include the media URLs as text, `structuredContent`, and MCP
`resource_link` items.

## How agents should behave

These rules are built into both integrations, and are worth following if you call the
[raw API](/docs/quickstart-agents) yourself:

::callout{type="warning" title="Real, single-GPU devices"}
Most models run on one home GPU that handles **one request at a time**
(`max_concurrent`, declared per service). inference.club enforces that budget across
every path (sync calls, jobs, workflows, the playground agent, retries), so you
can't overload a device. You *can* make the queue long, though: generate sequentially,
and use `n` (images) or a [workflow](/docs/api/workflows) for batches.
::

- Discover models with `GET /v1/models` and choose by `service_type`.
- Send `"async": "auto"`: the request runs now if a slot is free, otherwise it's queued
  (`202`, `queued_reason: at_capacity | no_provider`). Poll `poll_url` with backoff.
- Send `"delivery": "url"` to audio/video endpoints to get JSON with URLs instead of bytes.
- `429 at_capacity` means the device is busy and the request wasn't queued. Wait for
  `Retry-After`, or resend with `"async": "auto"`.
- Don't resubmit a queued request; poll its job instead.
- `GET /v1/capacity` shows live load if you want to plan ahead.

The machine-readable spec is at [`/openapi.json`](https://api.inference.club/openapi.json),
and a compact primer for LLMs is at [`/llms.txt`](/llms.txt).
