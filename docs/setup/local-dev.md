# Local dev

Running the inference.club stack on your laptop.

**The default loop is `docker compose up`.** It runs the whole stack —
Postgres, Redis, Mailpit, RustFS (S3), backend, Celery worker + beat,
prober and the Nuxt dev server — with the source bind-mounted, so both
halves hot-reload. A no-Docker host loop is documented below as a fallback.

## Quick start

```bash
docker compose up -d --build      # first run builds the backend image
docker compose logs -f backend frontend
```

| What | URL |
|---|---|
| Frontend (Nuxt dev, HMR) | <http://localhost:3101/> |
| Backend API / admin | <http://localhost:8101/admin/> |
| Mailpit (sign-up confirmation mails) | <http://localhost:8125/> |
| RustFS console (media bucket) | <http://localhost:9101/> — `inferenceclub` / `localdevrustfs` |
| Postgres | `postgres://inference:localdev@localhost:5532/inference` |

Host ports are deliberately off-default (3101 / 8101 / 5532 / 9100) so
they coexist with Docker Desktop's `:3000`/`:5432` and Grafana LGTM's
Loki on `:3100`. Override the frontend port with `FRONTEND_PORT=…` in a
repo-root `.env`.

## Signing in

Local dev uses **email + password only** (`AUTH_EMAIL_ENABLED=True`,
`AUTH_GITHUB_ENABLED=False`) — no OAuth app needed, and `backend/.env`
is optional.

- **New account:** register on <http://localhost:3101/register>, click
  the confirmation link in Mailpit, then sign in.
- **Existing (GitHub-created) account:** it has no password yet — set one:
  `docker compose exec backend python manage.py changepassword <email>`
- **Admin:** `docker compose exec backend python manage.py createsuperuser`

To bring GitHub back, set `AUTH_GITHUB_ENABLED=True` in a repo-root
`.env`, put the dev OAuth app creds in `backend/.env` (see
[github-oauth.md](github-oauth.md#dev-app)), and make the app's callback
match the compose ports.

## Hot reload — what reloads and what doesn't

- **Backend:** `./backend` is mounted over the image's `/app` and the
  container runs `manage.py runserver` (migrations run on start).
  Python edits reload in ~1 s. Rebuild (`docker compose build backend`)
  only when `pyproject.toml` / `poetry.lock` change.
- **Frontend:** `./frontend` is mounted; `yarn dev` (Vite HMR) picks up
  `pages/`, `components/`, `composables/` instantly. `nuxt.config.ts`
  changes need `docker compose restart frontend`; new deps need a
  restart too (it runs `yarn install` on start into its own
  `node_modules` volume).
- **Celery worker / beat** run under `watchmedo auto-restart` (watchdog,
  installed only in the backend image's `dev` stage) and restart on any
  `.py` change. The **prober** shares the code but doesn't reload —
  `docker compose restart prober` if you touch it.

## Host loop (no Docker, fallback)

```bash
cd backend && poetry install && poetry run python manage.py migrate
poetry run python manage.py runserver 8001        # SQLite by default
cd frontend && yarn install && yarn dev --port 3001
```

`DATABASE_URL` points it at the compose Postgres if you want real data.
`frontend/nuxt.config.ts` defaults `apiBase` to `http://localhost:8001`
(override with `NUXT_PUBLIC_API_BASE`).

## Using real cluster agents (direct mode)

The compose backend runs with `INFERENCE_DIRECT_AGENTS=True`, so an agent
started with `AGENT_DIRECT=1` can register to `http://<mac-lan-ip>:8101`
and the backend calls it straight over the LAN — no Tailscale. The home
cluster's `agent-dev` Deployment (home-cluster `services/agent-dev/`) is
set up exactly this way: scale it to 1 and every model on the nodes that
are up appears in the local catalog. Those provider services are owner-only
(PRIVATE), so sign in as the account that owns them.

## Running the agent locally

For end-to-end testing of the inference proxy, you need a registered
provider. Two paths today:

### Path A — real agent + real Tailscale (no shortcuts)

If you have a Tailscale account already (and the same `TAILSCALE_*`
secrets the prod deploy uses), the agent can register against your
local Django and join the *production* tailnet. Point it at your
local backend:

```bash
cd ~/git/inference-club-agent
# .env
INFERENCE_CLUB_API_KEY=<token from your local dashboard>
INFERENCE_CLUB_URL=http://host.docker.internal:8001
LOCAL_LLM_URL=http://host.docker.internal:1234/v1
```

Then `docker build -t inference-club-agent:dev . && docker run …`.

The agent registers, gets the static Tailscale auth key from your
local backend (which means your local backend needs the
`TAILSCALE_STATIC_AUTHKEY` env var set — easiest is to copy the
value from prod into `backend/.env`), and joins the prod tailnet.

This works but it pollutes the prod tailnet with dev devices.
Acceptable for occasional testing; not great for sustained dev work.

### Path B — fake agent + manual Provider row

For UI dev / proxy dev where you don't actually need to run an LLM,
spin up a stub HTTP server that pretends to be the agent's `/v1/*`
surface, and seed a Provider row in the local DB pointing at it:

```bash
# terminal: stub agent on port 9876
python3 - << 'PY'
import json, time
from http.server import BaseHTTPRequestHandler, HTTPServer

def chat_response(body):
    return {
        "id": "chatcmpl-stub", "object": "chat.completion",
        "created": int(time.time()), "model": body.get("model","stub"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "stub reply"}, "finish_reason": "stop"}],
    }

class H(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self):
        if self.path.endswith("/healthz"):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok"); return
        if self.path.endswith("/v1/models"):
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers()
            self.wfile.write(json.dumps({"object":"list","data":[{"id":"stub-llm","object":"model"}]}).encode())
            return
        self.send_response(404); self.end_headers()
    def do_POST(self):
        n = int(self.headers.get("content-length",0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path.endswith("/chat/completions") or self.path.endswith("/completions"):
            payload = json.dumps(chat_response(body)).encode()
            self.send_response(200); self.send_header("Content-Type","application/json")
            self.send_header("Content-Length", str(len(payload))); self.end_headers()
            self.wfile.write(payload); return
        self.send_response(404); self.end_headers()

HTTPServer(("127.0.0.1", 9876), H).serve_forever()
PY
```

```bash
# terminal: seed a Provider row pointing at the stub
cd backend
poetry run python manage.py shell -c "
from apps.accounts.models import CustomUser
from apps.inference.models import Provider, ProviderModel
from rest_framework.authtoken.models import Token
from django.utils import timezone

u, _ = CustomUser.objects.get_or_create(email='dev@inference.club', defaults={'is_active': True})
u.set_unusable_password(); u.save()
Token.objects.filter(user=u).delete()
t = Token.objects.create(user=u)
print('TOKEN:', t.key)

Provider.objects.filter(user=u, name='stub').delete()
p = Provider.objects.create(
    user=u, name='stub',
    tailnet_hostname='127.0.0.1',  # short-name resolved by your laptop's hosts file
    agent_port=9876,
    is_active=True,
    last_seen_at=timezone.now(),
    registered_at=timezone.now(),
)
ProviderModel.objects.create(provider=p, name='stub-llm', is_active=True)
print('Provider seeded. Test with: curl -H \"Authorization: Bearer ' + t.key + '\" http://localhost:8001/v1/models')
"
```

Because `TAILNET_PROXY_URL` is unset in dev, the backend's
`_tailnet_proxies()` returns `None` and `requests` talks to
`127.0.0.1:9876` directly — no Tailscale needed.

A "no-Tailscale local mode" baked into the real agent (skip `tsnet`,
listen on plain HTTP) is on the [backlog](../../BACKLOG.md#local-dev-flow);
until then this stub is the simpler option for UI / proxy work.

## Ergonomic things

- **Browser dev tools.** The shadcn-vue components ship a lot of
  ARIA-driven behavior; install the Vue Devtools extension for any
  reactivity debugging
- **Reset the dev DB.** compose: `docker compose down -v` (drops the
  Postgres, RustFS and node_modules volumes). Host loop: `rm
  backend/db.sqlite3 && poetry run python manage.py migrate`
- **Frontend hot reload.** Nuxt picks up changes to `pages/`,
  `components/`, `composables/`, and `content/` without a restart.
  `nuxt.config.ts` and `app.config.ts` *do* require a restart
- **Backend reload.** `runserver` reloads on Python file changes but
  *not* on settings.py changes — restart manually for those
- **Run tests.** `cd backend && poetry run pytest` (config in
  `pytest.ini`). No frontend tests yet
