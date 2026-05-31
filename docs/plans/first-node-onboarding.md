# First-node onboarding flow

A guided "connect your first node" experience that takes a freshly-signed-in
user from zero to a live, online node with as little friction as possible.

_Last updated: 2026-05-30_

## Why

The whole value loop depends on people contributing nodes, but today the path
from signup → online node is a scavenger hunt across the docs and three
dashboard pages. A new provider has to, in order:

1. Sign in with GitHub (account auto-created — fine).
2. Detour to **Settings → Token**, click _Create_, and copy a key shown only once.
3. Open the **run-an-agent** docs in another tab.
4. Hand-edit a `docker run` with five env vars
   (`INFERENCE_CLUB_API_KEY`, `AGENT_NAME`, `AGENT_CALLBACK_URL`,
   `LLM_BASE_URL`, `LLM_MODELS`), including figuring out how to make their home
   machine reachable.
5. Switch to **Providers → My Nodes** and manually click _Refresh_, with no
   live feedback and no explanation if the node never appears.

Every one of those tab-switches and "did it work?" moments is a drop-off point.
The friction we can remove cheaply, in priority order:

- **Token is a separate manual detour** → mint/show it inline.
- **The docker command is hand-assembled** → generate it pre-filled.
- **No live feedback that the node came online** → poll and show progress.
- **Silent failure** → detect "registered but never heartbeated" and explain.

## Goals

- One linear flow, reachable from the dashboard, the My Nodes empty state, and a
  first-run nudge after signup.
- The user never leaves the flow to mint a key or copy a command.
- A live "waiting → online" indicator with the node's discovered models on success.
- A useful, specific message when a node registers but doesn't come online
  (the common real-world failure: callback unreachable / tailnet not joined).

## Non-goals (for v1)

- Auto-installing Docker or the agent.
- Auto-detecting the user's local LLM server or model list (nice later).
- Any change to the Tailscale auth-key mechanism (registration already mints one).
- Replacing the `run-an-agent` reference docs — the wizard links to them for depth.

## The flow

A 4-step stepper (full page at `/dashboard/onboarding`, also embeddable as a
modal). State is derived from existing endpoints; no schema changes for the MVP.

### Step 1 — Get your API key
- If the user has no token, show an inline **Create key** button →
  `POST /api/token/` (existing). Display once, with a copy button, and carry the
  value in component state so step 2 can inject it.
- If they already have a token (`GET /api/token/list/` returns a prefix), show
  "You already have a key (`ab12…`)" and a field to paste it, since the full
  value is never re-shown.

### Step 2 — Start the agent
A **live command builder**. Inputs (with sensible defaults) drive a `docker run`
block that updates as the user types:

| Field | Default | Notes |
|---|---|---|
| `AGENT_NAME` | `my-first-node` | unique per account |
| `LLM_BASE_URL` | `http://localhost:1234/v1` | LM Studio default |
| `LLM_MODELS` | _(empty, required)_ | comma-separated served model IDs |
| `AGENT_CALLBACK_URL` | `http://<your-ip>:8002/v1` | the hard part — see below |

- `INFERENCE_CLUB_API_KEY` is injected from step 1 automatically.
- A collapsible **"How do I make my node reachable?"** inlines the three options
  already in the docs (router port-forward, Cloudflare Tunnel, Tailscale Funnel).
- Big copy button for the assembled command.

### Step 3 — Wait for it to come online
Poll `GET /api/inference/providers/` every ~3s while this step is active and
render the derived state:

- **No matching provider yet** → "Waiting for your node to register…"
- **Provider exists, `registered_at` set, `is_online === false`** →
  "Registered — waiting for the first heartbeat…"
- **`is_online === true`** → "✅ `<name>` is online" + the discovered models as
  chips (from `provider.models`).
- **Registered but still offline after ~60s** → a troubleshooting callout:
  most likely the `AGENT_CALLBACK_URL` isn't reachable from our network or the
  node hasn't joined the tailnet. Link to the networking section + how to read
  agent logs.

`is_online` is already `last_seen_at` within a 120s window, kept fresh by the
probe sidecar, so this needs no backend work.

### Step 4 — Try it
On success, hand off to the in-app playground with the new model preselected
(`/dashboard/playground`), and show a pre-filled `curl` snippet (key + model) for
users who want to wire up their own client.

## What to build

### Frontend (the bulk of v1)
- `pages/dashboard/onboarding/index.vue` — the stepper page.
- `components/onboarding/` — `StepKey.vue`, `StepRunAgent.vue` (the live command
  builder), `StepWaitOnline.vue`, `StepTryIt.vue`.
- A small polling helper around `useProviders().fetchProviders` with
  start/stop/interval (so the wizard can poll without leaking timers).
- Entry points: replace the My Nodes empty state
  (`pages/dashboard/providers/my-nodes/index.vue:49-64`) with a "Connect your
  first node" CTA into the wizard; add a first-run nudge on the dashboard home
  for users with zero providers.

### Backend
- **None required for v1** — reuses `POST /api/token/`, `GET /api/token/list/`,
  and `GET /api/inference/providers/`. Registration and heartbeat already work.
- _Optional later:_ richer "stuck" diagnostics would need the agent to report
  whether it joined the tailnet / whether its callback was reachable; out of
  scope for v1, which infers state from `registered_at` + `is_online`.

## Phasing

- **Phase 1 — Guided wizard (MVP).** Steps 1–3, reusing existing endpoints +
  polling. Highest leverage, zero backend change. Removes the token detour and
  gives live online feedback.
- **Phase 2 — Failure intelligence + handoff.** The stuck-state troubleshooting
  callout, plus the Step 4 playground/`curl` handoff.
- **Phase 3 — Self-check (optional).** Agent reports tailnet-join + callback
  reachability so Step 3 can say exactly what's wrong instead of inferring.

## Open decisions

1. **Auto-mint the token at first GitHub login?** That would delete Step 1
   entirely. Trade-off: a token exists before the user has anywhere safe to see
   it, and we only show the full value once. Leaning: keep Step 1 but make it
   one inline click.
2. **Full page vs. modal stepper?** A page is linkable and survives refresh
   (useful while waiting on a heartbeat); a modal is lower-friction from the
   empty state. Leaning: page, openable from both CTAs.
3. **Should My Nodes auto-poll generally**, independent of the wizard? Cheap win
   that also fixes the "stale until manual refresh" complaint.
