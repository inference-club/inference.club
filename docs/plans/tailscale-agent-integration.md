# Plan: Tailscale-based agent integration

> **Status:** Implemented (April 2026). End-to-end inference is working
> through the design described below. Kept in-repo as a historical record
> of the design decision and as the canonical contract between this repo
> and `inference-club-agent`. Future changes to that contract should
> update this document and both implementations together.
>
> **Original audience:** the agent working on this repo. The matching
> home-side agent exists at `~/git/inference-club-agent` (single-purpose
> Go binary using embedded `tsnet`). This document is the contract the
> server side implements so the agent works end-to-end.

> **Decision:** **option B — replace**. The existing
> `Provider.callback_url` + `AgentHeartbeatView` design (agent exposes a
> publicly-reachable URL and posts heartbeats to be considered online) is
> being replaced wholesale by a Tailscale-based design. The server reaches
> agents over a private tailnet using MagicDNS hostnames; nothing the
> agent runs needs to be on a public URL or behind port-forwarding.

---

## What the agent does today (already merged in `~/git/inference-club-agent`)

Single Go binary, distributed as a Docker image. On boot:

1. If no Tailscale auth key is cached on disk, **POST**
   `${INFERENCE_CLUB_URL}/api/inference/agent/register/`
   with `Authorization: Bearer <user's INFERENCE_CLUB_API_KEY>` and JSON body:
   ```json
   { "name": "<friendly label>",
     "tailnet_hostname": "<requested hostname>",
     "agent_port": 443 }
   ```
   Expected `200`/`201` response shape:
   ```json
   { "provider_id": 17,
     "tailscale_authkey": "tskey-auth-...",
     "tailnet_hostname": "club-host-17",
     "tailscale_login_server": "" }
   ```
2. Persist `tailscale_authkey` to `${AGENT_STATE_DIR}/authkey`.
3. Start `tsnet` with that key, listen on `:443` inside the tailnet.
4. Reverse-proxy `/v1/*` to a local OpenAI-compatible server
   (`LOCAL_LLM_URL`, default `http://host.docker.internal:1234/v1`).
5. Also serves `GET /healthz` returning `200 ok` for liveness probes.

The agent never reports models — the server discovers them by hitting
`https://<tailnet_hostname>/v1/models` when needed.

The agent does **not** post heartbeats. The server treats a provider as
online if it can reach `/healthz` over the tailnet (see §6 below).

---

## Server-side work (this repo)

Everything below is in `backend/apps/inference/` unless noted. The
`apps.accounts` `BearerTokenAuthentication` already handles
`Authorization: Bearer <token>` against the existing
`rest_framework.authtoken.Token` model, which is what we re-use as
`INFERENCE_CLUB_API_KEY`. No new auth code needed.

### 1. `Provider` model migration (`models.py`)

Replace `callback_url` and the heartbeat fields with tailnet fields.

```python
class Provider(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=CASCADE,
                             related_name="providers")
    name = models.CharField(max_length=128)

    # NEW
    tailnet_hostname = models.CharField(max_length=255, blank=True)
    agent_port = models.PositiveIntegerField(default=443)
    last_seen_at = models.DateTimeField(null=True, blank=True)  # bumped on
                                                                # successful proxy
    registered_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_on"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name"],
                                    name="unique_provider_name_per_user"),
        ]
```

Drop: `callback_url`, `last_heartbeat_at`, `PROVIDER_HEARTBEAT_TIMEOUT`.

`is_online` becomes a property derived from `last_seen_at` (within e.g.
2 min) plus an active flag, **or** a synchronous reachability probe — see
§6 for the recommendation.

Add a helper:

```python
@property
def tailnet_base_url(self) -> str:
    if not self.tailnet_hostname:
        return ""
    if self.agent_port == 443:
        return f"https://{self.tailnet_hostname}/v1"
    return f"http://{self.tailnet_hostname}:{self.agent_port}/v1"
```

`ProviderModel` is unchanged in shape but is now populated by the
server-side discovery flow (§4), not the agent.

Migration: `makemigrations inference` will produce a single migration that
drops `callback_url`/`last_heartbeat_at` and adds the new fields. Since
no real prod data exists yet (still pre-launch), no data migration is
needed — feel free to wipe the dev DB.

### 2. New endpoint: `POST /api/inference/agent/register/`

Add to `urls.py`:

```python
path("agent/register/", AgentRegisterView.as_view(), name="agent-register"),
```

(Drop the existing `path("agent/heartbeat/", ...)` entirely.)

View (`views.py`):

```python
class AgentRegisterView(APIView):
    """Agent calls this on first run; returns a Tailscale auth key the
    agent uses to join the inference.club tailnet."""

    permission_classes = [IsAuthenticated]   # Bearer token auth

    @transaction.atomic
    def post(self, request):
        ser = AgentRegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        provider, _ = Provider.objects.update_or_create(
            user=request.user,
            name=data["name"] or "club-host",
            defaults={
                "tailnet_hostname": data["tailnet_hostname"],
                "agent_port": data.get("agent_port", 443),
                "is_active": True,
                "registered_at": timezone.now(),
                "last_seen_at": timezone.now(),
            },
        )

        # Make the hostname canonical: if the agent asked for "club-host"
        # but we want one per-provider (so multiple agents don't collide
        # in the tailnet), rewrite to a deterministic name:
        canonical = f"club-host-{provider.id}"
        if provider.tailnet_hostname != canonical:
            provider.tailnet_hostname = canonical
            provider.save(update_fields=["tailnet_hostname", "modified_on"])

        minted = mint_authkey_for_provider(provider)

        return Response({
            "provider_id": provider.id,
            "tailscale_authkey": minted.authkey,
            "tailscale_login_server": minted.login_server,
            "tailnet_hostname": provider.tailnet_hostname,
        }, status=status.HTTP_200_OK)
```

Serializer (`serializers.py`):

```python
class AgentRegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128, required=False, allow_blank=True)
    tailnet_hostname = serializers.CharField(max_length=255, required=False, allow_blank=True)
    agent_port = serializers.IntegerField(required=False, default=443,
                                          min_value=1, max_value=65535)
```

Drop `HeartbeatSerializer` and `HeartbeatModelSerializer`.

### 3. Tailscale auth-key minting (new file `tailscale.py`)

```python
"""Mint Tailscale auth keys for provider agents.

Production: Tailscale OAuth client (mints fresh ephemeral keys per agent).
Bootstrap: a single static reusable+ephemeral key, returned for every
register call. Lets us iterate before the OAuth client is provisioned.
"""

from dataclasses import dataclass
import requests
from django.conf import settings


@dataclass
class MintedKey:
    authkey: str
    login_server: str = ""


def mint_authkey_for_provider(provider) -> MintedKey:
    if settings.TAILSCALE_OAUTH_CLIENT_ID and settings.TAILSCALE_OAUTH_CLIENT_SECRET:
        try:
            return _mint_via_oauth(provider)
        except Exception:
            # Fall through to the static-key fallback so a misconfigured
            # OAuth client doesn't permanently brick registration.
            ...
    if settings.TAILSCALE_STATIC_AUTHKEY:
        return MintedKey(authkey=settings.TAILSCALE_STATIC_AUTHKEY)
    return MintedKey(authkey="")


def _mint_via_oauth(provider) -> MintedKey:
    token_resp = requests.post(
        "https://api.tailscale.com/api/v2/oauth/token",
        data={
            "client_id": settings.TAILSCALE_OAUTH_CLIENT_ID,
            "client_secret": settings.TAILSCALE_OAUTH_CLIENT_SECRET,
        },
        timeout=10,
    )
    token_resp.raise_for_status()
    access = token_resp.json()["access_token"]

    tailnet = settings.TAILSCALE_TAILNET or "-"
    resp = requests.post(
        f"https://api.tailscale.com/api/v2/tailnet/{tailnet}/keys",
        headers={"Authorization": f"Bearer {access}"},
        json={
            "capabilities": {"devices": {"create": {
                "reusable": False,
                "ephemeral": True,
                "preauthorized": True,
                "tags": [settings.TAILSCALE_HOST_TAG],
            }}},
            "expirySeconds": 900,
            "description": f"club-host-{provider.id} ({provider.user.email})",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return MintedKey(authkey=resp.json()["key"])
```

### 4. Discover models from the agent

Two places this runs:

- **Synchronously, in the proxy**, on first proxy attempt after registration
  if no `ProviderModel` rows exist for the provider yet (cheap and
  self-healing).
- **On demand**, via a new endpoint
  `POST /api/inference/providers/<id>/refresh-models/` so the UI can
  trigger a refresh.

Helper:

```python
def refresh_provider_models(provider) -> int:
    if not provider.tailnet_base_url:
        return 0
    resp = requests.get(
        provider.tailnet_base_url.rstrip("/") + "/models",
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("data") or payload.get("models") or []

    incoming = {row["id"]: row for row in rows if row.get("id")}
    existing = {pm.name: pm for pm in provider.models.all()}

    # Soft-replace: deactivate ones the agent no longer reports, upsert the rest.
    for name, pm in existing.items():
        if name not in incoming and pm.is_active:
            pm.is_active = False
            pm.save(update_fields=["is_active", "modified_on"])
    for name in incoming:
        defaults = {"is_active": True}
        ProviderModel.objects.update_or_create(
            provider=provider, name=name, defaults=defaults,
        )
    return len(incoming)
```

The reachability is over the tailnet, so the backend container needs to
be on the tailnet too (see §7).

### 5. OpenAI proxy changes (`openai_views.py`)

Two small edits:

1. Replace `provider.callback_url.rstrip("/") + self.upstream_path` with
   `provider.tailnet_base_url.rstrip("/") + self.upstream_path`.
2. After a successful upstream call, bump `last_seen_at`:
   ```python
   Provider.objects.filter(id=provider.id).update(last_seen_at=timezone.now())
   ```
3. In `_find_provider_for_model`, gate on `provider.tailnet_hostname`
   being non-empty (treat unregistered providers as offline).

### 6. `is_online` semantics

Two acceptable approaches; pick one:

- **Recommended (cheap, tolerates flapping):** `is_online` = `is_active AND
  last_seen_at within last 2 min`. `last_seen_at` is bumped by §5. Add a
  background Celery beat task (or a periodic systemd timer) that probes
  `/healthz` over the tailnet every 30s for providers with no recent
  activity, so an idle-but-up provider doesn't appear offline. This is
  what most production setups do.
- **Simpler interim:** synchronous probe in the `/v1/models` and
  `/providers/` endpoints when serializing — `is_online` does a 2s GET
  to `/healthz`. Fine while there are <50 providers per request; doesn't
  scale to many.

This repo doesn't currently have Celery wired up, so the **synchronous
probe** is the easier first step. Switch to the periodic-probe model
once Celery (or a cheaper alternative like a thread-pool background
worker triggered by Django) is added.

### 7. Tailscale sidecar in production compose template

In `infra/templates/docker-compose.yml.tpl`, add:

```yaml
  tailscale:
    image: tailscale/tailscale:stable
    restart: unless-stopped
    hostname: club-web
    environment:
      TS_AUTHKEY: __TAILSCALE_WEB_AUTHKEY__
      TS_HOSTNAME: club-web
      TS_USERSPACE: "true"
      TS_STATE_DIR: /var/lib/tailscale
      TS_EXTRA_ARGS: "--advertise-tags=tag:club-web"
      TS_SOCKS5_SERVER: ":1055"
      TS_OUTBOUND_HTTP_PROXY_LISTEN: ":1055"
    volumes:
      - /srv/inference-club/tailscale-state:/var/lib/tailscale
```

And on the `backend` service, route outbound HTTP traffic via the sidecar:

```yaml
  backend:
    ...
    environment:
      HTTPS_PROXY: socks5h://tailscale:1055
      HTTP_PROXY: socks5h://tailscale:1055
      NO_PROXY: localhost,127.0.0.1,postgres,frontend,caddy
```

(Add the matching keys to `infra/templates/backend.env.tpl` as well, OR
inline them in the compose env block.)

### 8. New env vars

Add to `backend/backend/settings.py`:

```python
TAILSCALE_TAILNET = os.environ.get("TAILSCALE_TAILNET", "-")
TAILSCALE_OAUTH_CLIENT_ID = os.environ.get("TAILSCALE_OAUTH_CLIENT_ID", "")
TAILSCALE_OAUTH_CLIENT_SECRET = os.environ.get("TAILSCALE_OAUTH_CLIENT_SECRET", "")
TAILSCALE_HOST_TAG = os.environ.get("TAILSCALE_HOST_TAG", "tag:club-host")
TAILSCALE_STATIC_AUTHKEY = os.environ.get("TAILSCALE_STATIC_AUTHKEY", "")
```

Add to `infra/templates/backend.env.tpl`:

```
TAILSCALE_TAILNET=__TAILSCALE_TAILNET__
TAILSCALE_OAUTH_CLIENT_ID=__TAILSCALE_OAUTH_CLIENT_ID__
TAILSCALE_OAUTH_CLIENT_SECRET=__TAILSCALE_OAUTH_CLIENT_SECRET__
TAILSCALE_HOST_TAG=tag:club-host
```

Add corresponding Pulumi config keys in `infra/config.ts` and document them
in `infra/README.md` under "Required secrets".

### 9. Tailscale ACL (one-time manual step in Tailscale admin)

In your tailnet's Access Controls panel, replace the default policy with:

```jsonc
{
  "tagOwners": {
    "tag:club-host": ["autogroup:admin"],
    "tag:club-web":  ["autogroup:admin"]
  },
  "acls": [
    // backend may reach agents on their listen port only
    { "action": "accept", "src": ["tag:club-web"], "dst": ["tag:club-host:443"] }
  ],
  "ssh": []
}
```

This keeps agents from ever talking to each other or to anything other
than the central web service.

### 10. Frontend: `/providers/my-nodes`

In `frontend/composables/useProviders.ts` and the page template:

- Replace the `callback_url` field on the `Provider` interface with
  `tailnet_hostname` (string) and `agent_port` (number).
- Drop `last_heartbeat_at` from the interface; show `last_seen_at` instead
  (relative time formatting can be reused).
- The empty-state copy already says "Run `inference-club-agent` …" — keep
  it but update the example to match the agent's new env var names
  (`INFERENCE_CLUB_API_KEY`, `LOCAL_LLM_URL`). Linking to the agent repo's
  README is the simplest:
  https://github.com/briancaffey/inference-club-agent
- Add a "Refresh models" button per-card that POSTs to
  `/api/inference/providers/<id>/refresh-models/`.

### 11. Tests

- Update existing heartbeat tests in `apps/inference/tests/` to be
  registration tests.
- Add a test for `mint_authkey_for_provider` that exercises both
  fallback paths (mock the requests library).
- Add a test for `refresh_provider_models` (mock the HTTP call to the
  agent's `/v1/models`).
- Update OpenAI-proxy tests to set `tailnet_hostname` instead of
  `callback_url` on test fixtures (`apps/inference/factories.py`).

### 12. Frontend env vars / docs

No frontend env vars need to change for this work. The README links to
the agent repo, so update `frontend/content/blog/...` if there's an
"Operating a node" post that mentions `callback_url` (search for that
string).

---

## Acceptance criteria (end-to-end)

1. `docker compose up` produces a backend that boots cleanly with the new
   `Provider` schema (no `callback_url`).
2. With a valid `TAILSCALE_STATIC_AUTHKEY` in the backend env and a
   running agent on a separate machine, the agent's first start results
   in a `Provider` row appearing under the user, with the agent reporting
   `serving on tailnet port 443` in its logs.
3. `GET /api/inference/providers/` returns the new shape (`tailnet_hostname`,
   `agent_port`, `is_online`, `last_seen_at`).
4. `POST /api/inference/providers/<id>/refresh-models/` populates
   `ProviderModel` rows from the agent's `/v1/models`.
5. `GET /v1/models` (with the user's API key as Bearer) lists the agent's
   models.
6. `POST /v1/chat/completions` (Bearer) streams a real completion through
   the central server → tailnet → agent → local LLM and back. Verified
   with `openai` Python SDK pointed at `https://inference.club/v1`.
7. The deployment runs on Hetzner with the `tailscale` sidecar joined to
   the tailnet as `club-web`.

---

## Out of scope for this PR (good follow-ups)

- Multiple consumer API keys per user (today there's one `Token` per user).
- Provider load-balancing / fallback when multiple providers serve the same
  model.
- Rate limiting per consumer key.
- Switching to Headscale (the agent already accepts a
  `TAILSCALE_LOGIN_SERVER` override, so this is a server-side flip later).
- Heartbeat-style background probing via Celery (see §6).
- Billing / usage accounting (the existing `InferenceRequest` table is
  the right place to start).

---

## Reference: matching agent code

`~/git/inference-club-agent/main.go`:
- Line ~30 has the env-var docs the agent reads.
- `register()` function: the exact request shape and headers.
- `registerResponse` struct: the exact response shape it expects.

If the server side ever needs to evolve the contract, those are the
fields to keep in sync.
