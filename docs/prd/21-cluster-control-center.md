# PRD 21 — Cluster Control Center (park, unpark & place inference services from one pane of glass)

> **Status:** Drafted (2026-07-09), not started. Turn the read-only cluster
> pages into a simple **operational control center**: one mobile-first surface,
> plain clean cards, where the operator sees at a glance **what is running on
> which box, what is parked, how much GPU memory is free, and whether the next
> service will fit** — and can **start / stop (park / unpark)** an inference
> service, and later **move** it to another box, to bin-pack the fleet by hand.
> It is **owner-only** and **opt-in**, and it works identically from the public
> **inference.club** and the in-cluster **club.lan** copy, because both talk to
> the same agent and the same cluster.
>
> **Scope note (kills a real confusion):** this is about the **inference
> *services*** — the cluster control plane, the Deployments that host the models
> — **not** the *results* of inference. Each app instance keeps its own database
> and shows its own generated content; the control center is a shared window onto
> the one cluster underneath. See §4.
>
> **Builds on:** the read-only cluster stack — `Provider` (owner-scoped, already
> carries the agent dial host/port), `Host`/`Gpu`/`ProviderService`/
> `ResourceGroup`/`ManifestRevision` (PRD 07), the agent `GET /cluster/state`
> proxy + `vram-reporter` per-service VRAM, the activity/history proxies, and the
> UI kit (`MachineCard`, `MachineSummary`, `VramSparkline`, `ReadinessDot`,
> `ProviderMachineGrid`, `useClusterState`). It lands on top of the PRD 20
> homelab deploy (the `club.lan` in-cluster app, Harbor/Forgejo/Argo GitOps) and
> the version surface it added.
>
> **Author:** Brian (product direction) · drafted with Claude Code.

> **Cross-repo contract — keep in sync.** This is the first feature that
> **writes to the cluster**, so it spans four repos. Nothing here ships in one
> repo alone (verified current state in §6):
>
> - **agent** (`inference-club-agent`): its **first-ever inbound-authed route**
>   `POST /cluster/services/{name}/scale` (V1) and `.../move` (V2); a **write
>   path to the kube API** (today the k8s helper is GET-only, raw REST, in-cluster
>   SA token) that PATCHes `deployments/{name}/scale`; a `GET /version` for
>   compatibility; and a `desired`/`actual` shape in `GET /cluster/state`.
> - **agent chart** (`inference-club-agent/charts/.../templates/rbac.yaml`): a new
>   `Role` granting `apps/deployments` + `deployments/scale` `get,list,patch` in
>   ns `inference-club`, bound to SA `agent-inference-club-agent` (today: entirely
>   read-only). Committed as code — see [[feedback_infra_in_repo_not_imperative]].
> - **backend** (`inference.club`): opt-in flag + agent-auth secret on `Provider`,
>   `desired_state`/`expected_vram_gb`/candidate-boxes on `ProviderService`, a
>   `ServiceAction` audit model, owner-only actuation views that proxy to the
>   agent, and a reconcile/poll loop.
> - **frontend** (`inference.club`): the Control Center hub — simple tight cards,
>   **no 3D** — that consolidates the scattered cluster pages and adds park/unpark,
>   a fit preflight, a box picker, and an action feed.

---

## 1. Summary

The single biggest day-to-day pain running the home fleet is **bin-packing GPU
memory by hand**: which model is up on which box, what's parked, how much VRAM is
left, and what has to be stopped before the next thing will fit. Today that is a
`kubectl scale` headache across a1/a2/a3/spark — park one model to free VRAM,
unpark another, squint at `nvidia-smi`, repeat. The app can *show* the fleet but
cannot *touch* it: PRD 07 made "no actions on the cluster" an explicit non-goal,
and a repo-wide search confirms there is **no cluster write path anywhere** yet.

This PRD adds the missing operational half — kept deliberately simple. It reuses
the rich telemetry we already collect but reframes it around the three questions
the operator actually asks — **Is it up? Will it fit? Is it busy?** — and gives
one-tap **park / unpark** control over each inference service, VRAM-fit-aware,
from a phone or a browser, plus a later **move-to-another-box** action.

The mental model is a small **control plane**: Django holds the **desired state**
(should this service be running, and on which box), the agent reports the
**actual state** (pods, node conditions, live VRAM), the control center shows both
and highlights **drift**, and changing desired state actuates through the agent
until actual converges. The home platform is *already built for this*: Argo CD is
configured to ignore Deployment replica counts precisely so that park/unpark is
operator-owned, not git-owned (§6).

This PRD is deliberately **manual** — the human does the bin-packing. Automatic
scheduling from request demand, and agent-driven placement (Hermes and friends),
are a **future PRD** (§10). Ship manual control first, live with it, then
automate what proves tedious.

## 2. Goals & non-goals

**Goals**

1. **One simple pane of glass.** Consolidate the scattered cluster/nodes/services
   pages into a single **Control Center** of plain, tight, information-dense
   cards — mobile-first, live-updating, not overwhelming, **no 3D**.
2. **Park / unpark inference services** from the UI — **strictly on/off: replicas
   0 or 1, never higher.** This is not replica autoscaling; a model service is one
   GPU-bound pod that's either running or not. Unparking carries a **fit preflight**
   so you know before you tap whether it lands.
3. **Show the whole roster** — running *and* parked (scaled-to-zero) services —
   so you can see what's *possible* to run, not just what's up right now.
4. **Make bin-packing legible.** Every box shows its VRAM budget (total / used /
   free); every service shows its VRAM footprint (live when running, *expected*
   when parked).
5. **Answer "what can run where."** Per service, show the **boxes it can run on**
   (its candidates) and let you **move** it there — hiding the taint/affinity
   machinery behind a simple box picker (§5.4).
6. **Owner-only & opt-in.** Only the provider's owner can control it; a per-provider
   opt-in switch turns cluster control on at all. Make it **obvious in the UI which
   cluster/agent you are pointed at** (§4).
7. **Same behavior everywhere** — identical from public `inference.club` and
   in-cluster `club.lan`; both actuate the same agent.
8. **Auditable & safe.** Every action is attributed and logged; parking a service
   that's actively serving warns first.

**Non-goals**

- **No auto-scheduling / demand-based placement** here — deferred (§10). Manual only.
- **No 3D visualization** in this feature. The existing `cluster/Scene.vue` stays
  as a separate showpiece; the control center is the fast operational view.
- **Not a general kubectl/k9s replacement.** It operates the *inference services we
  declared in the manifest*, not arbitrary workloads, pods, or namespaces.
- **Not about inference results.** It does not touch generated content, requests,
  or per-app databases (§4).
- **No cluster provisioning** (adding nodes, drivers, Longhorn). Declared via the
  existing manifest flow.
- **No new metrics pipeline.** We reuse `vram-reporter` + `/cluster/state` and
  **deep-link into existing Grafana** (NodePort 30030) for the heavy telemetry
  instead of re-plotting it.

## 3. The three questions (design north star)

Everything on a card answers one of three questions; anything else is one tap
deeper (drawer) or a link out (Grafana). This is how we "use all the data without
overwhelming."

- **Is it up?** — `ReadinessDot` state (running / parked / starting / stopping /
  failed / drift) + which box.
- **Will it fit?** — the box's free VRAM vs. the service's live/expected footprint,
  as a green/amber/red preflight on the unpark/move button.
- **Is it busy?** — trailing-hour request activity (we already bucket this).

## 4. Topology: many apps → one agent each → one cluster (resolving base-URL / API-key)

The confusion to put to rest, and the shape we're committing to. There are
**several inference.club app instances**, each with its **own database and its own
generated content**, and they will grow:

- **production** `inference.club` (Hetzner) — public sign-ups, also used by Brian;
- **in-cluster** `club.lan` (namespace `inference-club-web`, own DB `inferenceclub`,
  email-only auth) — the PRD 20 homelab deploy, in progress;
- **local dev** — the docker-compose environment on the laptop;
- …and likely more later.

They all need to **see and control the one home cluster**. The confusing idea —
one app switching its "base URL" to peer into another app's data, or mixing
inference *results* across apps — is **out**; each app keeps its own DB and shows
its own content. What's shared is the **cluster underneath**, and the way each app
reaches it is **its own inference-club agent**.

### 4.1 One agent per environment (recommended)

Give each environment its own agent rather than funnelling every app through one
shared agent. Concretely, run a small fleet of `inference-club-agent` containers
in (or reachable from) the cluster, one per environment — e.g. `club-agent-prod`,
`club-agent-lan`, `club-agent-dev` — each with **its own inbound API key** and its
own **`Provider` registration** in the app that owns it. Why this, not one shared
agent:

- **They all talk to the same Kubernetes cluster, and that's fine.** k8s is the
  single source of truth and serialises writes; if prod tells its agent "unpark
  service X," it happens, and the moment `club.lan`'s pane of glass next reads the
  cluster it shows X running. Multiple clients commanding one cluster is a normal,
  safe pattern — the reconciliation lives in k8s, not in our apps (§7).
- **Independent failure domains.** The dev agent — actively hacked on, restarted
  and broken often — must never take down prod's control path.
- **Per-environment credentials & blast radius.** Rotating or revoking one
  environment's key touches only that environment; the laptop dev path can even
  get narrower RBAC than prod.
- **Clean attribution.** Each agent stamps every action with its environment, so
  every pane of glass can show "unparked by *prod* 2m ago" (§4.3).

The auth work is identical either way, so this does **not** foreclose consolidating
to one agent + multiple keys later if the fleet feels like too many containers —
but per-environment agents are the recommended default and match how `Provider`s
already work (each app registers its own).

> **The one topology decision to confirm before V1.** Starting with a single shared
> agent (fewer moving parts) and splitting later is a valid fallback; the *only*
> difference is how many agent Deployments + keys we create — the app-side and RBAC
> design are the same.

### 4.2 Reaching the agent — dial config per environment

The agent is the **universal write path**: even `club.lan`, which runs inside the
cluster, actuates *through* its agent rather than hitting the kube API itself, so
there is **one code path everywhere**. How each app dials its agent differs, so the
`Provider` connection must support both:

- **`club.lan` → ClusterIP / in-cluster DNS** (e.g. `club-agent-lan.inference-club.svc:PORT`)
  over plain HTTP — **no tailnet, no SOCKS** (confirmed by Brian). This is
  **net-new**: `Provider` today assumes a tailnet dial via the SOCKS proxy, so it
  needs a **direct-dial mode** (the agent already supports `AGENT_DIRECT` plain HTTP).
- **prod & local-dev → tailnet** (SOCKS via `tailnet_addr` : `agent_port`), as today.

The UI **always shows which agent/cluster it is pointed at** ("Controlling:
*club-agent-lan* · 4 boxes · agent v1.x") and checks **agent↔app version
compatibility** before enabling actions.

### 4.3 Naming & labelling spec (no ambiguity)

With several agents against one cluster, naming must be rigorous:

- **Agent identity** = `AGENT_NAME` per environment (`club-agent-{prod,lan,dev}`),
  which is also its `Provider.name` in the owning app.
- **Inbound key** = one Kubernetes `Secret` per environment; the matching secret is
  stored on that app's `Provider` and sent as `Authorization: Bearer` on writes.
- **Action attribution on the cluster itself**: every scale/move stamps annotations
  on the target Deployment — `inference-club.com/last-scaled-by: <env>`,
  `inference-club.com/last-scaled-at: <ts>`, `inference-club.com/last-action: park|unpark|move`.
  Because every environment reads these back in `/cluster/state`, **all panes of
  glass show a consistent "who last touched this," regardless of which app did it.**
  This is what makes the multi-writer story feel coherent instead of chaotic.

### 4.4 Actuation path & auth

```
Control Center (phone / browser, owner only)
  → POST /api/providers/<id>/services/<name>/scale {desired: running|parked}   (Django, owner-only)
     → agent POST /cluster/services/<name>/scale {replicas: 0|1}               (tailnet SOCKS, Bearer <agent secret>)
        → k8s PATCH /apis/apps/v1/namespaces/inference-club/deployments/<name>/scale   (agent SA, new RBAC)
  ← desired persisted; poll /cluster/state until actual converges
```

- **Owner-only** in Django (provider owner); no other user can see or actuate
  another person's cluster. **Opt-in**: a `Provider.cluster_control_enabled` flag
  gates the whole feature per provider (default off).
- **Agent inbound auth is net-new** — the agent enforces *zero* inbound auth today
  (trust = tailnet). The mutation endpoint requires a **shared secret** (stored on
  the `Provider`, sent as Bearer); reads may stay tailnet-trusted or get the same
  guard (§10 Q).
- **RBAC is net-new** — the agent SA is read-only today; we add `deployments/scale`
  `patch` in ns `inference-club` (§6).
- **Command + observe, no auto-heal** — the app issues the scale once, then polls
  `/cluster/state` and flips `starting → running` from what it *sees*; it does not
  re-assert desired in a loop (§7 — multiple apps write the same cluster). Because
  Argo ignores `/spec/replicas`, GitOps won't revert the change either.

## 5. Bin-packing & placement

### 5.1 Per-box headline metrics: memory + utilization

Every box card leads with the **two measurements we already collect** — the same
ones shown per-service today, rolled up to the box:

- **GPU memory** — per box, **total / used / free** VRAM (used = sum of live
  per-service `vram-reporter` VRAM + safety headroom), labeled with **absolute GB
  free** on the existing `MachineCard` gauge. Free VRAM is what the fit-check (§5.3)
  reads.
- **GPU utilization** — how hard the box is actually working right now (the DCGM /
  `nvidia-smi` utilization already in `/cluster/state`), as a small percent/bar.

Those two, side by side, are the at-a-glance "is this box busy, and does it have
room?" that the whole board is built around. Everything else about a box is one tap
deeper or a link to Grafana.

### 5.2 Expected VRAM per service (new)

A parked service reports **0** live VRAM, so the fit-check needs an estimate. Add
`expected_vram_gb`: manually settable, and **auto-learned** from the service's
observed peak VRAM while running. Over a few park/unpark cycles each service learns
its own footprint — the small feedback loop that makes the fit-check trustworthy
without hand-entered numbers. In the multi-app world the learned peak is best
surfaced by the **agent in `/cluster/state`** (it watches the cluster directly), so
every environment agrees on a service's footprint instead of each app's DB
re-learning it separately.

### 5.3 The fit preflight

Before an **unpark** (or **move**), compare `expected_vram_gb` against the target
box's **free** VRAM (and any `resource_group` one-at-a-time budget):

- **Fits** → green, one-tap.
- **Tight** → amber, allowed with a warning.
- **Won't fit** → red; the control center **lists what to park on that box** to make
  room (running services, largest first), so the manual bin-pack is one or two taps
  instead of a mental puzzle.

This directly answers *"how much memory do I have and how do I bin-pack?"* with no
automation.

### 5.4 "What can run where" — candidate boxes, simply

Placement in the fleet is expressed as a **single node label**
(`nodeSelector: inference-club.com/box: <a1|a2|a3|spark>`) — **no taints/tolerations
at all** — so *moving* a service is just patching that one label. The hard part
isn't the label; it's knowing **which boxes a service can actually run on**. Two
real constraints, surfaced as a service's **candidate boxes**:

1. **Architecture** — `spark` is arm64 (GB10, unified memory); `a1/a2/a3` are amd64
   (RTX 4090). A service's image must match, so spark-only and a-box services don't
   cross over unless multi-arch.
2. **Where the weights are** — most model weights are **node-local `hostPath` HF
   caches**, present only where the service has already run. The exception is
   anything on **Longhorn RWX** (today just `dia`, replicated on a2+a3) — which is
   exactly why `dia` runs on both a2 and a3. **Longhorn replication is the lever
   that widens a service's candidate set**, and the control center should make that
   payoff visible ("on Longhorn → can run on a2, a3").

So each service shows **"runs on `<box>` · can also run on `<candidates>`"**. V0/V1
treat candidates as declared in the manifest (simple, honest); V2 patches the box
label to move within them and can auto-derive candidates from arch + weight
availability. Also mind **hostPort collisions** (some services claim a hostPort;
two can't co-locate) — a move preflight check.

## 6. Current state (verified across four repos)

**The app is read-only to the cluster** — only declarative writes exist (manifest
upload upserting `Host`/`Gpu`/`ProviderService`/…). PRD 07 states the non-goal:
"read-only, no actions on the cluster."

**Services are real, scalable, and GitOps already yields to us.** All ~11 GPU model
services live in namespace `inference-club` as real `apps/v1` Deployments with an
explicit `replicas` (0↔1 works directly); `lmstudio-headless` and `trellis2`
already sit at `replicas: 0`. Crucially, `home-cluster`'s Argo CD app for the fleet
sets, on **every** inference Deployment:

```yaml
ignoreDifferences: [{ group: apps, kind: Deployment, jsonPointers: ["/spec/replicas"] }]
syncOptions: [RespectIgnoreDifferences=true]
# comment: "/spec/replicas is IGNORED on every Deployment — scaling is operational
#           state owned by Brian/Hermes (GPU bin-packing, park/unpark), never by git."
```

→ **an out-of-band scale from the agent will not be reverted by GitOps.** The
platform was built anticipating exactly this control center. (It also means manual
`kubectl` / other clients are existing out-of-band actors — our **drift** state must
show when actual ≠ what this app last asked for.)

**This unlocks the intended workflow: declare-in-Argo, park-by-default, turn-on
here.** Because replica count is git-ignored, Brian can define *many* inference apps
in Argo CD (each a real Deployment) and leave them **scaled to 0 by default** — no
need to worry up front about whether the fleet has room for all of them. Argo keeps
their *configuration* in sync (image, resources, node label) while never touching
their run-state; the control center is where they get turned **on**, one at a time,
onto a box with space. Editing an app's Argo config later just updates the spec — if
a pod is running it rolls, if it's parked it simply applies for next time — so the
config lane (Argo) and the run-state lane (this control center) never fight. The
**roster of "services you can start"** is exactly this set of declared-but-parked
Deployments (today, `lmstudio-headless` and `trellis2` already sit this way).

**Placement** = `nodeSelector: inference-club.com/box: <a1|a2|a3|spark>` + `runtimeClassName: nvidia`
+ `nvidia.com/gpu: 1`. No taints. Boxes: a1/a2/a3 (amd64 4090), spark (arm64 GB10).

**The agent is read-only, unauthenticated, unversioned** (`inference-club-agent`):
raw k8s REST, **GET-only** (no `client-go`), in-cluster SA token; **zero inbound
auth** (tailnet trust); routes are only `/healthz`, `/v1/*`, `/cluster/state` —
**no `/version`, no `/cluster/activity|history` on the agent** (those are backend-
side). Namespace via `AGENT_DISCOVERY_NAMESPACE=inference-club`. Its SA
`agent-inference-club-agent` RBAC is **read-only** (`services,pods,endpointslices,
secrets` get/list in ns; `nodes`+metrics cluster-wide) — **no `apps`/`deployments`/
`deployments/scale`, no write verbs**. The in-cluster SA token plumbing is reusable
for a write call.

**The local LAN app is real & shipping** (`inference-club-deploy`): Kustomize +
Argo CD, ns `inference-club-web`, ingress `club.lan`, own DB `inferenceclub`,
Harbor images (`harbor.lan/apps/inference-club-{backend,frontend}`, CI rewrites tag
+ `APP_VERSION` to commit sha), Forgejo build → bump → Argo sync. Email-only auth,
`DEPLOY_ENV=homelab`.

**Telemetry is in place:** `vram-reporter` DaemonSet (ns `monitoring`, `:9401/vram`)
→ agent scrapes and attributes per-service VRAM into `/cluster/state`; Prometheus
(30090) + Grafana (30030) with gpu-fleet / gpu-vram / vllm dashboards to deep-link.

**Provider** already models the agent connection (owner-scoped; `tailnet_addr`,
`agent_port`, `dial_host`, `is_online`).

**Net-new for this PRD:** everything on the write side — agent scale/move endpoint
+ its first inbound auth + write RBAC + `/version`; backend desired-state model,
opt-in flag, agent-auth secret, `ServiceAction` audit, actuation views + reconcile;
and the simple-cards frontend.

## 7. The control model — desired vs. actual

A **service** maps to one Deployment; its operational state is derived from
*desired* (Django) reconciled against *actual* (agent):

| State | Meaning |
| --- | --- |
| `parked` | desired 0, no pod (VRAM freed) — a first-class, visible roster entry |
| `starting` | desired 1, pod pending / pulling / not-ready |
| `running` | desired 1, pod `Ready`, serving |
| `stopping` | desired 0, pod terminating |
| `failed` | desired 1 but crash-looping / unschedulable (e.g. won't fit) |
| `drift` | actual ≠ desired past a grace window (someone `kubectl`'d, Hermes moved it, or a box went `NotReady`) |

`ReadinessDot` already renders liveness; we extend its palette to these.

**The cluster is the one source of truth — the apps are remote controls, not
controllers.** Because several environments actuate the same cluster (§4), no app
runs an auto-healing loop that continuously re-asserts its own desired state — two
apps doing that would fight forever. Instead each app: **(1)** issues a scale/move
*command* through its agent, **(2)** records it in its own `ServiceAction` audit,
**(3)** then just *observes* actual cluster state and displays that. `desired_state`
is therefore **"the last command this app sent"** — it drives the optimistic UI flip
(`starting`/`stopping`) and the drift banner, but it is **never enforced by a
background loop**. k8s does the only real reconciliation (Deployment → pod). This is
exactly the "prod scales X, `club.lan` sees X up" behaviour: every pane of glass
converges on the cluster's truth, and the last-scaled-by annotation (§4.3) tells you
which app moved it. `drift` here means "actual ≠ the last thing *I* asked for" —
**informational, not auto-corrected** (a future auto-scheduler, §10, is where any
enforce-desired loop would live, and only one owner should run it).

## 8. The board is GPU boxes only — and "start here" on a free one

**The main page is a breakdown of the cluster's GPU-schedulable boxes, and nothing
else.** That's a1 / a2 / a3 / spark — the machines that actually run inference.
Non-GPU / control-plane / storage-only nodes are **not shown on the board** (at
most a small collapsed "utility nodes" row if it's ever useful); the operator
should see only the boxes where inference workloads live. A GPU box is identified
by carrying GPUs (a `Gpu` row / `nvidia.com/gpu` allocatable) and the
`inference-club.com/box` label.

A GPU box is **schedulable right now** when it is online (fresh heartbeat), k8s
`Ready`, and **not** under `MemoryPressure`/`DiskPressure` (real failures seen on
a1/a2). A box that fails any check is still shown but **grayed and non-actionable**,
with the reason stated plainly ("NotReady", "disk-pressure", "offline"). All from
node-condition data already in `/cluster/state`.

**Start-here on a free box.** The user's core move is *"this box is idle and has
room — put a workload on it."* So a schedulable box with low utilization and free
VRAM offers a **"start a service here"** affordance: it lists the **parked services
that can run on this box** — i.e. whose candidate set (§5.4) includes it *and* whose
`expected_vram_gb` fits the free VRAM — and one tap unparks the chosen one onto that
box. Early on that list is short (e.g. only `dia` can land on a2/a3 because only its
weights are Longhorn-replicated); as more model weights move to Longhorn it widens
toward "any compatible service on any box," with **no UI change** — the candidate
set simply grows.

## 9. Frontend — simple, tight cards

A single **Control Center** hub (proposed `/dashboard/control`; the 3D
`/dashboard/cluster` scene stays separate and cross-linked). Mobile-first, dense,
plain, **no 3D**, progressive disclosure. Cards are **compact — not big** — packing
the screen while showing only what matters, with the actions on the card.

1. **Box cards (default) — GPU boxes only.** One tight card per GPU-schedulable box:
   form-factor + hardware/engine **logos**, the two headline metrics (**free-VRAM bar
   + utilization**, §5.1), a schedulable/why-not badge, and a stacked list of its
   running services — each row: logo, `ReadinessDot` state, live VRAM, trailing-hour
   activity spark, and a **Stop (park) toggle**. A box with room shows a **"+ start a
   service here"** control listing the parked services that fit it (§8). This *is*
   the pane of glass.
2. **Parked roster.** Parked services appear in their home box's card (dimmed, with
   an Unpark + fit preflight) so what's *possible* is always visible, not just
   what's up.
3. **Fit preflight** inline on Unpark/Move: green / amber / red + "park X to fit".
4. **Service drawer** (tap a row): logo, type, engine, box, state, `VramSparkline`,
   activity, candidate boxes + **Move** picker (V2), recent `ServiceAction`s, a link
   out to Grafana, and the primary Park/Unpark with confirm-on-busy.
5. **Action feed.** The `ServiceAction` audit log as a live timeline.
6. **Header.** Always shows *which* cluster/agent you're controlling + version
   compatibility (§4).

Principles: reuse the component kit + `useClusterPalette`; lead with **up? fits?
busy?**; keep deep telemetry one tap / one link away so the surface stays calm;
live updates ride the existing `useClusterState` poller; actions optimistically flip
to `starting`/`stopping` and settle on the next poll.

## 10. Phasing

Each phase has a proof-of-success gate.

- **V0 — Consolidate + desired-state model + opt-in (read-only, no actuation).**
  Build the Control Center hub over existing telemetry; fold the scattered pages
  into it; **GPU boxes only**; render each box's **free-VRAM + utilization**, the
  full running+parked roster, fit math, schedulability, candidate boxes, and drift.
  Add `Provider.cluster_control_enabled` (default off), `ProviderService.desired_state`
  + `expected_vram_gb` (seeded from actual / observed peak), candidate-boxes field.
  Park/Unpark and start-here are visible but disabled. *Gate:* on a phone, one page
  shows only the GPU boxes, each with free VRAM + utilization, every service's state
  + footprint (incl. parked), whether each would fit, where each can run, and any
  drift — no actuation yet.

- **V1 — Actuation: Park / Unpark (scale 0↔1).** Agent gains `POST /cluster/services/{name}/scale`
  + its first inbound-auth check + a kube PATCH write path + `GET /version`; agent
  chart gains `deployments/scale` RBAC; backend gains the owner-only actuation view +
  agent-auth secret on `Provider` + `ServiceAction` audit + reconcile/poll + fit
  preflight + confirm-on-busy + version-compat gate. *Gate:* from your phone, park a
  running service and unpark another; VRAM visibly frees and fills; the action is
  logged; it works identically from `inference.club` and `club.lan`.

- **V2 — Move between boxes.** Agent patches the `inference-club.com/box` label to
  reschedule; UI offers the service's **candidate boxes** with a fit + hostPort
  preflight; candidates start manifest-declared, then auto-derive from arch + weight
  availability (Longhorn RWX vs hostPath). *Gate:* move `dia` between a2 and a3 from
  the UI, fit-checked.

- **V3 — Learned footprints + fleet presets.** Auto-learn `expected_vram_gb` from
  rolling observed peak. **Presets**: save a named set of desired states
  ("podcast mode" = omni + magpie up, rest parked; "video mode" = ltx + flux up) and
  **apply in one tap** to rebin-pack the fleet — which is how the fleet is juggled by
  hand today. *Gate:* apply a preset, the fleet converges, drift clears.

**Deferred to a future PRD:** (a) automatic scheduling / demand-based placement — an
enforce-desired loop that one owner runs; (b) an **inference.club "scaling skill"**
that lets any agent (Claude, Hermes, …) park/unpark/move via natural language — it's
the *same* owner-only actuation API this PRD builds, just called by an agent holding
the owner's key instead of a human tapping a card, so V1's endpoint is deliberately
shaped to be that skill's backend later. Ship the human pane of glass first.

## 11. Prerequisites & gap to close (before we start)

Where the surrounding work stands and what must be true to begin V0/V1. **Already
done** (green): the local `club.lan` app is deployed (PRD 20 Epics 0–3); services
are real scalable Deployments with two already parked; **Argo ignores replicas**;
placement is a single box label; the agent has reusable in-cluster SA token
plumbing; `vram-reporter` + Grafana are live; `Provider` models the agent
connection. **Net-new, and roughly ordered:**

1. **Agent write path + auth + version** (`inference-club-agent`): a PATCH helper to
   `deployments/{name}/scale` (sibling to the GET-only helper), the
   `POST /cluster/services/{name}/scale` route behind the agent's **first inbound
   Bearer check**, and a `GET /version`. *Depends on nothing; can start immediately.*
2. **Agent RBAC** (`inference-club-agent/charts/.../rbac.yaml`): add
   `apps/deployments` + `deployments/scale` `get,list,patch` in ns `inference-club`,
   bound to the existing SA; roll via Argo. *Pairs with #1.*
3. **Backend desired-state + control surface** (`inference.club`): migration for
   `Provider.cluster_control_enabled` + agent-auth secret + **direct-dial mode**
   (ClusterIP/in-cluster DNS, bypassing SOCKS — for `club.lan`),
   `ProviderService.desired_state` + `expected_vram_gb` + candidate boxes,
   `ServiceAction` model, owner-only actuation views proxying to the agent, the
   command-then-observe flow (no auto-heal loop, §7), version-compat check. *V0
   (read/model) needs none of #1–2; V1 actuation needs them.*
4. **Frontend Control Center** (`inference.club`): the simple-cards hub. *V0 can build
   entirely on today's read APIs.*
5. **Version-compat convention:** define the agent↔backend API version handshake
   (agent `/version` ↔ the app's `APP_VERSION`/version surface from PRD 20) so the UI
   can gate actions. *Small; do alongside #1.*

**Decisions locked (from Brian):** `club.lan` dials its agent by **ClusterIP /
in-cluster DNS**, not the tailnet — so the `Provider` **direct-dial mode** (item 3)
is required. **One agent per environment** is the chosen model (§4.1); Hermes is
experimental and explicitly **not a concern** for this PRD (the drift model already
tolerates any out-of-band writer).

**Remaining setup before V1 (net-new, small):** **(a)** stand up the per-environment
agents — at least `club-agent-lan` (in-cluster, `AGENT_DIRECT`/ClusterIP) alongside
the existing prod agent, each with its own Secret key; **(b)** **register the
`club.lan` app's `Provider`** against `club-agent-lan` — it is **not registered
today** (the in-cluster app was only deployed), so this is a concrete task, not an
assumption; **(c)** define the per-environment key convention (§4.3).

## 12. Open questions

1. **Route & naming.** New `/dashboard/control` beside the 3D `/dashboard/cluster`,
   or reimagine `/dashboard/cluster` itself as the control center? (Lean: new hub.)
2. **Desired vs. manifest.** Manifest declares *existence*; the control center owns
   *run-state*. On manifest re-upload, preserve desired state (don't reset). Confirm.
3. *(Resolved, §7)* **Reconcile / concurrent writes.** No app-side enforce-desired
   loop; command-then-observe, cluster is source of truth, last-write-wins on
   replicas, k8s reconciles. Multi-app conflict is accepted by design. Any
   enforce-desired loop is deferred to the auto-scheduler (§10), run by one owner.
4. **Agent inbound auth scope.** Guard only writes, or add the Bearer check to reads
   too (tightening the currently-open `/cluster/state`)? (Lean: writes now, reads
   opportunistically.)
5. **Cold-start honesty.** Some services take real time to load weights (spark had an
   autotune-cache cold-start tax, see [[project_trellis2_perf]]). `starting` should
   surface expected warm-up, ideally learned from first-ready time.
6. **Move & node-local weights.** Moving a service off its `hostPath`-cached box means
   a cold weight pull (or nothing) unless it's on Longhorn RWX. Do we block moves to
   boxes without weights, warn, or offer a "replicate to Longhorn" nudge?
7. **Roadmap tracker shape.** `backend/apps/inference/roadmap.py` is single-programme
   (hard-coded to PRD 12). Registering this PRD's phases means extending it to
   multiple programmes or swapping it. Decide before V0 tracking begins.
