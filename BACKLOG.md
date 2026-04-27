# inference.club backlog

Living list of work to do after the MVP. Roughly grouped by area; not
strictly prioritized. Items get deleted when shipped (use git history if
you need to know what was there).

## Dashboard / app UX

The dashboard is mostly stub pages right now. Token mint is the only
fully working flow.

- **`/dashboard/` landing** is a single `<h1>Dashboard</h1>` with no
  content. Fill in: API key prompt if no token yet, providers status
  summary, recent inference activity, "next step" cards.
- **`/dashboard/inference/requests/`** lists past `InferenceRequest`
  rows but the schema/columns aren't tuned (model, latency_ms, status,
  truncated request body).
- **`/dashboard/inference/requests/create.vue`** exists but is stale —
  there's no use case for manually creating an `InferenceRequest` from
  the UI; either delete the page or repurpose it as a "playground"
  (chat against your own provider from inside the dashboard).
- **`/dashboard/settings/general/`** is a stub — should at least show
  the user's email and a delete-account button.
- **`/providers/my-nodes/`** works but shows "No models reported" until
  the user clicks "Refresh models". The agent register flow already
  triggers this server-side; verify the UI updates after a fresh
  register without a manual click.
- **Sidebar nav (`AppSidebar.vue`, `NavMain.vue`, etc.)** has shadcn
  template defaults — links/labels need to reflect the real IA.
- **Empty states** across the dashboard need real copy + screenshots
  of what the populated view looks like.

## Local dev flow

Running the full stack on a laptop without spinning up a Tailscale
account would shorten the iteration loop.

- **No-Tailscale local mode.** Backend's `tailnet_base_url` already
  uses just the hostname when `TAILSCALE_TAILNET` is unset, and
  `_tailnet_proxies()` returns `None` when `TAILNET_PROXY_URL` is
  unset — so the proxy goes direct. What's missing is a way for the
  agent to register without needing a real Tailscale auth key.
  Options:
  - Add a "direct mode" to the agent (skip `tsnet`, listen on plain
    HTTP, register with its docker-network hostname). Smallest delta.
  - Or: provide a tiny Python `fake_agent.py` (we already have one
    from earlier smoke testing at `/tmp/fake_agent.py`) and a script
    that POSTs to `/api/inference/agent/register/` to seed a Provider
    row pointing at it. Useful for proxy/streaming dev without
    touching the Go agent at all.
- **`docker-compose.yml`** at repo root brings up backend + frontend +
  postgres on alternate ports (5532 / 8101 / 3100) so it can coexist
  with `manage.py runserver` / `yarn dev`. Document this in a CONTRIBUTING
  or DEVELOPMENT.md.
- **Seed script** that creates a dev user + token + provider in one
  command, so a fresh dev DB has something to inference against.

## API / proxy hardening

The `/v1/*` proxy works but a few things are MVP-grade.

- **Streaming (`stream: true`)** end-to-end isn't validated. The path
  is the same as buffered, but worth a real test with a long-running
  generation.
- **Hide diagnostic error from `/refresh-models/` response.** Currently
  the response includes `error` with full URL + proxy + exception
  detail. Useful while iterating but leaks internal infrastructure.
  Gate behind `DEBUG=True` or a per-user "admin" flag.
- ~~**`is_online` flapping.**~~ Done — see
  `backend/apps/inference/management/commands/probe_providers.py` and
  the `prober` service in the prod compose template. Single sidecar
  process, parallel probes every 30s, no Celery / Redis broker.
- **Rate limits per consumer key.** None today. Add before any kind of
  public sign-up.
- **Quota / accounting.** `InferenceRequest` rows are written but
  there's no aggregation, no billing surface.
- **Multi-provider routing.** If two providers serve the same model,
  pick deterministically (load-balanced or fastest-last). Today it's
  whichever ProviderModel row sorts first.
- **Failover.** If the chosen provider's agent goes offline mid-request,
  the request fails. Add one retry against a second matching provider.

## Agent integration

The agent (`inference-club-agent`) is in a separate repo; coordination
issues to watch.

- **Inbound auth on the agent.** Today the agent's `/v1/*` endpoint
  trusts any caller that can reach it on the tailnet. The Tailscale
  ACL is the only thing keeping randos out. Consider a shared HMAC or
  signed-token check before treating tailnet ACLs as the only
  perimeter.
- **OAuth-based per-agent auth keys.** Currently every agent gets the
  same static `TAILSCALE_STATIC_AUTHKEY`. PLAN.md §3 has the OAuth
  client flow that mints a fresh ephemeral key per provider; do this
  before scale-up.
- **Push mode for NAT-stuck agents.** The current model has the server
  reach into agents over the tailnet. Some users may not be able to
  run a tailnet daemon (firewalls, corp networks). PLAN.md mentions a
  websocket push variant — design + ship later.
- **Agent updates.** No mechanism to push agent updates today; users
  pull a new image manually.

## Infra / ops

- **Database backups.** Postgres lives in a bind mount on the single
  Hetzner VPS. Add `pg_dump` cron + offsite copy (Backblaze B2 or
  similar) before any data matters.
- **Log shipping.** `docker logs` only today. Loki + a tiny Grafana,
  or a hosted service.
- **Monitoring / alerting.** No uptime monitoring beyond "did the
  page load."
- **Zero-downtime deploys.** Compose restarts cause ~5s of downtime;
  fine for MVP, revisit when we have real users.
- **DNS as code.** `inference.club` and `api.inference.club` A
  records are managed by hand in NameCheap. Add `@pulumi/cloudflare`
  (move DNS to Cloudflare first) so future infra changes are
  reproducible.
- **Staging environment.** `pulumi stack init staging` + a separate
  Hetzner box + a separate set of GitHub secrets pointing at it.
  Useful once we have anything to risk breaking.
- **Custom error pages** in Caddy (502 / 503 / etc.) instead of raw
  plaintext.

## Marketing / docs

- **`/about`, `/contact`, `/privacy-policy`** are linked from the
  footer but don't exist (Vue Router warnings every page load).
- **Docs sidebar** surfaces directory-level pseudo-pages (`/docs/api`,
  `/docs/providers`) and the literal `/docs/index` alongside real
  pages. Filter those out in `layouts/docs.vue`.
- **Search** in the docs (Pagefind is the no-server option).
- **RSS** for the blog (one Nitro server route).
- **OG images per post** instead of the static `/images/inference-club.png`.
- **Status page** at `status.inference.club` (or a service like
  Better Stack / UptimeRobot) so users know when something's down.

## Security / launch checklist

Before opening sign-ups beyond personal use:

- Rotate any secret that has touched a chat transcript or commit
  (Hetzner token, GitHub OAuth client secret, etc.).
- Verify CSP headers on the frontend.
- Verify `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`, etc. in Django
  settings.
- Rate limit `/oauth/login/github/` and the token-mint endpoint.
- Review what the agent's `error` responses can leak about the
  upstream LLM server.
