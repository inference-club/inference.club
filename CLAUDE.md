# Working in this repo

inference.club is a Django API (`backend/`) and a Nuxt 3 app (`frontend/`).
Inference is done by GPU services in a Kubernetes cluster; an agent
([inference-club-agent](https://github.com/inference-club/inference-club-agent))
discovers them and registers them with the backend.

## Start a dev session

```bash
scripts/dev-check.sh --up        # compose stack + in-cluster dev agent, then checks
scripts/dev-check.sh --smoke     # one real request per cluster service
```

- Frontend http://localhost:3101, backend http://localhost:8101, mail http://localhost:8125.
- Both hot-reload. Rebuild an image only when its lockfile changes.
- Backend commands always run in compose: `docker compose exec backend python manage.py …`
  and `docker compose exec backend pytest -q`. Never bare-metal poetry.
- Sign in locally as the seeded staff user `designbot@inference.club` /
  `designbot-pass-1` (`docker compose exec backend python manage.py seed_design_data`).
- The dev agent is the `agent-dev` Deployment in namespace `inference-club`. It is
  parked at 0 replicas between sessions. Cluster changes go through the
  home-cluster repo and Argo CD, not `kubectl apply`.

## The quality loop

The plan lives in GitHub milestones (M0–M5) and issues on this repo. Work an
issue like this:

1. Pick the lowest open milestone, then the smallest open issue in it.
2. Branch from `main` (`fix/…`, `design/…`, `feat/…`). One issue or one tight
   group of issues per branch.
3. Make the change. Check it in the running app, on phone, tablet and desktop.
4. Run the guards (from `frontend/`):
   - `yarn audit && yarn audit:report` — every page × 375 / 768 / 1440, never
     fails, writes findings and screenshots to `.captures/audit/`.
   - `yarn test:overflow` — fails on any page that scrolls sideways.
   - `yarn i18n:check` — every locale has every key.
   - `docker compose exec backend pytest -q` for backend changes.
5. Open a PR that says what changed and how it was checked, with before/after
   screenshots for visual work. `Closes #n`.
6. New problems found on the way become issues in the right milestone. They do
   not get fixed in the current branch unless they are one line.

A page added to `frontend/pages/` gets a row in `frontend/e2e/routes.ts` in the
same PR.

## Conventions

- UI: shadcn-vue primitives in `frontend/components/ui`, Tailwind v4, dark and
  light themes both first-class. Flex children that hold text need `min-w-0`;
  long tokens need `break-words` or `truncate`.
- Every user-visible string goes through i18n (`frontend/i18n/locales`), in all
  seven locales.
- API: `/v1/*` is the public, token-authenticated surface and is described in
  `backend/apps/inference/openapi.yaml`; change the spec with the code.
- Commits are conventional (`feat(scope): …`). `/commit` commits; `/deploy`
  lands on main and deploys production, so only on request.
- This repo is public. No LAN addresses, hostnames, tokens or personal details
  in code, issues or PRs.
