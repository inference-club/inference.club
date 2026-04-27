# Secrets and config

Single-source-of-truth list of every credential the platform reads.

| Where | What | Source |
|---|---|---|
| GitHub repo secret | `HCLOUD_TOKEN` | [Hetzner Cloud Console → Security → API Tokens](https://console.hetzner.cloud) — Read & Write |
| GitHub repo secret | `PULUMI_ACCESS_TOKEN` | [Pulumi Cloud → Personal access tokens](https://app.pulumi.com/account/tokens) (free tier) |
| GitHub repo secret | `GHCR_TOKEN` | <https://github.com/settings/tokens/new> — classic PAT, scope `read:packages` only. Used by the VPS to pull private container images |
| GitHub repo secret | `DEPLOY_SSH_PUBLIC_KEY` | Public half of an ED25519 keypair you generate (`ssh-keygen -t ed25519 -f ~/.ssh/inference-club-deploy`) |
| GitHub repo secret | `DEPLOY_SSH_PRIVATE_KEY` | Private half of the same keypair, **base64-encoded as a single line**: `base64 -i ~/.ssh/inference-club-deploy \| tr -d '\n'`. The workflow exports it as an env var; `infra/config.ts` decodes it. Multi-line values can't go through pulumi/actions' YAML config-map cleanly, hence the encoding |
| GitHub repo secret | `TAILSCALE_TAILNET` | MagicDNS suffix of your tailnet, e.g. `tailb224b8` — see [tailscale.md §2](tailscale.md#2-find-your-tailnet-name) |
| GitHub repo secret | `TAILSCALE_WEB_AUTHKEY` | Tailscale auth key tagged `tag:club-web` (Reusable: off, Ephemeral: off) — see [tailscale.md §5](tailscale.md#5-generate-two-auth-keys) |
| GitHub repo secret | `TAILSCALE_STATIC_AUTHKEY` | Tailscale auth key tagged `tag:club-host` (Reusable: on, Ephemeral: on) — handed to every registering agent |
| GitHub repo secret | `GH_OAUTH_CLIENT_ID` | From the production GitHub OAuth App — see [github-oauth.md](github-oauth.md) |
| GitHub repo secret | `GH_OAUTH_CLIENT_SECRET` | Same OAuth App, "Generate a new client secret" |
| Pulumi auto-generated | SSH keypair | ⛔️ removed — we used to auto-gen via `@pulumi/tls` but it regenerated unpredictably and triggered server replacement. Now user-supplied (`DEPLOY_SSH_*` above) |
| Pulumi auto-generated | `djangoSecretKey` | `@pulumi/random` `RandomPassword` — never visible to humans, persists in Pulumi state |
| Pulumi auto-generated | `postgresPassword` | Same — `@pulumi/random`, persists in state |
| `backend/.env` (local dev only) | `GITHUB_OAUTH_CLIENT_ID/SECRET` | Dev OAuth app — see [github-oauth.md](github-oauth.md#dev-app) |
| `backend/.env` (local dev only) | `INFERENCE_CLUB_API_KEY` (if running the agent locally) | Mint via the dashboard once logged in |

## Where to set repo secrets

<https://github.com/inference-club/inference.club/settings/secrets/actions> →
**New repository secret** for each.

You can also script it from the CLI once `gh` is authed:

```bash
echo "<value>" | gh secret set HCLOUD_TOKEN -R inference-club/inference.club
```

For the multi-line `DEPLOY_SSH_PRIVATE_KEY` value, base64-encode first:

```bash
base64 -i ~/.ssh/inference-club-deploy | tr -d '\n' \
  | gh secret set DEPLOY_SSH_PRIVATE_KEY -R inference-club/inference.club
```

## How values flow at deploy time

1. **GitHub Actions workflow** (`.github/workflows/infra-deploy.yml`)
   reads `secrets.X` for each name above
2. Most are passed to `pulumi/actions` as `config-map` entries (Pulumi
   secrets, encrypted in state)
3. `HCLOUD_TOKEN` and `DEPLOY_SSH_PRIVATE_KEY` are passed as **env
   vars** instead — the hcloud provider reads `HCLOUD_TOKEN` directly,
   and multi-line values don't survive YAML config-map serialization
4. Pulumi auto-generates `djangoSecretKey` and `postgresPassword`
   inside the program (no user input needed)
5. `infra/deployment.ts` substitutes everything into
   `backend.env.tpl` and `docker-compose.yml.tpl`, base64-encodes the
   rendered files, and ships them to the VPS over SSH

## Rotating

| If this leaks | Do this |
|---|---|
| `HCLOUD_TOKEN` | Hetzner console → revoke the old token, generate a new one, update the repo secret, trigger `infra-deploy` |
| `GHCR_TOKEN` | <https://github.com/settings/tokens> → revoke + regenerate, update secret, redeploy |
| `DEPLOY_SSH_PRIVATE_KEY` | Generate a new keypair, update both `DEPLOY_SSH_PUBLIC_KEY` and `DEPLOY_SSH_PRIVATE_KEY`, redeploy. Pulumi will replace the Hetzner SSH key (handled cleanly by `deleteBeforeReplace: true` in `infra/server.ts`) |
| `TAILSCALE_*_AUTHKEY` | Tailscale admin → revoke the old key, generate a new one with the same tag/options, update secret, redeploy |
| `GH_OAUTH_CLIENT_SECRET` | GitHub OAuth app → "Generate a new client secret", update repo secret, redeploy |
| `djangoSecretKey` / `postgresPassword` | Less straightforward — these live in Pulumi state. Rotating djangoSecretKey logs everyone out (sessions are signed with it). Rotating postgresPassword without coordination breaks the existing Postgres data dir. Coordinate carefully or do `pulumi destroy && pulumi up` for a clean reset (loses data) |

## What we deferred

- **Per-agent Tailscale auth keys via OAuth client.** The static
  reusable key is fine for MVP. Setting up the OAuth client is in
  the [backlog](../../BACKLOG.md#agent-integration)
- **DNS as code.** A records for `inference.club` and
  `api.inference.club` are managed by hand at NameCheap. Adding
  `@pulumi/cloudflare` (after moving DNS to Cloudflare) is in the
  backlog
- **Secret rotation playbook automation.** Rotation is manual today
