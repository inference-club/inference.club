# PRD 14 — Playground Agent

> **Status:** V0–V2 shipped (2026-06-18). A shared, server-side chatbot **Agent**
> in the playground: a tool-calling loop running in the Django backend, reusing
> the OpenAI-compatible proxy, the existing model on the home k3s cluster
> (Nemotron Omni, which already serves OpenAI tool-calls), and the MCP-adjacent
> services already deployed there (SearXNG, browserless, Firecrawl).
>
> **Implemented:** `apps/inference/agent.py` (the loop), `agent_tools.py`
> (registry + tools), `agent_skills.py` (skills), `agent_mcp.py` (MCP client),
> `agent_views.py` (`POST /v1/agent` SSE, `GET /v1/agent/tools`,
> `POST/DELETE /v1/agent/brave-key`). Frontend: `composables/useAgent.ts` +
> `pages/dashboard/playground/agent.vue` (Agent surface with tool-call cards,
> skill picker, Brave-key dialog), linked from the main playground header.
> V0 tools: `web_search` (SearXNG), `generate_image`. V1 adds `scrape_url`,
> `browse` (browserless), `generate_video`/`music`/`voice`, and
> `web_search_brave` (per-user key on `CustomUser.brave_api_key`, migration
> 0007). V2 adds skills (researcher/artist/producer) and MCP-server tools.
> 24 agent tests green. Settings: `AGENT_*` in `backend/settings.py`.
> **Not yet wired in prod:** `AGENT_SEARXNG_URL` / `AGENT_BROWSERLESS_URL` /
> `AGENT_MCP_SERVERS` env vars must point at the cluster NodePorts over the
> tailnet for the web tools to light up.
>
> **Builds on:** the `/v1/chat/completions` proxy and `_find_provider_for_model`
> routing (the inference core), `ChatThread` persistence + the playground
> (`project_logprobs_chat_threads`), the per-modality runners reused by async
> jobs (`_RETRY_RUNNERS`, PRD 10), and PRD 08 anonymous access (guests can chat,
> `IsFullMember` gates compute/keys).
>
> **Author:** Brian (product direction) · drafted with Claude Code.

---

## 1. Summary

The playground today is a thin client over `/v1/chat/completions`: the model
answers from its own weights and nothing else. This PRD adds an **Agent** — a
shared chatbot that can *act*: search the web, read pages, and **create real
inference requests on the user's behalf** ("generate an image of a cat in a
spaceship" → an actual image in their gallery). It is a single shared feature
every signed-in user (including guests) can use, with **no cross-user state**:
the loop is stateless per `(user, thread)` and every tool runs as the requesting
user.

The whole thing runs **in-process in Django**. We do *not* stand up a separate
agent service (à la odysseus) or adopt a third-party harness. The reason is the
headline use case: a tool that creates an inference request must run *as the
user*, with their routing, quota, ownership, and visibility — which is a direct
function call in Django (reusing `_find_provider_for_model` + the modality
runners), and an awkward re-authenticating round-trip from any external service.

The agent loop itself is small: call the model with an OpenAI `tools` array; if
it returns `tool_calls`, execute them as the user, append the results, and loop
until it answers or a budget is hit. The genuinely new pieces are a **tool
registry**, a handful of **tools**, and a **streaming agent endpoint** — the
model, routing, persistence, and media handling already exist.

---

## 2. What does NOT change (load-bearing promises)

- **The sync chat path is untouched.** `/v1/chat/completions` keeps forwarding
  verbatim bodies. The Agent is a *new* endpoint (`/v1/agent`); plain playground
  chat does not route through it. Turning the Agent off loses these features and
  nothing else.
- **Tools run as the requesting user.** A tool never escalates privilege. Image
  generation, scrape, etc. create `InferenceRequest` rows owned by the user,
  routed by *their* `routing_preference`, gated by *their* rate limits, and
  surfaced in *their* gallery — identical to calling the modality directly.
- **No always-on new infrastructure.** The agent loop is Python in the existing
  web/worker process. Its tools call services that already exist: the cluster
  LLM (proxy), SearXNG / browserless / Firecrawl (already deployed in the `mcp`
  namespace), and our own `/v1/*` runners. No new daemon for V0–V2.
- **Media stays pointers, not blobs** (`project_gcs_media`): tool outputs are
  `MediaAsset` rows + URLs, never binary in the agent transcript.
- **Persistence reuses `ChatThread`.** An agent conversation is a `ChatThread`
  whose `messages` carry the extra `tool_calls` / `tool` entries. No parallel
  history model.

---

## 3. Cluster building blocks (what we already have)

Verified from `~/git/home-cluster`:

| Capability | Where | Today |
|---|---|---|
| **Tool-calling model** | `services/nemotron-omni` | vLLM `nvidia/Nemotron-3-Nano-Omni-30B-A3B` served with `--enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser nemotron_v3`. **OpenAI tool-calls already on.** Multimodal (image/video/audio in). ⚠️ `--max-model-len 10000`. |
| **Web search** | `mcp/searxng` | Keyless metasearch with a plain JSON HTTP API — `GET /search?q=…&format=json` (svc `searxng.mcp:8080`, NodePort 30808). No key, no MCP client needed. |
| **Real browser** | `mcp/browserless` | Headless Chromium over WebSocket (`ws://browserless.mcp:3000?token=…`, NodePort 30330) — clicks, forms, screenshots, PDF. The "browse" capability. |
| **Scrape** | `/v1/scrape` (Firecrawl) | URL → markdown, stored as `OUTPUT_DOC`. Already a modality + runner. |
| **Diagram canvas** | `mcp/excalidraw` | Self-hosted canvas (NodePort 30505); pairs with an excalidraw MCP server (V2). |
| **Generation** | `/v1/{images,videos,voice,music}/generations` | Image/video/voice/music modalities + per-modality runners (`_RETRY_RUNNERS`) reusable from the loop. |

**Consequence:** V0–V1 need **no MCP client at all** — SearXNG is HTTP, browserless
is WS, generation is in-process. MCP becomes a *later extensibility layer* (V2),
not a dependency. This also sidesteps the "skills need a node environment" worry:
none of these run in our app; npm-based MCP servers (if ever) run as k3s sidecars.

**The one real constraint: the 10k context window.** An agent that pastes search
results and scraped pages back into the conversation overflows fast. We design
around it from V0 (§5.4): hard-cap tool-output size, cap iterations, summarize
long pages before re-injection. The loop is model-agnostic (`_find_provider_for_model`),
so routing the agent to a larger-context model later is a config change.

---

## 4. Design

### 4.1 The agent loop (`apps/inference/agent.py` — V0)

A small, synchronous tool-calling loop:

```
messages = [system_prompt, *history, user_turn]
for step in range(MAX_ITERATIONS):
    resp = call_model(user, model, messages, tools=registry.specs(enabled))
    msg  = resp.choices[0].message
    messages.append(msg)                      # assistant turn (may carry tool_calls)
    if not msg.tool_calls:
        return msg                            # final answer
    for call in msg.tool_calls:
        result = registry.run(call.name, user, json.loads(call.arguments))
        messages.append(tool_message(call.id, result.text))   # role="tool"
        emit(tool_event(call, result))        # → SSE, for the UI
# budget exhausted → one final no-tools call to force an answer
```

- **`call_model`** resolves a provider with `_find_provider_for_model(user, model)`
  and POSTs to its `/chat/completions` over the tailnet — the same path the proxy
  uses, factored so both share it. Tool-deciding turns are **non-streaming** (we
  need the full `tool_calls` array); only the **final** answer streams.
- **Each turn records an `InferenceRequest`** (`inference_type="LLM"`) so agent
  usage shows up in dashboards/metering exactly like normal chat. Tool calls that
  generate media record their own modality `InferenceRequest` via the runner.
- The loop is **stateless**: it receives the prior `messages` (from the
  `ChatThread`) and the new user turn, and returns the updated list. No shared
  mutable state between users or requests.

### 4.2 Tool registry (`apps/inference/agent_tools.py` — V0)

One small abstraction so adding a tool is declaring it, and V1/V2 tools (and
later MCP tools) slot in without touching the loop:

```python
@dataclass
class Tool:
    name: str
    description: str
    parameters: dict          # JSON Schema (the OpenAI function "parameters")
    handler: Callable         # (user, args) -> ToolResult
    full_member_only: bool = False
    enabled_by_default: bool = True

@dataclass
class ToolResult:
    text: str                 # what the model sees (truncated to a budget)
    data: dict | None = None  # structured payload for the UI (e.g. image URLs)
```

- `registry.specs(enabled)` → the OpenAI `tools` array. `registry.run(name, user, args)`
  → `ToolResult`, with per-tool error capture (a failing tool returns an error
  string the model can react to, never crashes the loop).
- A tool's `text` is **hard-capped** (`AGENT_TOOL_OUTPUT_MAX_CHARS`) before it
  re-enters the conversation — the 10k-context guardrail.
- `full_member_only` tools are filtered out for guests (PRD 08); `enabled` lets a
  request opt into a subset.

**V0 tools:**

| Tool | Does | Backed by |
|---|---|---|
| `web_search` | top-N results (title, url, snippet) for a query | SearXNG JSON API (keyless) |
| `generate_image` | create an image from a prompt; returns asset URL(s) | new `InferenceRequest(IMAGE)` + `_rerun_image`, owned by the user |

`generate_image` is the proof of the "agent makes inference requests" thesis: it
mints a real, owned, gallery-visible image via the exact runner the image
endpoint and async jobs use — the agent gets no special path.

### 4.3 The endpoint (`POST /v1/agent` — V0)

A new view (`AgentChatView`), `IsAuthenticated` + the `inference` throttle scope
(so guests can use it, like the chat proxy). Request:

```jsonc
{
  "model": "nemotron-3-nano-omni",   // any tool-capable model the user can route to
  "messages": [...],                  // OpenAI-shape history (from the ChatThread)
  "thread_id": "<public_id>",         // optional: persist into this ChatThread
  "tools": ["web_search", "generate_image"],  // optional subset; default = all enabled
  "stream": true
}
```

Response is **SSE** with typed events (a small superset of the chat stream the
playground already parses), so the UI can show the agent's actions live:

- `tool_call`  — `{ id, name, arguments }` (the model decided to call a tool)
- `tool_result`— `{ id, name, summary, data }` (e.g. image URLs to render inline)
- `token`      — `{ delta }` (final-answer text, streamed)
- `error`      — `{ message }`
- `done`       — `{ usage, thread_id, message }` (final assembled assistant msg)

### 4.4 Guardrails (the 10k-context reality — V0)

All as settings with sane defaults:

- `AGENT_MAX_ITERATIONS` (default **6**) — tool rounds before forcing an answer.
- `AGENT_TOOL_OUTPUT_MAX_CHARS` (default **4000**) — per tool result, truncated
  with an explicit "…(truncated)" marker.
- `AGENT_MAX_SEARCH_RESULTS` (default **5**).
- A coarse **context budget**: before each model call, if the running message
  size approaches the model's window, drop/condense the oldest tool results
  (keep the user turns and the latest results).
- `AGENT_WALL_CLOCK_SECONDS` — overall loop timeout.

### 4.5 Persistence

The conversation is a `ChatThread` (reused). `messages` gains the standard
OpenAI agent entries: assistant messages with a `tool_calls` array, and
`role:"tool"` messages with `tool_call_id` + content. `recompute_stats()` already
tolerates extra roles (it only sums assistant `usage`). The UI renders `tool`
entries and assistant `tool_calls` as collapsible "Agent used X" cards. AI
titling (`generate_thread_title`) works unchanged.

### 4.6 Frontend (V0)

The playground gets an **Agent** mode toggle (alongside plain chat). A
`useAgent` composable streams `/v1/agent`, routes the typed SSE events, and the
chat view renders:

- streamed final answer (same renderer as chat),
- collapsible **tool-call cards** ("🔎 web_search: cats in space" → results;
  "🖼 generate_image" → inline image), and
- reuses `ModelPicker` + `ChatThread` save/restore.

Plain chat stays exactly as is.

---

## 5. API surface (incremental)

| Endpoint | Phase | Purpose |
|---|---|---|
| `POST /v1/agent` | V0 | run the agent loop; SSE tool + token events |
| `GET /v1/agent/tools` | V0 | list available tools for the user (UI affordances) |
| `POST /api/inference/account/brave-key` | V1 | store the user's Brave key (encrypted, `IsFullMember`) |

(Agent conversations reuse the existing `/api/inference/threads/` CRUD.)

---

## 6. Rollout

| Phase | Headline | Gate / proof of success |
|---|---|---|
| **V0** | Loop + registry + `web_search` + `generate_image` + `/v1/agent` SSE + playground Agent mode | In the playground, "search the web for X and make an image of it" runs a tool round and returns an answer + an owned image; conversation saved as a `ChatThread`. Well tested. |
| **V1** | More tools + Brave + UI polish: `scrape`, `browse` (browserless), `generate_video`/`voice`/`music`; `web_search_brave` (per-user encrypted key, `IsFullMember`); polished tool cards | The agent can read a page, drive a browser, and create any media modality; a full member can opt into Brave search with their own key. |
| **V2** | Skills + MCP: a lightweight **skills** layer (markdown instruction fragments + tool subsets, pure Python) and an **MCP client adapter** so external MCP servers register as registry tools (excalidraw) | A skill switches the agent's system prompt + tool subset; an MCP server's tools appear in the registry and work end-to-end. |

> **Explicitly out of scope (for now):** sandboxed code execution. Considered and
> deferred — revisit later as an ephemeral-k3s-Job tool if wanted.

---

## 7. Infra & ops

- **Reachability**: the Django box reaches the cluster over the tailnet (the proxy
  already does, `verify=False`, `_tailnet_proxies()`). The agent's tools reach
  SearXNG/browserless the same way, via their NodePorts on a1 — configured by
  settings (`AGENT_SEARXNG_URL`, `AGENT_BROWSERLESS_WS` + token). No new ingress.
- **Settings**: tool toggles + the guardrail caps in §4.4; service URLs/secrets via
  env. The Agent is gated by an `AGENT_ENABLED` flag (default on where a tool model
  is routable).
- **Tool model**: defaults to a tool-capable served model (Nemotron Omni). If the
  user picks a model the cluster serves without a tool parser, the loop degrades
  gracefully to a no-tools answer.
- **Metering**: every model turn and every media tool is an `InferenceRequest`, so
  existing dashboards/limits cover agent usage with no new accounting.

---

## 8. Open questions

1. **Streaming + tool calls**: V0 streams only the final answer (tool-deciding
   turns buffered). Word-level streaming of intermediate "thinking" turns is a
   later polish — revisit if the UX needs it.
2. **Context strategy at 10k**: start with truncate + drop-oldest (§4.4); if real
   tasks routinely overflow, add a summarize-tool-output sub-call or route the
   agent to a larger-context model.
3. **Tool authorization granularity**: V0 gates by `full_member_only`; per-tool
   user opt-in/out (a settings page) may be wanted once there are many tools.
4. **MCP transport** (V2): in-process MCP client speaking to in-cluster MCP
   servers over the tailnet vs. running MCP servers as sidecars — decide at V2.
5. **Brave key storage** (V1): a dedicated encrypted field on the user vs. a
   generic per-user secrets store reusable by future tools.
