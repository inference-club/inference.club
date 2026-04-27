# Plan: Service Manifest (hosts + GPUs + LLM services)

> **Status:** Proposed. Not yet implemented.
>
> **Audience:** the agent working on either this repo or
> `~/git/inference-club-agent`. This document is the contract between
> the two so the feature works end-to-end.

A YAML file on the agent describes the operator's home network — the
hosts they own, each host's GPU, and the LLM services running on each
host. The agent validates the YAML, ships it to inference.club on
register / reload, and the site renders it on a public profile at
`inference.club/<github_login>`.

The YAML is also the single source of truth for the agent's
multi-backend router (Phase 1 of the agent's existing ROADMAP). We
ship one file, not two.

---

## 1. The YAML shape

Mounted at `/etc/inference-club-agent/agent.yaml`. Services live
**inside** their host — a host is the unit, services are what runs
on it.

```yaml
schema_version: 1

agent:
  name: brian-home              # display label + provider lookup key
  hostname: club-host-brian     # tailnet hostname (server may rewrite)
  listen_port: 443

hosts:
  - id: rig-01                  # short, unique within this manifest
    hostname: rig-01.local      # display only
    address: 192.168.1.10       # LAN IP, display only
    gpu:
      vendor: nvidia            # nvidia | amd | apple | intel
      model: RTX 4090
      vram_gb: 24
      count: 1                  # default 1
    notes: "main rig"           # optional, free-form, short
    services:
      - name: rtx-4090-vllm     # router-key: also serves as backend name
        engine: vllm            # vllm | lmstudio | ollama | sglang | llamacpp | tgi | other
        url: http://192.168.1.10:8000/v1
        models:
          - id: qwen3-30b-a3b
          - id: mistral-small-3.1
        command: >              # optional, free-form, for display
          vllm serve Qwen/Qwen3-30B-A3B
          --tensor-parallel-size 1 --max-model-len 32768
        extra: {}               # optional opaque key/value, displayed as a list

  - id: mac-studio
    address: 192.168.1.20
    gpu:
      vendor: apple
      model: M2 Ultra
      vram_gb: 64               # unified memory
      count: 1
    services:
      - name: mac-studio-lmstudio
        engine: lmstudio
        url: http://192.168.1.20:1234/v1
        # no models → server auto-discovers via /v1/models as it does today

  - id: headless-pi             # a host with no services is still valid
    address: 192.168.1.30
    gpu:
      vendor: nvidia
      model: Jetson Orin Nano
      vram_gb: 8
    services: []
```

### Why nested

- The user's mental model is "this box runs these things." A flat
  `services[]` with a `host` foreign key reads correctly to a developer
  but inverts the relationship that matters to the operator. Nesting
  matches how the data is *displayed* on the public profile.
- A host with zero services is a legal state and shows up correctly
  (the box is in the network even if nothing's running yet).
- The router (Phase 1 of the agent ROADMAP) walks
  `hosts[].services[]` to populate its backend table — same data, just
  one extra layer of iteration.

### Field semantics

- `agent.name` is the lookup key used to bind a manifest to a
  `Provider` row server-side. Match the value the operator passed to
  the existing register call, or stick to one name across both.
- `hosts[].id` is unique within this manifest only — it's a stable
  display anchor, not a global ID.
- `services[].name` must be unique across **the whole manifest** (not
  just within one host). It's the key the multi-backend router uses
  and what we display in `owned_by` on aggregated `/v1/models`.
- `services[].url` is the only field the router actually needs to
  forward traffic. Everything else is metadata.
- `services[].models` is optional. If omitted, the central server
  continues to auto-discover via `GET /v1/models` over the tailnet —
  same as today.
- `command` and `extra` are opaque to the agent and the server; they
  exist to give the operator a place to record context that future-them
  will want when looking at the manifest.
- `schema_version: 1` so we can evolve the shape without breaking
  older agents. Server rejects unknown versions with a clear error.

### Backwards compatibility

If no `agent.yaml` is present, the agent synthesizes a single host
(`gpu: unknown`) with one service derived from the existing env vars
(`LOCAL_LLM_URL` etc.). The current single-LLM workflow keeps working
with zero config changes.

---

## 2. Validation

Validation runs in three places — each cheap, each catches a
different failure mode.

**Agent, at startup:**
- `schema_version == 1`.
- `hosts[].id` unique.
- `services[].name` unique across the whole manifest.
- `gpu.vendor` in `{nvidia, amd, apple, intel}`.
- `engine` in `{vllm, lmstudio, ollama, sglang, llamacpp, tgi, other}`.
- Every `services[].url` parses as a URL.
- Manifest within size limits (see §6).

If invalid, the agent logs the validation errors and exits non-zero.
The operator sees them via `docker logs club-host`.

**Agent, via `inference-club-agent doctor` subcommand:**
- All of the above, plus a probe of each `services[].url` to confirm
  it's reachable from inside the container. Catches the most common
  deploy gotcha — forgetting `--add-host` on Linux.

**Server, on receive:**
- Re-validates the parsed structure independently. Never trust the
  agent.
- On validation failure, persists the manifest with `is_valid=False`
  and a list of errors, *and* returns 400 with the same error list.
  Persisting even invalid manifests means the dashboard can show
  "your manifest is broken, here's why" instead of "no manifest yet."

---

## 3. Agent changes (`~/git/inference-club-agent`)

**New deps:** `gopkg.in/yaml.v3` only. No viper.

**New packages:**

- `internal/manifest/manifest.go` — Go structs mirroring the YAML,
  `Load(path) (*Manifest, error)`, `Validate() error`. The structs are
  re-used by the router package later.
- `internal/manifest/upload.go` — `Push(ctx, baseURL, apiKey, m)`
  PUTs the manifest to inference.club. Called after `ensureAuthKey`
  succeeds, and on every reload.

**`main.go` changes:**

- Load YAML at startup (path: `--config` flag → `AGENT_CONFIG_FILE`
  env → `/etc/inference-club-agent/agent.yaml` default).
- If no YAML found, synthesize a one-host / one-service manifest from
  env vars (back-compat path).
- After `ensureAuthKey()` succeeds, call `manifest.Push(...)`.
- On `SIGHUP`: reload the file, re-validate, re-upload. Log clearly
  on each step.

**docker-compose example for the README:**

```yaml
services:
  club-host:
    image: ghcr.io/briancaffey/inference-club-agent:latest
    restart: unless-stopped
    environment:
      INFERENCE_CLUB_API_KEY: ${INFERENCE_CLUB_API_KEY}
    volumes:
      - club-host-state:/var/lib/club-host
      - ./agent.yaml:/etc/inference-club-agent/agent.yaml:ro
volumes:
  club-host-state:
```

The bind mount makes the edit / reload loop a one-liner: edit the
file on the host, `docker kill -s HUP club-host`, watch
`docker logs -f`.

---

## 4. Server changes (`backend/apps/inference/`)

### Model

```python
class ServiceManifest(BaseModel):
    provider = models.OneToOneField(
        Provider, on_delete=models.CASCADE, related_name="manifest"
    )
    schema_version = models.PositiveSmallIntegerField(default=1)
    raw_yaml = models.TextField()        # exactly what the operator wrote
    parsed = models.JSONField()          # validated structured form, for UI
    uploaded_at = models.DateTimeField(auto_now=True)
    is_valid = models.BooleanField(default=True)
    validation_errors = models.JSONField(default=list, blank=True)
```

OneToOne with `Provider` so `provider.manifest` is the natural query.
A user with multiple agents has multiple `Provider` rows and therefore
multiple manifests.

Why store both raw and parsed: parsed is what the UI renders (no YAML
parser in the browser); raw is what the operator uploaded, displayed
verbatim for the owner so they don't have to remember which file
they edited last.

### Endpoints

- `PUT /api/inference/agent/manifest/`
  - Auth: `BearerTokenAuthentication` (same key the agent already uses
    for `/agent/register/`).
  - Body: `{"raw_yaml": "...", "parsed": { ... }}`.
  - Resolves `Provider` by `(request.user, name=parsed.agent.name)`.
  - Server-side validator runs against `parsed`. Always persists; on
    failure returns 400 with `{"errors": [...]}` and sets
    `is_valid=False`.
- `GET /api/inference/providers/<id>/manifest/`
  - Auth: owner only. Returns `raw_yaml + parsed + status`.
- `GET /api/users/<github_login>/`
  - **Public, no auth.** Looks up user by GitHub login via the
    `social_auth` reverse manager (same trick `PublicProviderSerializer`
    already uses). Returns: display name, avatar, `github_login`,
    joined date, and a list of `{provider, manifest.parsed}` for
    `is_active=True` providers.
  - 404 if no user matches that login.

### Validator

`apps/inference/manifest_validator.py` — pure-Python, mirrors the
agent's checks. No YAML parsing server-side; the agent ships parsed
JSON and we validate the structure. Hand-rolled is fine for the field
count we have.

### Migrations

Single additive migration. No backfill needed.

---

## 5. Frontend changes (`frontend/`)

### Public profile page

**New file:** `pages/[username].vue`. Top-level dynamic route. Catches
`/<anything>` so it must come *after* all named sibling routes;
Nuxt's file-based routing already gives that ordering as long as
`dashboard/`, `docs/`, `blog/`, `login/`, `sign-up/`, `models/`,
`terms-of-service/` exist as siblings (they do).

Layout (Tailwind + shadcn-nuxt, matching `pages/index.vue`):

- Header: GitHub avatar, `@<login>` linked to
  `https://github.com/<login>`, joined date.
- One section per `Provider`:
  - Provider name + `is_online` status pill (already on the serializer).
  - One card per host showing:
    - hostname + LAN IP
    - GPU vendor badge, GPU model, VRAM
    - notes
    - a list of services, each rendered with:
      - engine badge, service name
      - model chips (or "auto-discovered" placeholder)
      - `command` in a collapsible `<pre>` block
      - `extra` as a key/value list

- "View raw manifest" → modal showing `raw_yaml`, **owner only**.
  Easy gate: the public payload simply omits `raw_yaml`.

### Dashboard page

**New file:** `pages/dashboard/manifest/index.vue`. Shows the
most-recently-uploaded manifest's raw YAML, validation status,
validation errors (if any), and `uploaded_at` per provider. No
in-browser editing — the YAML is edited on the agent host and
SIGHUP'd in. Single source of truth.

### Composable

`composables/useManifest.ts` — wraps the two endpoints above,
matches the `useFetch`/`apiBase` patterns used elsewhere.

---

## 6. Limits

To keep the public profile from becoming a target, the validator
enforces:

- raw YAML ≤ 64 KB
- ≤ 50 hosts
- ≤ 100 services total
- per-string fields ≤ 1 KB each (`command`, `notes`, `extra` values)

Cheap to enforce, plenty of headroom for any real home network.

---

## 7. Out of scope (called out so we don't drift)

- **GPU auto-detection.** All GPU info is hand-entered. No
  `nvidia-smi` parsing, no SMC poking, no ROCm shelling. Auto-detect
  is its own project.
- **Service auto-detection.** Same — `inference-club-agent doctor`
  can probe known ports as an *aid* to writing the YAML, but it
  doesn't write the file.
- **Editing the manifest from the dashboard.** The YAML on the
  agent host is the source of truth. A web editor that round-trips
  through the agent is interesting but a different feature.
- **Non-LLM services.** Same scope cut as the agent ROADMAP — TTS,
  image gen, embeddings all wait until the LLM path is solid.

---

## 8. Sequencing — three PRs

Each PR is independently mergeable; the feature lights up at the end
of PR 2.

**PR 1 — backend:**
model, migration, validator, three endpoints,
`PublicProviderSerializer` extension, public-profile view. Ships
with a JSON-only stub on the frontend (just dumps the API response)
so the shape can be sanity-checked before we design the UI.

**PR 2 — agent:**
`internal/manifest/` package, YAML loader with env-var fallback,
validator, upload-on-register, SIGHUP reload, `doctor` subcommand
for local validation. Drops an example `agent.yaml` into the repo
and updates the README's docker-compose snippet to bind-mount it.
*At the end of PR 2 the feature works end-to-end* — the public
profile renders real manifests.

**PR 3 — frontend polish:**
real `pages/[username].vue` styling, `dashboard/manifest/`,
raw-YAML modal for owners. UI-only.

The agent ROADMAP's Phase 1 multi-backend router slots in
*after* PR 2 (or alongside it) — the YAML shape was designed to
support both, and the same `hosts[].services[]` data feeds the
router.

---

## 9. Open calls to settle before implementation

1. **Manifest auth.** Above, the agent uses the user's
   `INFERENCE_CLUB_API_KEY` (Bearer) to upload. With multiple agents
   per account, that key gives any agent write access to *any* of
   that user's manifests. Alternative: a per-provider token returned
   at registration time. Lean: keep one token for now (matches the
   existing surface); revisit when someone runs >1 agent per account.
2. **`/<username>` route conflict.** A top-level dynamic route
   swallows any future top-level path that isn't a named sibling.
   Alternative: namespace under `/u/<username>`. Cleaner routing,
   uglier share link. Lean: top-level for the share link, with a
   route-collision lint check in CI as a safety net.
3. **Schema evolution.** `schema_version: 1` is in the file; we
   reject anything else. When we bump it, do we keep parsing v1 too,
   or force agents to upgrade in lockstep? Lean: server keeps a
   small set of accepted versions; agent always emits the newest it
   knows. Decide concretely when v2 is on the table.
