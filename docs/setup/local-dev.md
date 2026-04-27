# Local dev

Running the inference.club stack on your laptop.

The fast loop is plain `manage.py runserver` + `yarn dev` — no Docker,
no Tailscale required, just enough to iterate on Django views and
Nuxt pages. The full prod-like loop with `docker compose` is also
documented for when you need to verify a containerized change.

## Ports

The dev stack uses non-default ports so it can coexist with whatever
else might be listening on your machine — Docker Desktop in particular
holds `*:3000` and `*:5432` on this machine.

| Service | Dev port | Prod port |
|---|---|---|
| Nuxt frontend | 3001 | 3000 (inside container) |
| Django backend | 8001 | 8001 |
| Postgres | 5432 (local SQLite by default) / 5532 (compose) | 5432 (inside container) |

The frontend's `apiBase` is `http://localhost:8001` (set in
`frontend/nuxt.config.ts`). If you change the backend port in dev,
update that too.

## Fast loop (what you'll use day to day)

Two terminals, no Docker:

```bash
# terminal 1: backend
cd backend
poetry install                  # one-time
poetry run python manage.py migrate
poetry run python manage.py runserver 8001

# terminal 2: frontend
cd frontend
yarn install                    # one-time
yarn dev --port 3001
```

Backend uses SQLite at `backend/db.sqlite3` by default — no Postgres
needed. The Django settings module supports `DATABASE_URL` via
`dj-database-url` if you want to point at a real Postgres.

For GitHub OAuth in dev, set up a dev OAuth app per
[github-oauth.md](github-oauth.md#dev-app) and put the credentials
in `backend/.env` (gitignored).

## Prod-like loop (`docker compose up`)

The repo-root `docker-compose.yml` builds the same images CI publishes
and runs them with Postgres. Useful for verifying a containerized
change *before* it touches the real prod box.

```bash
docker compose up -d --build
docker compose logs -f backend
```

Then:
- Backend at <http://localhost:8101/admin/login/>
- Frontend at <http://localhost:3100/>

This compose file uses **alternate host ports** (8101 / 3100 / 5532)
so it can coexist with the fast-loop processes above. Compose is for
*verifying* the container; the fast loop is for *iterating*.

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
- **Reset the dev DB.** `rm backend/db.sqlite3 && poetry run python
  manage.py migrate` — fast and lossless since you'll re-seed via
  the snippet above
- **Frontend hot reload.** Nuxt picks up changes to `pages/`,
  `components/`, `composables/`, and `content/` without a restart.
  `nuxt.config.ts` and `app.config.ts` *do* require a restart
- **Backend reload.** `runserver` reloads on Python file changes but
  *not* on settings.py changes — restart manually for those
- **Run tests.** `cd backend && poetry run pytest` (config in
  `pytest.ini`). No frontend tests yet
