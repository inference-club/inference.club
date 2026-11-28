# inference.club

A distributed inference network built from consumer GPUs. Members run an
agent next to their models; the network gives everyone one OpenAI-compatible
API and a web app for chat, images, video, music, speech, transcription, 3D
and multi-step workflows.

- Hosted service: <https://inference.club>
- User and API docs: <https://inference.club/docs>
- The agent that puts a machine on the network:
  [inference-club-agent](https://github.com/inference-club/inference-club-agent)

## How it fits together

```
 browser ──▶ Nuxt app (frontend/) ──▶ Django API (backend/) ──▶ agent ──▶ model services
 scripts, SDKs, MCP ───── /v1 ──────────────┘         private network        on your GPUs
```

- **`backend/`** Django + DRF. `/v1/*` is the public OpenAI-compatible surface
  (described in `backend/apps/inference/openapi.yaml`, served at
  `/openapi.json`); `/api/*` serves the web app. Celery runs queued jobs and
  workflows.
- **`frontend/`** Nuxt 3, Tailwind v4, shadcn-vue. Playground, media library,
  cluster view, docs and blog.
- **Agents** register a manifest of the models they serve and proxy requests to
  them, over Tailscale for the hosted service or directly on a LAN.
- **`k8s/`, `infra/`** production deployment (k3s, Argo CD, Pulumi for the node).
- **`integrations/`** the `ic` CLI and agent skill.

## Use it

```bash
curl https://api.inference.club/v1/chat/completions \
  -H "Authorization: Bearer $INFERENCE_CLUB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "<a model from /v1/models>", "messages": [{"role": "user", "content": "hello"}]}'
```

Any OpenAI SDK works with `base_url="https://api.inference.club/v1"`. See the
[quickstart](https://inference.club/docs/quickstart).

## Run a node

See [Run an agent](https://inference.club/docs/providers/run-an-agent) and, for
Kubernetes clusters, [the Kubernetes agent](https://inference.club/docs/providers/kubernetes-agent).

## Develop

Requirements: Docker, and for real inference a cluster running the agent's dev
Deployment (the app works without it; model lists are just empty).

```bash
docker compose up -d            # or: scripts/dev-check.sh --up
scripts/dev-check.sh            # stack, agent and catalog readiness
scripts/dev-check.sh --smoke    # one real request per service
```

- App http://localhost:3101, API http://localhost:8101, mail catcher http://localhost:8125
- Backend and frontend both hot-reload.
- Tests: `docker compose exec backend pytest -q`
- Design guards (from `frontend/`): `yarn audit && yarn audit:report`,
  `yarn test:overflow`, `yarn i18n:check`

More in [docs/setup/local-dev.md](docs/setup/local-dev.md). The plan of work is
in this repo's [milestones](https://github.com/inference-club/inference.club/milestones);
[CLAUDE.md](CLAUDE.md) describes the loop used to work through it.

## Deploy your own

[docs/setup/](docs/setup/README.md) covers the external accounts and secrets;
[infra/README.md](infra/README.md) is the deploy runbook. A blog post walks
through [self-hosting](https://inference.club/blog/self-hosting-inference-club).
