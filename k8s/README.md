# Production on k3s

inference.club runs on a single-node k3s cluster on the Hetzner server.
Argo CD, running in the cluster, deploys whatever is in this directory on
`main`. Nothing here is applied by hand.

## Layout

```
k8s/
├── apps/             # Argo CD Applications (app-of-apps). One file per thing deployed.
├── platform/         # Cluster add-ons: Argo CD itself, Sealed Secrets, cert-manager issuers
└── inference-club/   # The app: Postgres, Redis, Tailscale, backend, workers, frontend, ingress
    ├── config.env    # Non-secret backend settings
    └── secrets/      # SealedSecrets (encrypted; safe to commit)
```

The node itself (server, firewall, k3s install, Traefik config, first Argo CD
bootstrap) is Pulumi's job: see `infra/`.

## How a deploy happens

1. Push to `main` touching `backend/` or `frontend/`.
2. `build-and-push` builds both images, pushes them to GHCR as `sha-<commit>`.
3. Its `deploy` job commits that tag to `inference-club/kustomization.yaml`.
4. Argo CD notices within about three minutes and rolls the pods. The backend
   runs migrations in an init container before the new version takes traffic.

Config change: edit `inference-club/config.env` or a manifest, push. Same path.

Rollback: set both `newTag` values in `inference-club/kustomization.yaml` to an
older `sha-<commit>` and push (or `git revert` the `deploy:` commit).

## Getting at the cluster

The Kubernetes API is not exposed publicly. Use SSH:

```bash
ssh -i ~/.ssh/inference_club root@178.104.253.37 kubectl get pods -A
```

Argo CD UI, tunnelled to http://localhost:8080 (user `admin`):

```bash
ssh -i ~/.ssh/inference_club -L 8080:localhost:8080 root@178.104.253.37 \
  kubectl -n argocd port-forward svc/argocd-server 8080:80 --address 127.0.0.1
```

```bash
ssh -i ~/.ssh/inference_club root@178.104.253.37 \
  "kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
```

## Secrets

Secrets are SealedSecrets: encrypted with a key only the cluster holds. To add
or change one, run on the server (which has `kubeseal`):

```bash
kubectl -n inference-club create secret generic backend-secrets \
  --from-env-file=values.env --dry-run=client -o yaml | kubeseal -o yaml
```

Commit the output under `inference-club/secrets/`. Sealing replaces the whole
secret, so `values.env` must contain every key, not just the changed one.

The sealing key is backed up outside the cluster. Without it, every secret has
to be re-created from its original value.

## Data

- **Postgres** lives on a `local-path-retain` volume (kept on disk even if the
  claim is deleted).
- **Backups:** the `postgres-backup` CronJob dumps nightly to the private GCS
  bucket under `backups/postgres/`, 30 days kept. `inference-club/backup.yaml`
  has the run-now and restore commands.
- **Media** is on GCS and is not on the server at all.
- **Tailscale** node state is a host directory, `/srv/inference-club/tailscale-state`.

## Certificates

cert-manager issues Let's Encrypt certificates for the hosts in
`inference-club/ingress.yaml` over HTTP-01 and renews them automatically.
A new hostname needs a DNS record pointing at the server first.

## Upgrades

- **k3s:** automatic. system-upgrade-controller follows the k3s `stable`
  channel (`platform/system-upgrade/k3s-plan.yaml`) and upgrades between
  04:00 and 05:00 UTC. Pods keep running during an upgrade. Check with
  `kubectl -n system-upgrade get plans,jobs`. To hold a version, set
  `version:` instead of `channel:` in the plan.
- **system-upgrade-controller:** bump the version in
  `platform/system-upgrade/kustomization.yaml`.
- **Argo CD:** bump the version in `platform/argocd/kustomization.yaml`.
- **cert-manager:** bump `targetRevision` in `apps/cert-manager.yaml`.
- **Sealed Secrets:** bump the version in `platform/sealed-secrets/kustomization.yaml`.
