# Setup docs

Operational docs for maintainers — how to set up the external accounts
and credentials this project depends on. These are *not* the public-facing
docs at `frontend/content/docs/` (which are for users of the API).

If you're doing a clean deploy from zero, work through these in order:

1. **[GitHub OAuth app](github-oauth.md)** — for sign-in
2. **[Tailscale](tailscale.md)** — for the agent ↔ server private network
3. **[Pulumi + GitHub secrets](secrets.md)** — what every secret is, where it comes from
4. **[First deploy](../../infra/README.md)** — the actual `pulumi up` runbook

For day-to-day:

- **[Local dev](local-dev.md)** — running the stack on your laptop
- **[`infra/README.md`](../../infra/README.md)** — deploy / destroy / day-2 ops
- **[`BACKLOG.md`](../../BACKLOG.md)** — what's known-broken or known-missing

For architecture / "why is it like this":

- **[Tailscale agent integration plan](../plans/tailscale-agent-integration.md)** —
  the contract between this repo and `inference-club-agent`
- **[Tailscale + tsnet deep dive](https://inference.club/blog/tailscale-and-tsnet)** —
  the public blog post version
