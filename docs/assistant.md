# The assistant, MCP server and skill

One set of account tools, three ways to reach it.

```
 Assistant panel (web app, text + voice) ─┐
 ic.py do "…"  (skill for shell agents) ──┼─▶ POST /v1/agent  skill: "assistant" ─┐
                                          │      (an LLM picks the tools)          │
 Claude, Hermes, Cursor … over MCP ───────┴─▶ POST /mcp  tools/call ───────────────┼─▶ tools ─▶ the app's own HTTP views
 ic.py tool NAME …                                                                 │            (same permissions as the UI)
```

## Where things live

| Piece | File |
| --- | --- |
| Account tools (library, collections, settings, services, playback, `make_song`, `api_request`) | `backend/apps/inference/control_tools.py` |
| Generation tools and the MCP endpoint | `backend/apps/inference/mcp_server.py` |
| Assistant prompt and tool wiring for `/v1/agent` | `backend/apps/inference/assistant.py` |
| The tool-calling loop | `backend/apps/inference/agent.py` |
| Web panel | `frontend/components/AssistantPanel.vue`, `frontend/stores/assistant.ts` |
| Skill and CLI | `integrations/skills/inference-club/` |
| Tests | `backend/apps/inference/tests/test_control_tools.py` |

## How a tool works

A tool is a schema plus a handler `(request, args) -> dict`. The handler calls
the same view the web app calls, in-process and as the caller
(`control_tools.internal`), so there is no second copy of any rule. It returns a
dict with:

- `summary`: one past-tense sentence saying what happened. Assistants repeat
  it, the panel shows it on the step's card, `ic.py do` returns it in `did`.
- optional `media`, `job_id` / `jobs`: results, or work still running. The
  panel follows jobs until their media lands.
- optional `client_action`: `{type: "navigate", path}` or
  `{type: "play", tracks}`. The web app carries it out; other clients use the
  URLs in the result.

## Adding a tool

1. Write the handler in `control_tools.py` using `_ok(outer, METHOD, path, body)`.
2. Add an entry to `CONTROL_TOOLS` (name, description, `inputSchema`, handler).
3. Add a label under `assistant.tools` in every locale file.
4. Add a test in `test_control_tools.py`.

It is then available over MCP, in the panel and in the CLI with no other change.

## Safety rules built in

- Tools act as the caller and go through the app's views: nothing a person
  could not do in the UI.
- `delete_item` and `delete_collection` take two calls. Inside the assistant
  the second must come in a later turn, after the person has answered.
- `api_request` cannot reach sign-in, token, registration, admin or node-agent
  endpoints, cannot write external API keys, and hides token fields in
  responses.

## Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `ASSISTANT_MAX_ITERATIONS` | 10 | Model turns per request |
| `ASSISTANT_WALL_CLOCK_SECONDS` | 240 | Time budget per request |
| `ASSISTANT_TOOL_WAIT_SECONDS` | 20 | How long a generation tool waits before handing back a job |
| `MCP_TOOL_WAIT_SECONDS` | 45 | The same, for MCP clients |
