# inference.club infrastructure

Pulumi (TypeScript) program for the node-level infrastructure: the Hetzner
Cloud server and firewall, the GCS media buckets, host hardening, and a
single-node k3s cluster with Argo CD bootstrapped. Run from GitHub Actions
(`infra-deploy`, manual dispatch); you don't need Pulumi installed locally.

The application is not deployed from here. Argo CD deploys it from `k8s/`
(see `k8s/README.md`).

## Layout

```
infra/
├── index.ts            # entry point
├── server.ts           # Hetzner server + firewall + SSH key
├── gcs.ts              # media buckets + service account
├── deployment.ts       # runs the two scripts below over SSH
├── config.ts           # typed access to Pulumi config / secrets
└── templates/
    ├── harden.sh       # key-only sshd, fail2ban, ufw
    └── k3s.sh          # k3s install, Traefik config, Argo CD bootstrap
```

Both scripts are idempotent and re-run whenever their contents change.

The server is protected three ways against accidental replacement: Hetzner
delete/rebuild protection, Pulumi `protect`, and `ignoreChanges` on
`userData`. Resizes keep the disk size so they can be reversed.

## Required GitHub repo secrets

Set at <https://github.com/inference-club/inference.club/settings/secrets/actions>:

| Name | Purpose |
|---|---|
| `HCLOUD_TOKEN` | Hetzner Cloud API token (Read & Write) |
| `PULUMI_ACCESS_TOKEN` | <https://app.pulumi.com/account/tokens> |
| `DEPLOY_SSH_PUBLIC_KEY` | Public key registered with Hetzner |
| `DEPLOY_SSH_PRIVATE_KEY` | Matching private key, base64-encoded |
| `GOOGLE_CREDENTIALS` | Service-account key JSON for managing the media buckets |

Application secrets (Django key, database password, OAuth, Tailscale, GCS
media credentials) are not GitHub or Pulumi secrets any more. They are
SealedSecrets in `k8s/inference-club/secrets/`.

## Running it

Actions tab → **`infra-deploy`** → Run workflow. Tick `preview_only` to see
what would change without applying it. Each run refreshes state from Hetzner
first, so a change made outside Pulumi is picked up, not undone.

Run it after any change under `infra/`. Pushes alone do not trigger it.

## Day-2 ops

| Need | How |
|---|---|
| SSH in | `ssh -i ~/.ssh/inference_club root@178.104.253.37` |
| Look at the cluster | `kubectl` on the server; see `k8s/README.md` |
| Deploy or roll back the app | A git commit under `k8s/`; see `k8s/README.md` |
| Resize the server | Change `serverType` in `Pulumi.prod.yaml`, run `infra-deploy` (powers the server off for a minute) |
| Tear down | `infra-destroy` will refuse while the server is protected. Remove `protect` and the two protection flags in `server.ts` first, deliberately. |

## From scratch

On a brand-new server the same workflow installs everything up to a running
Argo CD. Two things then need a human:

1. Point the `inference.club` and `api.inference.club` A records at the new IP.
2. Restore the Sealed Secrets key backup into `kube-system` (or re-seal every
   secret), and restore Postgres from the latest dump in the private bucket
   under `backups/postgres/`.
