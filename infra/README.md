# inference.club infrastructure

Pulumi (TypeScript) program that provisions a Hetzner Cloud VPS and deploys
the inference.club app stack (Caddy + Nuxt frontend + Django backend +
Postgres) over `docker compose`.

## Layout

```
infra/
├── index.ts            # entry point
├── server.ts           # Hetzner server + firewall + SSH key + cloud-init
├── deployment.ts       # renders templates, ships them via SSH, runs compose
├── config.ts           # typed access to Pulumi config / secrets
└── templates/
    ├── docker-compose.yml.tpl
    ├── Caddyfile.tpl
    └── backend.env.tpl
```

`__TOKEN__` placeholders in templates are substituted at `pulumi up` time
from stack config (no templating library needed).

## Required secrets

Set with `pulumi config set --secret <key> <value>` from inside `infra/`:

| Key | Purpose |
|---|---|
| `hcloudToken` | Hetzner Cloud API token (Read & Write). Create at https://console.hetzner.cloud → Security → API tokens |
| `sshPublicKey` | Contents of `~/.ssh/id_ed25519.pub` (added to the server) |
| `sshPrivateKey` | Contents of `~/.ssh/id_ed25519` (used by Pulumi to scp/run on the server) |
| `djangoSecretKey` | Random 50+ char string. Generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `postgresPassword` | Random string for the Postgres user |
| `githubOauthClientId` | Production GitHub OAuth App client ID |
| `githubOauthClientSecret` | Production GitHub OAuth App client secret |
| `ghcrUsername` | GitHub username with `read:packages` on the org's GHCR images |
| `ghcrToken` | Classic GitHub PAT with `read:packages` scope |

Non-secret config (already set in `Pulumi.prod.yaml`):

| Key | Default |
|---|---|
| `domain` | `inference.club` |
| `hcloudLocation` | `nbg1` (Nuremberg) |
| `serverType` | `cx22` (4 GB / 2 vCPU, ~€4/mo) |
| `backendImage` | `ghcr.io/inference-club/inference-club-backend:latest` |
| `frontendImage` | `ghcr.io/inference-club/inference-club-frontend:latest` |

## First deploy (from a clean machine)

1. **Install Pulumi**: `brew install pulumi/tap/pulumi`, then `pulumi login`.
2. **Register a production GitHub OAuth App** at <https://github.com/settings/developers>. Set the callback URL to `https://api.inference.club/oauth/complete/github/`. (You can edit it later if you decide on a different host.)
3. **Generate a deploy keypair** if you don't have one: `ssh-keygen -t ed25519 -f ~/.ssh/inference-club-deploy -C inference-club-deploy`.
4. **Install infra deps**: `cd infra && npm install`.
5. **Init the stack**: `pulumi stack init prod`.
6. **Set all the secrets above** with `pulumi config set --secret <key> <value>`.
7. **Provision + deploy**: `pulumi up`.
8. The stack output `serverIp` is the new VPS's IPv4. SSH in with `ssh -i ~/.ssh/inference-club-deploy root@<ip>`. Logs: `cd /srv/inference-club && docker compose logs -f`.
9. **Point DNS** at `serverIp`: A records for `inference.club` and `api.inference.club`. Caddy auto-issues TLS certs once DNS resolves.

## Subsequent deploys

Two paths:

- **Automatic** — push to `main`. The `build-and-push` GitHub workflow builds new images and tags them with the commit SHA. The `deploy` workflow then runs `pulumi up` with that SHA. Requires the `PULUMI_ACCESS_TOKEN` GitHub secret and the same Pulumi secrets above (set as `pulumi config` once and the GitHub action picks them up).
- **Manual** — `cd infra && pulumi up` from your laptop. Or trigger the `deploy` workflow with a specific image SHA.

## Day-2 ops

| Need | How |
|---|---|
| SSH in | `ssh -i <key> root@<serverIp>` |
| Tail app logs | `docker compose -f /srv/inference-club/docker-compose.yml logs -f backend` |
| Force-redeploy with current images | `cd infra && pulumi up --refresh` |
| Roll back to a specific SHA | Trigger `deploy` workflow manually with `image_sha=sha-abc1234` |
| Take it down | `pulumi destroy` (deletes the VPS — Postgres data is on the server, so back it up first) |

## Deferred — revisit before scaling up

- **Backups.** Postgres data lives in a bind mount on the single VPS. Add `pg_dump` cron + offsite copy (e.g. Backblaze B2) before this matters.
- **Monitoring / log shipping.** Currently `docker logs` only. Loki + Grafana or a hosted service when you outgrow that.
- **Zero-downtime deploys.** Compose restarts cause ~5 s of downtime. Compose v2 + Caddy support no-downtime via container replacement; revisit when traffic warrants it.
- **Staging environment.** Clone the stack as `pulumi stack init staging` and `pulumi config cp -d staging` from prod, then point at a separate Hetzner server.
- **Provisioned smaller server during off-hours.** Out of scope for MVP.
