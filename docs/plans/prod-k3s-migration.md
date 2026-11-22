# Moving inference.club production from docker compose to k3s

Report, 2026-11-21. **Status: done on 2026-11-22**, with three deviations from
the plan below. Day-to-day docs are in `k8s/README.md` and `infra/README.md`.

- **In place, not a new server.** The cheap server types were out of stock for
  new orders, but an in-place resize of the existing server to `cx33` was
  accepted. k3s was installed next to the running compose stack, the app was
  staged on side ports against a restored database copy, then cut over
  (about a minute of downtime).
- **Plain Postgres StatefulSet, not CloudNativePG.** Same `postgres:16` image
  on a retained local volume, plus a nightly `pg_dump` CronJob to the private
  GCS bucket. CloudNativePG remains a good follow-up.
- **Manifests live in this repo** under `k8s/`, not a separate deploy repo.

Not done: system-upgrade-controller, automatic reboots for kernel updates.
The stopped compose stack and its data are still on the server as a rollback.

## Verdict

Yes, do it, on single-node k3s, mainly because learning is the goal and most of the work already exists.

- **What you gain:** real production k8s experience, GitOps deploys with Argo CD, one set of manifests for homelab and prod, and proper database backups (prod has none today).
- **What you do not gain:** availability. One node running k3s is no more resilient than one node running compose. It is also more moving parts and more memory.
- **Why it is cheap for you:** the app already runs on k3s at `club.lan` from `~/git/inference-club-deploy` (kustomize, Argo CD, Traefik, migrate hook, probes). Prod is a second overlay of those manifests plus a handful of platform add-ons, not a fresh port.

If the goal were only "keep the site up with least effort", I would say stay on compose.

## What replaces what

| Today (compose on the VPS) | On k3s | Notes |
|---|---|---|
| docker compose | k3s, single server node | Bundles Traefik, CoreDNS, local-path storage, metrics-server |
| Pulumi `compose-up` over SSH | Argo CD in the cluster | Pulumi shrinks to: server, firewall, k3s install |
| Caddy reverse proxy | Traefik (bundled with k3s) | Same ingress controller as your homelab |
| Caddy automatic certs | cert-manager + Let's Encrypt | HTTP-01 through Traefik |
| `backend.env` rendered by Pulumi | Sealed Secrets | Encrypted secrets live in git |
| `postgres:16` + bind mount | CloudNativePG, one instance | Scheduled backups to your GCS bucket |
| `redis:7`, no persistence | Plain Deployment + Service | No operator needed |
| `tailscale` sidecar, SOCKS5 `:1055` | Deployment + Service named `tailscale` | State kept in a k8s Secret; `TAILNET_PROXY_URL` unchanged |
| backend, prober, celery worker/beat, frontend | Deployments | Already written for homelab; prober is the only new one |
| migrate on container start | Argo PreSync Job | Already exists (`RUN_MIGRATIONS_ON_START=0`) |
| Bind mounts in `/srv/inference-club` | local-path PVCs | Longhorn is overkill on one node |
| unattended-upgrades | unattended-upgrades + system-upgrade-controller | The second one upgrades k3s itself |

That is five add-ons to install: Argo CD, cert-manager, Sealed Secrets, CloudNativePG, system-upgrade-controller. Everything else ships with k3s.

## Your specific questions

### Argo CD: yes

Run it inside the prod cluster, non-HA install, app-of-apps like the homelab.

- Do not manage prod from the homelab Argo CD. That would make prod deploys depend on your home network and require exposing the prod kube API.
- It costs roughly 500–700 MB of RAM, which is the main reason to size up the server (below).
- Flux is lighter, but you already know and like Argo, and the UI is valuable while learning.

### Ingress: the bundled Traefik

- It is already in k3s and already what your homelab manifests target.
- ingress-nginx is being retired upstream, so it is the wrong thing to adopt now.
- SSE streaming for `/v1/chat/completions` works without the `flush_interval` tweak Caddy needed. If you add a compression middleware, exclude `text/event-stream` on the API host.
- Start with plain `Ingress` resources. Gateway API is a good later learning step and Traefik supports it.

### Certificates: cert-manager with Let's Encrypt

- A `ClusterIssuer` using HTTP-01 covers `inference.club` and `api.inference.club`; renewal is automatic.
- Test against the Let's Encrypt staging issuer first to stay clear of rate limits.
- Traefik's built-in ACME is simpler but stores certs in a file on one pod and teaches you less. cert-manager is the standard tool.
- HTTP-01 only works once DNS points at the new server, so the first cert is issued at cutover (about a minute). DNS-01 avoids that and allows wildcards, if your DNS provider has a cert-manager solver.

### Secrets

Sealed Secrets is the best fit for prod: encrypted in git, no external store to run. Your homelab uses External Secrets, but its store lives on the LAN, which prod should not depend on. Back up the sealing key somewhere safe; losing it means re-sealing everything.

### Database

CloudNativePG gives you scheduled base backups and WAL archiving to GCS, plus point-in-time restore. The database is 66 MB, so this is cheap. The simpler alternative is a plain StatefulSet with a `pg_dump` CronJob; it works, but you learn less and restores are coarser. Either way, this closes a real gap: there is no Postgres backup in prod right now.

### Server size

The current server is 2 vCPU / 4 GB and the app uses about 1.5 GB. k3s plus the add-ons need roughly another 1.5–2 GB. Go to the 4 vCPU / 8 GB tier (`cx33`); 4 GB would run but with no headroom for rollouts.

### Things I would leave out for now

Longhorn, a service mesh, the Tailscale operator, kube-prometheus-stack, multi-node HA. Each is a reasonable later project; none is needed to replace compose. For uptime, point your homelab Gatus at the public site.

## How the migration would go

1. **Restructure the deploy repo** into `base/` plus `overlays/homelab` and `overlays/prod`. Prod differs in hosts, auth flags, secrets, storage, image registry (GHCR), and adds the prober and tailscale Deployments.
2. **Provision a new server alongside the old one** with Pulumi: cloud-init installs a pinned k3s version. Keep 80/443 public; keep the kube API (6443) closed and reach it over Tailscale or an SSH tunnel.
3. **Bootstrap** Argo CD, then let it install the other add-ons and the app.
4. **Rehearse** a `pg_dump` restore into CloudNativePG and test the site via a hosts-file entry.
5. **Cut over:** lower DNS TTL beforehand, stop the old stack, final dump and restore, switch DNS, wait for the cert. Expect a few minutes of downtime.
6. **Keep the old VPS for a week** as rollback, then delete it.

CI changes little: GitHub Actions still builds to GHCR, then commits the new image tag to the prod overlay instead of running `pulumi up`. Argo CD syncs it.

Two things that will bite if forgotten:

- **Host firewall.** The ufw rules added today deny traffic k3s needs. The new server must allow the pod and service ranges (`10.42.0.0/16`, `10.43.0.0/16`), or `harden.sh` needs a k3s variant.
- **ALLOWED_HOSTS and probes.** The homelab crash loop (probes arriving with the pod IP as Host) applies to prod too; carry the same fix into the prod overlay.

## Decisions you need to make

| # | Decision | My recommendation |
|---|---|---|
| 1 | New server side by side, or convert the current VPS in place | New server; in place means long downtime and no rollback |
| 2 | Server size | 4 vCPU / 8 GB |
| 3 | Where prod manifests live | A GitHub repo (prod cannot reach `forgejo.lan`); either move `inference-club-deploy` to GitHub or use a `deploy/` folder in the app repo |
| 4 | Keep `api.inference.club` as a separate host, or go single-host like `club.lan` | Keep two hosts for the migration; no app, OAuth or cookie changes |
| 5 | Secrets tool | Sealed Secrets |
| 6 | Postgres | CloudNativePG with GCS backups; stay on Postgres 16 for the move |
| 7 | Cert challenge type | HTTP-01 unless your DNS provider makes DNS-01 easy |
| 8 | How image tags get bumped | CI commits the tag to the overlay, as in the homelab |
| 9 | kube API access | Tailscale or SSH tunnel only, never public |
| 10 | Node reboots for kernel updates | Automatic in a fixed window (kured or unattended-upgrades); this is the open question from today's hardening |
| 11 | What remains in Pulumi | Server, firewall, GCS, k3s bootstrap; app config moves to git |

## What to expect

- More to maintain: k3s and five add-ons need version bumps. Renovate, which you already run at home, handles most of it.
- Debugging shifts from `docker logs` to `kubectl`, events and Argo sync status. You already know this from the homelab.
- The first deploy will take longer than you expect; later ones will be faster and safer than today's SSH-driven rollout.
- A natural follow-up once it is stable: add a second node as a k3s agent to learn scheduling, draining and rolling node upgrades.
