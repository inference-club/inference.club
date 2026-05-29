# Post-MVP roadmap

The MVP works end-to-end: a user signs in with GitHub, mints a token,
runs `inference-club-agent` on their LAN against a local LLM, and uses
the same token to drive `api.inference.club` from any OpenAI-style
client. Before piling on more features, this doc steps back and lays
out the questions that need answers before the project can credibly
ship to anyone other than the author.

This plan is deliberately strategic, not a ticket list — `BACKLOG.md`
already holds the granular items. Read this first to decide *which
direction* to push, then pick tickets out of `BACKLOG.md` to execute.

---

## 0. Where we are right now

**One sentence:** inference.club is a single-tenant proxy in front of
self-hosted agents, with a clean OpenAI-compatible surface, a service
manifest as the operator's source of truth, and a Tailscale-based
transport that sidesteps NAT.

**What works:**
- GitHub OAuth → DRF token → Bearer auth on `/v1/*`
- Agent register flow that mints a Tailscale auth key per provider
- Service manifest (YAML) with server-side validation, mirrored into
  `ProviderModel` rows
- `GET /v1/models`, `POST /v1/chat/completions`, `POST /v1/completions`
  with SSE pass-through
- A separate `prober` sidecar in prod compose for liveness
- Public profile at `/{username}` reading manifests
- Pulumi → Hetzner → Caddy + compose deploy, image build via GHCR

**What's load-bearing but fragile** (the rest of this doc unpacks each):
1. Routing assumes "this user's providers serve this user's requests"
   — the marketplace pivot breaks every assumption in `_find_provider_for_model`.
2. The agent perimeter relies on Tailscale ACLs, not request-level auth.
3. Token model: one DRF token per user does double duty as agent
   identity *and* consumer credential — fine for one user, painful at scale.
4. Test coverage is thin (a handful of pytest cases on inference views
   and manifest sync; zero frontend tests).
5. No rate limiting, no quotas, no per-request cost accounting.
6. Observability is `docker logs` + Sentry; no per-request log surface
   for the dashboard.

---

## 1. Architecture: from "my providers, my requests" to a network

The single biggest unspoken assumption in the current code is in
`_find_provider_for_model` (`backend/apps/inference/openai_views.py:37`):
the consumer's providers and the request's possible routes are the
same set. That's correct for the MVP and wrong for the marketplace.

### 1.1 Decouple "who calls" from "who serves"

Today the proxy filters by `provider__user=user`. The marketplace
version needs:

- A **request identity** (the API key on `/v1/*`) that carries
  consumer-side context: who's spending, what budget, what allowlist,
  what privacy preferences.
- A **provider eligibility set** computed from network state: which
  providers serve this model, which are online, which have spare
  capacity, which the consumer has opted into (or opted out of).
- A **routing policy** that picks one. Even a stupid first version
  ("random eligible provider, no fallback") is conceptually right; the
  important step is moving the filter out of the queryset and into
  a routing layer that can grow.

**Concrete shape:**
- New `Route` (or `RoutingDecision`) record per request capturing
  consumer, model, candidate set size, chosen provider, reason
  (`only_eligible`, `lowest_load`, `consumer_preference`, etc.). This
  is also where failover retries get logged.
- A `ProviderVisibility` notion on `Provider` — `private` (today's
  behavior, owner only), `unlisted` (reachable by token but not in
  public listings), `public` (in the marketplace). Default to `private`
  so nothing changes for existing users.
- Consumer-side: a `ConsumerPreferences` blob (allow/deny providers,
  allow/deny GPU vendors, max price per million tokens, require
  no-logging, etc.). Can start as JSON on the user.

### 1.2 Money / accounting — design for it now even if dormant

Don't ship billing yet, but the data model should already record what
billing will need: `InferenceRequest` should carry `prompt_tokens`,
`completion_tokens`, `total_tokens`, `unit_price_in`, `unit_price_out`,
and `cost_credits`. Today only `latency_ms` is populated. Token counts
are in every OpenAI response — capture them now, decide pricing later.

A `CreditLedger` table (append-only: type, user, provider, amount,
request_id, reason) is the right primitive for both consumer spend
and provider earnings without committing to a payment processor.

### 1.3 Make the manifest the canonical "what does this provider sell"

The manifest already declares engines and models. Extend it (schema
v2) with the OpenRouter-shaped per-model metadata: `quantization`,
`context_length`, `max_output_length`, `supported_features`,
`supported_sampling_parameters`, optional `pricing`. This is a one-time
upfront cost that pays off three times: it powers a richer
`/v1/models`, it's exactly the shape an OpenRouter integration would
need, and it makes the public profile interesting to look at.

Keep schema v1 working — validator fan-out, not replacement.

---

## 2. Security

Two perimeters need to be distinguished and hardened independently:

### 2.1 The public API (`api.inference.club`)

- **Rate limiting per token**, sliding window. DRF's throttling
  is enough to start; cap at e.g. 60 req/min and 10 concurrent
  streaming connections per token. Tunable per-key once we have a
  reason.
- **Token rotation + scopes.** Replace the single DRF token with
  scoped tokens (`agent`, `consumer`) so a compromised consumer key
  can't re-register an agent and a compromised agent key can't drain
  the user's credits. Both can still be the same user; the *token*
  carries scope.
- **Custom prefix** (`ic-prov-...`, `ic-cons-...`) so leaks are easy
  to spot in logs and so future tooling can detect-and-revoke.
- **Audit log on token mint/revoke** with IP + UA. Visible in
  dashboard.
- **Secret rotation runbook.** Hetzner API token, GitHub OAuth
  client secret, Tailscale OAuth secret, Sentry DSN — write down what
  to rotate and how, so it's a 30-minute job not a research project.
- **CSP, HSTS, secure cookies** in Django settings (called out in
  `BACKLOG.md` already; tracked here as part of the security epic).

### 2.2 The home perimeter (consumer → user's LAN)

This is the part that should make us nervous, and the one we owe
users a clear story on before opening signups.

The current model: the agent joins our tailnet, the backend reaches
the agent over Tailscale, the agent forwards to the user's local
LLM server (vLLM/Ollama/LM Studio). Anything inside the tailnet
that knows the agent's hostname can call its `/v1/*` directly with no
auth. ACLs are the only fence.

**Hardening, in order of impact:**

1. **Per-agent shared secret** — the backend mints it at
   `/agent/register/`, the agent stores it, and the backend signs every
   proxied request with it (HMAC over method+path+body+timestamp,
   short window to defeat replay). Closes the "rogue tailnet member"
   gap without changing the transport.
2. **Egress allowlist on the agent side** — agent only accepts traffic
   from the inference.club tailnet, only forwards to the configured
   local URL, never to the public internet. Make it a default in the
   agent config and document why.
3. **Documented threat model** — a one-page doc with diagrams: what
   the agent exposes, what tailnet ACLs already block, what the
   shared-secret check adds, what's *still* possible (an attacker who
   compromises inference.club's own infra can issue requests to any
   provider). Users deserve this before handing us network access.
4. **Optional push mode** for users who can't or won't run Tailscale
   — agent holds a websocket to backend, requests come back over it.
   Ship later; flag it in the threat-model doc as "the path forward
   for users behind hostile NAT."
5. **Manifest-declared model allowlist** — only models the operator
   actually published in their manifest can be called via the proxy.
   Already mostly enforced via `ProviderModel`, but worth making
   explicit: a request for a model the operator never declared 404s
   immediately, before any tailnet traffic.

### 2.3 Privacy / data handling

- **Per-user opt-in to request logging.** Default off. When off,
  only metadata persists (latency, tokens, model, status) — no
  prompts, no completions. When on, store a configurable retention
  window. No third-party reads either way (no training, no analytics).
- **Per-request `X-No-Log: true` header** so a consumer can opt out
  of logging on a per-call basis even if they've enabled it generally.
  OpenAI clients can pass this with a `default_headers` config.
- **Public log surface (separate switch).** "Make my logged requests
  visible on my profile" — useful for showcasing what people are
  building with their nodes, terrible if it leaks anything sensitive.
  Keep this *off* by default, gate it behind a checkbox the user has
  to tick after reading a warning, and never auto-include requests
  from before the toggle was flipped.

---

## 3. Testing strategy

We have ~2 test files in the inference app and zero frontend tests.
The shape of what to add is more important than the count.

### 3.1 Backend — pytest, three layers

- **Unit:** the manifest validator (largely there), `_find_provider_for_model`,
  `sync_provider_models_from_manifest`, the routing policy when it
  exists. Pure functions, no fixtures heavier than a model factory.
- **Service / view:** every `/v1/*` and `/api/*` endpoint with
  authenticated, unauthenticated, and cross-user cases. Use
  `requests_mock` or `responses` to stub the upstream agent so we
  can assert what we sent without needing a real agent. The upstream
  proxy is the most-likely-to-regress code in the repo; it deserves
  a test for: streaming pass-through, upstream 4xx pass-through,
  upstream timeout, no-online-provider, manifest-declared model not
  served by any online provider.
- **Integration / smoke:** one test that boots the whole stack via
  `docker compose -f docker-compose.yml` (the alt-port one), points
  at a fake agent, and runs the OpenAI Python SDK against `/v1/*`.
  Slow (~30s); run it in CI on PRs to `main` only, not on every
  push.

### 3.2 Frontend — Vitest + Vue Test Utils + Playwright

- **Unit on composables and stores:** `useAuthStore`, `useManifest`,
  any future routing or budget composable. Keep these <100 ms each.
- **Component tests for the few pages that have real logic:**
  `/dashboard/inference/requests`, `/{username}` (the public profile),
  the manifest editor when it exists. Mock the network layer.
- **Playwright smoke** of the golden path: log in (mocked OAuth) →
  mint token → see provider → call inference → see result. One
  spec, runs in CI nightly.

### 3.3 Agent integration

The agent lives in another repo but is part of this product's surface.
Add a contract test in this repo: a small fixture file describing
the registration request shape and the manifest upload shape, asserted
against the validator. The agent repo can run the same fixture against
its own code so a change in either side fails loudly.

### 3.4 What we are *not* testing

- Three.js scene rendering. Visual regression on Three is more
  pain than value at this stage; cover it with a "does the page
  mount without console errors" smoke and move on.
- The Pulumi infra code. It's executed by deployment; tests would
  duplicate the deploy.

### 3.5 CI

- Backend: `pytest` + coverage report on every PR; fail if coverage
  on changed lines drops.
- Frontend: `vitest run` on every PR; Playwright nightly on `main`.
- Lint/format gates already in editors — also in CI to keep PRs
  honest.

---

## 4. OpenRouter readiness (LLM-only)

We've decided to focus on LLMs. OpenRouter's "for providers" page
boils down to a handful of things we can either already do, or can do
with bounded work. Treat OpenRouter onboarding as the *forcing
function* for the API hardening described above — if our `/v1/*`
surface is good enough for OpenRouter, it's good enough for any
client.

### 4.1 Hard prerequisites — what to build

- **Models endpoint with OR's exact schema.** We return OpenAI's
  models shape today. OR wants more fields per model: `quantization`,
  `context_length`, `max_output_length`, `pricing`,
  `input_modalities`, `output_modalities`, `supported_features`,
  `supported_sampling_parameters`, optional `hugging_face_id` and
  `deprecation_date`. Source these from a richer manifest (§1.3). Add
  a `GET /v1/models?format=openrouter` (or just always include the
  fields — OpenAI clients ignore unknowns) so we don't have to
  maintain two endpoints.
- **SSE keep-alives.** Verify our streaming pass-through emits SSE
  comments during long generations, since OR explicitly calls this
  out as required.
- **429 under load instead of queue.** Today a slow upstream pins a
  worker for `UPSTREAM_TIMEOUT_SECONDS = 300`. Add a per-provider
  in-flight cap; when exceeded, return 429 immediately with
  `Retry-After`. OR's docs are explicit that queueing kills
  throughput scoring.

### 4.2 Operational targets — what to measure

OR's routing tiers care about uptime % and TTFT. Both should be
on the dashboard *for the operator's own provider* before we go
anywhere near OR's onboarding form, because the operator should be
able to see whether their setup is OR-tier *good* or *degraded*
before we promise OR anything.

- Track per-request `ttft_ms` (time-to-first-byte upstream) and
  `tokens_per_second` for streamed responses. Already have
  `latency_ms`; add the other two.
- Compute rolling 1h, 24h, 7d uptime % per provider, with the same
  classification OR uses (5xx + mid-stream errors count; 400/413/429
  excluded). Show the result on the provider detail page.

### 4.3 Onboarding posture

Don't talk to OR until: 95%+ aggregate uptime, 100+ real requests,
tokens per second visible on the dashboard, and the
"per-agent shared secret" hardening (§2.2) shipped. Then fill the
form.

---

## 5. Observability — request/response logging + public log surface

The user explicitly wants logs in the UI and optionally on the public
profile. Below is the shape that satisfies that without painting us
into a corner.

### 5.1 Storage

- **Always-stored metadata:** `model_name`, `status`, `latency_ms`,
  `ttft_ms`, `prompt_tokens`, `completion_tokens`, `provider_id`,
  `consumer_token_id`, `error_class` (if any). Cheap, useful for
  debugging and dashboards. This is the default for every request.
- **Optionally-stored body:** prompt + completion (or streamed
  reconstruction). Off by default; user toggles per-key. Stored in
  a separate `InferenceRequestBody` table so the metadata table
  stays small and fast to query.
- **Retention.** Per-user TTL on bodies (7 / 30 / 90 days, "keep
  forever" — your choice). Metadata kept indefinitely (for analytics).
- **Streamed responses** are tricky: we currently throw away the
  chunks and only record byte count. If logging is on, accumulate
  chunks into a string and store on stream close (already most of the
  scaffolding exists in `_stream_response`).

### 5.2 Dashboard surface

- `/dashboard/inference/requests/` already exists in stub form; flesh
  it out with a real table (model, latency, tokens, cost-when-defined,
  status, click-through to detail).
- Detail page: full prompt + completion, system/user/assistant
  message structure, sampling params used, provider chosen, routing
  reason, full timing breakdown.
- "Search by model / time range / status" — start with the obvious
  filters; don't build a query DSL.

### 5.3 Public log surface

- New `is_public` flag per `InferenceRequest`, defaulting to false.
- Per-key "default to public" setting.
- A new `/{username}/activity` page rendering the user's public
  requests as a feed: one card per request, model, prompt preview
  (first ~300 chars), completion preview, timing. Click-through to
  full detail (still public, since the user opted in).
- *Hard rule:* a request can never become public retroactively
  without an explicit "make this public" action on that specific
  request. The "default to public" setting only affects future
  requests after it was flipped on.

---

## 6. Public profile — three.js compute inventory

You've already got Tres.js, an existing `NetworkScene`, and a
collection of scene primitives (`PcTower`, `ServerRack`, `Monitor`,
etc.). The puzzle is: how do we let a user's manifest *drive* a
deterministic 3D rendering of their inventory?

### 6.1 Inventory model

The manifest has hosts and per-host GPU/service info. Map each host
to a scene component:

- `host.gpu.model` (if present) → `PcTower` with stickers/colors per
  vendor (`nvidia` → green, `amd` → red, `apple` → silver, `intel`
  → blue), GPU count drives a stack/array of cards inside the tower.
- `host.services` → small monitors / overlays attached to that tower
  showing the engine icon (vLLM logo, Ollama logo, etc.) and the model
  count.
- VRAM / context window can drive size or label intensity.

Pick a small, fixed component vocabulary so a manifest deterministically
yields the same scene. No procedural creativity in v1.

### 6.2 Layout

- Grid layout: hosts are arranged in a row, sorted by host id, with
  a fixed spacing. No physics, no orbits, no animation beyond a
  gentle camera drift.
- Empty state: a single empty desk with "no nodes yet" text so the
  3D area doesn't look broken on profiles that haven't uploaded a
  manifest.

### 6.3 Performance + accessibility

- Lazy-load the scene on `IntersectionObserver` so the profile page
  doesn't ship 200KB of Three to people who never scroll. Already a
  good pattern with `<ClientOnly>`.
- Provide a 2D fallback ("Show as table") that renders the same
  inventory as a static HTML table for screen readers / no-WebGL.

This stays a "nice touch" tier feature — don't block the marketplace
or security work on it.

---

## 7. Operational / ops debt

Lifted/expanded from `BACKLOG.md` because it matters for "right
track":

- **Backups.** Postgres on a single VPS in a bind mount. `pg_dump`
  cron + offsite (Backblaze B2) before any user-facing data matters.
- **Log shipping.** Loki + Grafana, or a hosted equivalent. Sentry
  catches exceptions; we need logs we can grep over.
- **Uptime monitoring.** UptimeRobot or Better Stack against
  `inference.club`, `api.inference.club`, and a synthetic `/v1/models`
  call with a known token. Alerts to whatever inbox the user actually
  reads.
- **Staging.** A second Pulumi stack on a smaller box. Required
  before anyone other than the author can risk a deploy.
- **Zero-downtime deploys.** Compose down/up loses ~5s. Either a
  blue/green compose flip or moving to a small k3s; not urgent.
- **DNS as code.** Move DNS to Cloudflare and manage it via
  `@pulumi/cloudflare` so future infra changes are reproducible.

---

## 8. Documentation debt

- `/about`, `/contact`, `/privacy-policy` are linked but 404 (router
  warnings every page load). Either ship them or remove the links.
- A "what is inference.club, who is it for" landing page that doesn't
  rely on the 3D scene. Crawlers and people on slow connections need
  a textual answer.
- A *threat model* doc (§2.2) before any public sign-up.
- A *provider operator's guide*: how to set up the agent, what the
  manifest fields mean, how to tell if your provider is healthy, how
  to read the dashboard's uptime number.
- A *consumer's guide*: how to point Cline / Open WebUI / Continue /
  raw OpenAI SDK at the API; what `default_headers={"X-No-Log": "true"}`
  does; what 4xx errors mean.

---

## 9. Suggested sequencing

A rough ordering. Each numbered group is "would land in roughly one
focused work-week if you weren't context switching." Treat as a draft
— pick what you actually want to do first.

**Phase A — harden what we have (do before recommending the project
to anyone):**
1. Token scopes + per-agent shared secret (§2.1, §2.2)
2. Per-token rate limiting + 429 on capacity (§2.1, §4.1)
3. Per-request token-count + ttft logging (§1.2, §4.2)
4. Backend test coverage to ~70% on `apps.inference` (§3.1)
5. Threat model doc + privacy policy page (§2.3, §8)

**Phase B — make the surface marketplace-shaped without flipping it
on:**
6. `ProviderVisibility` field, default `private` (§1.1)
7. Routing layer abstraction; today's behavior preserved (§1.1)
8. Manifest schema v2 with OR-shaped per-model fields (§1.3)
9. Per-user opt-in request body logging + retention (§5.1)

**Phase C — light up the visible product:**
10. Dashboard request log table + detail page (§5.2)
11. Public activity feed with explicit per-request public flag (§5.3)
12. Three.js manifest renderer on public profile (§6)

**Phase D — pursue OpenRouter:**
13. Uptime / TTFT / TPS dashboard surface for operators (§4.2)
14. SSE keep-alive + 429-under-load verification (§4.1)
15. OR-shaped `/v1/models` (§4.1)
16. Form submission once the provider's own dashboard shows
    OR-tier numbers

**Phase E — operational hygiene (in parallel, not blocking):**
17. Postgres backups + uptime monitoring (§7)
18. Staging stack (§7)
19. DNS as code (§7)

---

## 10. Open questions for the author

These are decisions only you can make; flagged here so they don't
get answered implicitly by whatever code gets written first.

1. **What's the minimum acceptable level of trust between consumer and
   provider?** Pure-public marketplace (anyone can route to anyone
   who's opted in)? Or invite-only graphs (consumer follows provider,
   provider accepts)? The data model differs.
2. **Are providers paid in fiat, in credits, or both?** This drives
   whether we ever need a payment processor and KYC, vs. staying a
   credit-only system.
3. **Do we want providers to be able to set per-model prices, or is
   pricing centralized?** OR has *floor* pricing per model; a
   marketplace usually wants providers to undercut each other.
4. **How important is anonymity?** Today every provider is identified
   by GitHub login. A privacy-respecting model (random handle, no
   GitHub display) is a different product.
5. **Are we OK requiring Tailscale forever, or is push-mode a hard
   requirement before public launch?** This affects who can run an
   agent.

Answers here change the order of phases B and D more than anything
else, so worth pinning down before either starts.
