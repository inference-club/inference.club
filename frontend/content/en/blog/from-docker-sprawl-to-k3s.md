---
title: "From docker sprawl to k3s: rebuilding my home inference fleet"
description: "A 'healthy' mesh-generation service sat wedged for three days while my agent.yaml described services that didn't exist. So I moved four GPU boxes — three RTX 4090s and a DGX Spark — onto k3s and taught the inference-club-agent to discover services from the Kubernetes API instead of a config file. Health checks lie; queues don't. Config is fiction; clusters are testimony."
publishedAt: "2026-06-12"
author: briancaffey
tags: [k3s, kubernetes, homelab, architecture, deep-dive]
image: /images/blog/from-docker-sprawl-to-k3s.png
image_prompt: "Wide cinematic abstract illustration: four glowing GPU server towers of different sizes connected into one luminous orbital control ring, streams of cyan and violet light flowing from chaotic tangled cables on the left into clean orderly orbital paths on the right, one small node glowing outside the ring still connected by a thin thread of light, dark moody futuristic, soft glow, no text, no words, no letters"
featured: true
---

On 2026-06-11 I noticed that TRELLIS — the service that turns text and images into 3D meshes on my DGX Spark — had been "healthy" for three days. Green health check, container up, port answering. It had also completed zero requests in those three days, because a single wedged worker was sitting on the queue and every new request lined up politely behind it. The health endpoint said *the process is alive*. Nobody had asked the only question that matters: *is work coming out?*

Health checks lie. Queues don't.

While digging into that, I did an honest inventory of my fleet and found something more embarrassing. The `agent.yaml` file that describes my machines to [inference.club](https://github.com/inference-club/inference.club) — the hand-maintained map of hosts, GPUs, services, and models that the agent uploads so the platform knows what I can serve — declared a `qwen3-asr` service on a3 that was not running at all. It declared flux as a service on a2, which was technically true, except flux wasn't even a container: it was a bare Python process that had been running since May 19, launched with `uv run` from a git checkout, surviving only because nobody had rebooted the box. Meanwhile two services that *were* running (a voice-conversion NIM and a couple of Open WebUI instances) appeared nowhere. And almost every container on every box was `restart: no` — one power blip away from a fleet that silently doesn't come back.

Config drifts. Clusters don't — or rather, a cluster *is* the thing, not a description of the thing. That's the realization this post is about. I spent an evening moving four mixed-architecture GPU boxes onto k3s, and then — before migrating a single service — taught the [`inference-club-agent`](https://github.com/briancaffey/inference-club-agent) to stop reading a YAML file and start reading the Kubernetes API. The agent's 130-line `agent.yaml` collapsed to two environment variables, and the manifest it uploads got *more* accurate and *richer* at the same time, because every field is now derived from running state instead of typed by a human who last updated the file three services ago.

Both repos are open source — [`inference.club`](https://github.com/inference-club/inference.club) and [`inference-club-agent`](https://github.com/briancaffey/inference-club-agent) — and the migration itself lives in a third repo of kustomize manifests and docs, so you can follow along in the actual code.

## The five-second version

```
        inference.club backend
              │
              │  http://<node-LAN-IP>:8090   (LoadBalancer via k3s ServiceLB)
              ▼
┌──────────── k3s cluster · namespace: inference-club ─────────────┐
│                                                                  │
│  inference-club-agent (Deployment, Helm chart)                   │
│    AGENT_DISCOVERY=kubernetes                                    │
│    └─ every 30s: LIST Services/Pods/EndpointSlices (+ Nodes)     │
│       Services labeled inference-club.com/managed=true           │
│       → manifest → upload (only when the bytes changed)          │
│    └─ routes requests to http://<svc>.inference-club.svc:…       │
│                                                                  │
│  a3 · amd64 · RTX 4090 ── control plane + ltx2 (video)*          │
│  a1 · amd64 · RTX 4090 ── magpie-tts (speech)                    │
│  a2 · amd64 · RTX 4090 ── flux (image)*  ⚠ awaiting reboot       │
│  spark · arm64 · DGX Spark GB10 ── acestep (music),              │
│                    nemotron-asr (transcription), trellis2 (mesh) │
│                                                                  │
│  lmstudio Service (no selector)                                  │
│    └─ EndpointSlice → 192.168.6.19:1234 ──────────┐              │
└───────────────────────────────────────────────────┼──────────────┘
                                                    ▼
                                     LM Studio on spark's host OS
                                     (outside the cluster, on purpose)
```

\* still on docker as of this writing — services migrate one at a time.

Three boxes with RTX 4090s (amd64) and a DGX Spark (arm64, GB10, 121 GB unified memory) run k3s. Inference services become Deployments + Services carrying a small label/annotation schema. The agent runs in-cluster and polls the Kubernetes API every 30 seconds, building its manifest from what is *actually running* — exact image, exact command, which node, which GPU — instead of from a hand-typed file. A service that lives outside the cluster (LM Studio) is represented by a selector-less Service with a manual EndpointSlice, so the agent and router treat it identically to everything else. Docker keeps running beside k3s the whole time; each service cuts over only when its k8s copy is verified end to end.

## The fleet, before

Four Ubuntu boxes on one LAN, serving seven inference services for inference.club through a single agent:

| node  | arch  | GPU                          | what it serves |
|-------|-------|------------------------------|----------------|
| a1    | amd64 | RTX 4090 24GB                | magpie-tts (speech), maxine-studio-voice |
| a2    | amd64 | RTX 4090 24GB                | flux (image) — as a bare process |
| a3    | amd64 | RTX 4090 24GB                | ltx2 (video: a proxy + a ComfyUI worker) |
| spark | arm64 | DGX Spark GB10, 121GB unified | trellis2 (mesh), acestep (music), nemotron-asr (transcription), LM Studio (LLM) |

Every one of those was started by hand: `docker run` invocations of varying vintage, one bare `uv run` process, four locally-built images that exist nowhere but the box they were built on. The pre-migration inventory found that almost everything was `restart: no`, secrets rode along as plain `-e` env vars, and ltx2's proxy used host networking because that was the path of least resistance at the time.

This is not a confession of unusual sloppiness — I'd argue it's the *default end state* of a homelab that grew one exciting model at a time. Each service was set up in an afternoon of "let's get LTX-2 working," and afternoon-projects don't write systemd units. The system worked, mostly, which is exactly why nothing forced the cleanup until TRELLIS quietly stopped working in a way that all my monitoring called healthy.

## Why Kubernetes, and not just better docker hygiene

The obvious counter-move is discipline: docker compose files in git, `restart: unless-stopped` everywhere, a real healthcheck per service. I considered it. It fixes the restart problem and nothing else, because the deeper problem isn't restart policy — it's that **the description of the system and the system itself are two different artifacts that drift apart**.

`agent.yaml` is a map of hosts → GPUs → services → models. Every field in it is something I typed, which means every field is something I can forget to update. The file said qwen3-asr existed; the fleet said otherwise. The file said flux was a service at a2:8000; the fleet said it was an unsupervised process with no container, no restart policy, and no record of how it was launched beyond my shell history. Better docker hygiene gives you a *more disciplined fiction*. It's still fiction.

Kubernetes inverts the relationship. The cluster's API *is* the inventory — not a description that hopes to track reality, but the control loop that produces reality. If a pod isn't running, it isn't in the API as running, and there is no second artifact to fall out of sync. When my agent asks "what services exist, where, with what command?", the answer comes from the same source of truth the scheduler uses. Config is fiction; clusters are testimony.

That reframing is what made the migration worth it for me, and it dictated the build order: the agent learns to read the cluster *first*, before any service migrates, so that from day one the thing reporting my fleet to inference.club is reading testimony, not fiction. No interim agent.yaml-in-a-ConfigMap step — that would just relocate the fiction.

## k3s on mixed amd64/arm64 with GPUs: what actually mattered

The cluster itself was the easy evening. k3s installs with a shell script per node; a3 became the single server (it's a 4090 box, so it runs workloads too — taints are for people with spare machines), and a1, a2, and spark joined as agents. A homelab note on the single control plane: yes, a3 is a single point of failure. So is my electrical panel. Revisit if it bites.

Three details actually mattered:

**Embedded containerd, not the docker shim.** k3s ships its own containerd, and using it means docker keeps running untouched beside the cluster for the entire migration. Every service keeps serving production traffic from its docker copy until its k8s replacement is verified. Cutover per service, not per fleet.

**The NVIDIA RuntimeClass + device plugin, with a version that knows about unified memory.** GPU pods need the nvidia container runtime (k3s detects it and writes the containerd config; you add the `RuntimeClass`) plus the NVIDIA device plugin so nodes advertise `nvidia.com/gpu`. On the 4090 boxes, this just worked. On the DGX Spark's GB10 — where there is no discrete VRAM, just 121 GB of unified memory — device plugin **v0.17.0 fails** to read the GPU's memory and won't advertise it. **v0.17.4 handles GB10 unified memory correctly.** That patch-version gap cost me the better part of an hour and is exactly the kind of detail you only learn by doing it, which is why it's in this post.

::blog-note{type="tip"}
Running k8s on a DGX Spark (or anything GB10-based with unified memory): use NVIDIA device plugin v0.17.4 or newer. v0.17.0 can't read GB10 unified memory and the node will never advertise `nvidia.com/gpu`, with no error that says why.
::

**Multi-arch is mostly a non-event — until images.** k3s itself and the standard manifests are happily multi-arch. The pain arrives with *your* images: anything that has to run on spark needs an arm64 build, and four of my service images were locally built with no registry at all. The agent's own image now publishes as a multi-arch manifest (amd64 + arm64) from CI so one Helm chart serves the whole cluster.

Each node also gets a label, `inference-club.com/box=a1` through `spark`, which the agent uses as the stable host identity in the manifest it uploads — the successor to agent.yaml's hand-assigned host IDs.

One box sat the evening out: a2 has an NVML driver/library mismatch (userspace 580.159 against an older loaded kernel module), so new GPU processes fail until it reboots. The flux process *survives* because it predates the driver upgrade — a perfect little museum exhibit of why "it's been up for weeks" and "it will come back up" are unrelated claims.

## Teaching the agent to read the cluster

This is the part I care most about, because it's the part that generalizes beyond my basement: commit [`1908505`](https://github.com/briancaffey/inference-club-agent) in the agent repo, "kubernetes discovery mode + helm chart."

The design question was: what replaces agent.yaml? The answer: almost nothing. Identity stays as config (the agent's name and API key — Kubernetes can't know who you are on inference.club). *Everything service-shaped* moves onto the Services themselves, as labels and annotations:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: magpie-tts
  namespace: inference-club
  labels:
    inference-club.com/managed: "true"   # the discovery selector — only required label
    inference-club.com/type: tts         # llm|stt|tts|image|mesh|music|video
    inference-club.com/engine: other     # same enum agent.yaml used
  annotations:
    inference-club.com/models: |
      - id: magpie-tts-multilingual
    inference-club.com/base-path: "/v1"
spec:
  selector: { app: magpie-tts }
  ports: [{ name: http, port: 9000 }]
```

Labels carry the few fields worth *selecting* on; annotations carry the structured payload (the models list, features, base path) that doesn't fit label syntax. The service's description now lives on the service. It cannot drift to a different file, because there is no different file.

And here's the payoff — the fields nobody declares anymore, because they're derived from running state:

| agent.yaml field (old, hand-typed) | k8s source (new, derived) |
|---|---|
| `hosts[].address` / `hostname` | the backing Pod's `nodeName` → Node addresses |
| `hosts[].gpu.{model, vram_gb, count}` | device plugin allocatable + GPU-feature-discovery node labels |
| `services[].url` | `http://<svc>.<ns>.svc.cluster.local:<port>` |
| `services[].command` (cosmetic, often stale) | Pod `image` + `command` + `args` — exact and always true |
| — (never had it) | pod phase, readiness, restart counts |

That `command` row deserves a beat. The old agent.yaml had a `command:` field that was pure documentation — whatever I remembered typing when I launched the container. The new manifest reports the *literal* image, command, and args from the pod spec. When someone looks at my provider page on inference.club and wonders how to run ACE-Step on their own Spark, the answer on the page is now guaranteed to be the answer that's running. Exact-command manifests, for free.

### Stdlib REST and a 30-second poll, not client-go

The textbook Go implementation here is client-go with informers — a watch-based cache that reacts to cluster changes in real time. I read the textbook and put it down. The agent needs four namespace-scoped LISTs (Services filtered by `inference-club.com/managed=true`, Pods, EndpointSlices, plus cluster-scoped Nodes) on a slow loop, at homelab scale: tens of objects, not tens of thousands. client-go would dwarf every other dependency in a binary that ships to operators, and the repo deliberately keeps its Docker builds free of a committed `go.sum`.

So `internal/discovery/kubernetes.go` is ~470 lines of stdlib: `net/http` against the cluster API with the mounted serviceaccount CA and token (re-read on every request, because bound serviceaccount tokens rotate), minimal typed views of just the JSON fields we read, and a poll every 30 seconds (`AGENT_DISCOVERY_INTERVAL`). The built manifest is marshaled to YAML and **byte-diffed against the previous build** — services are walked in sorted order so identical cluster state always marshals to identical bytes — and an unchanged cluster re-pushes nothing. `SIGHUP` forces an immediate re-list, same signal the file mode always used for reloads.

Configuration, in its entirety:

```
AGENT_DISCOVERY=kubernetes
AGENT_DISCOVERY_NAMESPACE=inference-club   # this is also the default
```

That's what's left of 130 lines of agent.yaml. There's a subtle correctness rule in the builder, too: a Service whose selector matches no running pod is *dropped from the manifest* rather than reported. The manifest describes what is serving — a declared-but-dead service is exactly the qwen3-asr fiction this whole project exists to kill, and the next 30-second poll picks it up the moment a pod lands.

The Helm chart (`charts/inference-club-agent`, in the agent repo so any provider can use it — my fleet repo holds only values) ships the Deployment, the ServiceAccount and RBAC (read-only: Services/Pods/EndpointSlices/named Secrets in the namespace, plus Nodes cluster-wide), the API-key Secret plumbing, and a LoadBalancer Service for the inbound path — on k3s, the built-in ServiceLB binds it on the node LAN IPs, so the backend reaches the agent at any node's IP on port 8090 with zero extra infrastructure:

```bash
helm install agent charts/inference-club-agent \
  --namespace inference-club \
  --set agentName=club-host-k8s \
  --set apiKey.existingSecret=club-api-key \
  --set direct.enabled=true \
  --set direct.advertiseHost=192.168.5.173
```

The in-cluster agent runs under a *separate experimental account* (`club-host-k8s`) while the untouched production docker agent keeps serving the real one. Cutover is the last step of the whole migration, not the first.

## First light: a completion through a Service that points at nothing

Here's my favorite part. The first real request through the new path — verified end to end on 2026-06-11 — was a chat completion served by a "service" that was never migrated anywhere.

LM Studio runs on spark's host OS, on `:1234`, the way LM Studio wants to run. It is not a container and is not going to become one (it's a desktop app with its own model manager; containerizing it buys nothing). But Kubernetes has a first-class way to give a name to something outside the cluster: a **Service with no selector**, paired with a **manually-created EndpointSlice**:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: lmstudio
  namespace: inference-club
  labels:
    inference-club.com/managed: "true"
    inference-club.com/type: llm
    inference-club.com/engine: lmstudio
  annotations:
    inference-club.com/base-path: "/v1"
    inference-club.com/api-key-secret: lmstudio-key
    inference-club.com/models: |
      - id: google/gemma-4-12b
spec:
  ports: [{ port: 1234 }]
---
apiVersion: discovery.k8s.io/v1
kind: EndpointSlice
metadata:
  name: lmstudio-1
  namespace: inference-club
  labels: { kubernetes.io/service-name: lmstudio }
addressType: IPv4
ports: [{ port: 1234 }]
endpoints: [{ addresses: ["192.168.6.19"] }]
```

No selector means Kubernetes doesn't manage the endpoints — *you* do, by writing the EndpointSlice yourself. But kube-proxy doesn't care who wrote the endpoints. `lmstudio.inference-club.svc.cluster.local:1234` resolves and routes from any pod, straight to the host process on spark, exactly as if a pod were behind it.

The beautiful consequence: **the agent has no "external service" code path.** The Service carries the same labels as every other Service, so discovery picks it up the same way; the router gets the same cluster-DNS URL shape; kube-proxy does the actual delivery. The only difference in the built manifest is that an external endpoint has no `nodeName`, so it reports without GPU metadata — which is exactly the fidelity agent.yaml's hand-typed blocks had, so nothing is lost. (The one annotation doing extra work is `api-key-secret`: LM Studio wants a bearer token, so the agent reads the named k8s Secret and sends its value upstream — and never uploads it.)

So first light was: dev backend → in-cluster agent → Service DNS → kube-proxy → LM Studio on a host machine, returning gemma tokens — through a Service that selects nothing. If you only steal one trick from this post, steal the selector-less Service. It's the bridge that lets a half-migrated fleet behave like a whole one.

## Migrating the services, one at a time

With discovery proven, services move one by one: containerize if needed → push to a registry → write the Deployment/Service with the discovery labels → verify end to end on the experimental account → retire the docker copy. The war stories from the first wave, briefly, because each one taught me something:

**magpie-tts (a1, speech)** went first, as the boring self-contained NIM that proves GPU scheduling + Service DNS + discovery + routing in one shot. It refused to be boring. The image pull filled a1's 110 GB root disk mid-pull, triggering kubelet eviction and a disk-pressure taint (fix: move the k3s data dir to the big disk — the same move docker made on that box years ago). Then `latest` had moved since my two-week-old docker copy, so the NIM kicked off a ~30-minute TensorRT engine rebuild on first boot — which my default-ish 15-minute startup probe SIGKILLed, forever, in a loop. A pod stuck `Pending` with empty logs is answered by `kubectl describe`, not `kubectl logs`: the events table tells you about taints and probe kills that no log line ever will. Fixes: a 40-minute startup budget and an `emptyDir` on the engine cache so rebuilt engines survive restarts. One more cute trick: the k8s pod takes the box's old port via `hostPort: 9000`, so the *production* docker agent — which still has that URL hard-coded in its agent.yaml — healed with zero config changes.

**acestep (spark, music)** proved arm64 — and then proved the thesis a second time. Music generation ran fine; every MP3 save failed, because torchaudio 2.10 removed its backend-dispatch save path out from under ACE-Step. Healthy but wedged, again — and reproducing it against the *production docker copy* showed prod music had been quietly broken the same way since that image was rebuilt days earlier. The migration didn't cause the bug; it *exposed* a bug that uniform redeployment forced into the light. The fix (saving via soundfile + the ffmpeg CLI) repaired prod at cutover.

**nemotron-asr (spark, transcription)** closed a small poetic loop: its end-to-end verification was transcribing a WAV that magpie-tts had generated *inside the same cluster* minutes earlier. TTS → STT, round trip, no humans.

**trellis2 (spark, mesh)** — the service that started all of this — moved last of the wave, and its migration paid for itself in evidence: the mysterious CPU-spin behavior reproduces under containerd, which formally exonerates docker and narrows an open performance investigation. And the mesh export that wedged for three days? Verified end to end on k8s: a 692k-vertex GLB in 243 seconds, no wedge.

::blog-note{type="note" date="2026-06-12"}
The migration is ongoing as of publication. Still on docker: ltx2 (video, a3 — its host networking needs unwinding) and flux (image, a2 — blocked on a reboot to clear an NVML driver/library mismatch, plus containerizing what is currently a bare process). The production agent cutover to the in-cluster agent (over Tailscale, same pathway as today) is the final phase.
::

## What you get for free

The list of things I *deleted* or *stopped doing* is the real scorecard:

- **Restart semantics.** Every migrated service went from `restart: no` to a Deployment's default restart-always, with real liveness/startup probes. A box reboot is now a non-event instead of a silent partial outage discovered days later.
- **The inventory question, answered by the system itself.** "What runs where, with what command, on which GPU?" is now `kubectl get pods -o wide` — or, for the world, the manifest my agent uploads, every field derived.
- **Exact-command manifests.** The reproducibility documentation writes itself, and can't lie.
- **Secrets that are secrets.** NGC keys, HF tokens, the LM Studio key, and the agent's API key are k8s Secrets instead of `-e` flags fossilized in shell history.
- **A debugging vocabulary.** `kubectl describe` on a Pending pod replaced ssh-ing box to box and squinting at `docker ps`.
- **A place to hang what's next** — monitoring that watches queue depth and tokens-out rather than process-up, because the TRELLIS lesson is that liveness is the wrong question.

None of this is news to anyone running Kubernetes at work. The point is the *price*: at homelab scale, with k3s, the whole control plane costs one evening and a few hundred MB of RAM on a box that's mostly busy making videos anyway.

## Seven modalities, one cluster

Step back and look at what this little cluster actually serves through inference.club: **LLM** chat (LM Studio, via the selector-less Service), **image** generation (flux), **video** (LTX-2), **music** (ACE-Step), **speech synthesis** (magpie-tts), **transcription** (nemotron-asr), and **3D mesh** generation (TRELLIS) — seven modalities across three RTX 4090s and a DGX Spark, registered to the platform by one agent that nobody has to update when things change, because it reads the cluster instead of a file.

And the loop is starting to close in a way I find genuinely fun: the same discovery code now feeds a live `/cluster/state` endpoint, which powers a 3D visualization of the cluster on inference.club — whose 3D assets are generated by the mesh service running *on the cluster being visualized*. The substrate is learning to draw itself. That's a story for its own post.

If you run local AI on more than one box and your services are a pile of `docker run` commands you half-remember — that was me two days ago, and the distance from there to "the cluster is the config" is shorter than it looks. Start with k3s and the device plugin (v0.17.4 if you have a Spark), put labels on your Services, and let the system testify.

The code: [`inference-club-agent`](https://github.com/briancaffey/inference-club-agent) (the discovery mode is `internal/discovery/kubernetes.go`; the chart is `charts/inference-club-agent`) and [`inference.club`](https://github.com/inference-club/inference.club). To put your own hardware on the network: [run-an-agent](/docs/providers/run-an-agent).
