# Improvement roadmap (tracker)

A running checklist of multi-user-readiness improvements. Companion to the
strategic [`post-mvp-roadmap.md`](./post-mvp-roadmap.md) — that doc argues
*direction*; this one tracks *status*.

**Status:** ✅ shipped · 🔜 next · 📋 backlog · ❄️ deferred (by choice)

_Last updated: 2026-05-30_

---

## ✅ Shipped

- **Per-service access control** — `ProviderService` with PRIVATE / AUTHENTICATED /
  RESTRICTED (GitHub-username allowlist); access-aware `/v1/models` + chat routing
  (the "my providers, my requests → network" pivot).
- **Rate limiting** — per-user DRF throttles on `/v1/*` (429 + `Retry-After`),
  configurable.
- **Request-size guardrails** — max messages, max input chars, `max_tokens` clamp.
- **Provider pause / kill switch** — `accepting_requests`; toggle on My Nodes.
- **Token accounting** — `prompt/completion/total_tokens` columns + backfill.
- **Token leaderboard** — top consumers, hour→year ranges.
- **Rate-limit usage meter** — `/api/inference/usage/`, `X-RateLimit-*` headers,
  Settings → Usage page.
- **Shared Redis cache** — dev compose + prod template, so limits + meter are
  accurate across gunicorn workers.
- **Dev / UX foundations** — no-Tailscale local dev pathway, GitHub OAuth dev
  wiring, rich Inference Requests UI (cards, detail, reasoning, Your/All, delete),
  dynamic breadcrumbs, dashboard footer, Privacy/Terms pages.

---

## 🔜 Recommended next (pick 1–2 for organic-growth phase)

1. **403 → 401 auth fix** — _tiny._ OpenAI clients (Open WebUI etc.) misreport a
   bad/missing key as "network problem" because DRF returns 403 (SessionAuth is
   first in `DEFAULT_AUTHENTICATION_CLASSES`). High polish, ~1 small change.
2. **In-app playground** — a simple chat UI in the dashboard to try an available
   model right after signup, no external client needed. Biggest friction-reducer
   for new signups, and demoable/shareable on social.
3. **Public profile polish** (`/{github_login}`) — shareable card of a member's
   nodes / models / usage. On-brand for organic social growth.
4. **Provider-side usage view** — "who used my GPU, how much" (reuses the new
   token columns); builds provider trust now that others can route to you.

---

## 📋 Backlog by theme

### Safety / abuse (rest of category A)
- Abuse reporting + admin review queue.
- Per-consumer block (a provider blocks a specific user).
- Content takedown / hide (data is open-by-default).
- _Note: hard ban today = deactivate the user in Django admin._

### Usage / economics
- Quotas / credits (the ToS mentions credits that don't exist — build or soften).
- Provider earnings / consumption dashboard.
- Leaderboard privacy opt-out.

### Reliability / routing
- Failover + retry to another provider on error / mid-stream drop.
- Busy-awareness / load balancing across providers serving the same model.
- "loaded vs available" model state (heartbeat ≠ ready).
- Proxy concurrency review (gthread workers vs streaming load).

### Privacy / data governance
- Retention + purge job (`InferenceRequest` grows unbounded).
- Per-request / per-account "private" option + clear visibility indicators.
- Account deletion + data export (Privacy Policy promises deletion).

### Observability / ops
- Sentry, DB backups, staging environment.
- Network health / status page.
- Prometheus + Grafana + OpenTelemetry from vLLM metrics — _parked (complex)._

### Quality / CI
- Backend tests: access control, cross-user routing, serializers, streaming/usage.
- CI test gate + frontend typecheck/lint.

### Product / growth
- Onboarding quickstart (consumer + provider) + clear "no provider / no access"
  errors.
- **Blog** — build out with `@nuxt/content` to document progress & new features.
- Model catalog / discovery improvements (what can I run, who serves it).
- Offline notifications when a member's node drops (email via GitHub address).

---

## ❄️ Deferred (deliberately, for now)

- **Separate API vs agent auth tokens / key management** — not a priority; one
  DRF token continues to do double duty.
- **GitHub org-based access** (`read:org` scope).
- **Economic model + trial-audience decisions** — growing organically on social
  for now, so these stay open.
