# Model identity, capabilities & recommended profiles

How inference.club keeps "many providers serving the same model" from
fragmenting into many incompatible varieties — while still allowing the
real differences (context length, concurrency, modalities, custom
fine-tunes) that heterogeneous hardware forces.

## 0. The problem

A model isn't one thing once you serve it. The *same* weights become many
deployments that differ in ways that matter to a caller:

- **Context window** — `--max-model-len`. The single most important knob;
  a 24 GB card might serve `Qwen3-30B` at 16k, a 48 GB card at 64k.
- **Concurrency** — `--max-num-seqs`. How many requests run at once.
- **Modalities** — a Nemotron-Omni / Qwen-VL model *can* do image/audio/
  video, but a given node may enable only text (cheaper, less VRAM).
- **Quantization / dtype** — fp16 vs fp8 vs awq-int4, changing quality and
  speed.
- **Engine** — vLLM vs SGLang vs llama.cpp vs Ollama, each with its own
  quirks, tool-call parsing, chat templates.

The vision is *many providers each serving a few models → large, pooled
capacity per model*. That only works if a request for "model X" can land on
**any** provider serving X. The danger: if we treat every (model + settings)
combination as a distinct offering, the catalog explodes and the pools
shrink to one provider each — the opposite of the goal.

## 1. The core idea

Three principles, in priority order:

1. **Separate identity from deployment.** A *model* (identity) is keyed by
   its HuggingFace repo id. A *deployment* is one provider serving it with a
   specific config. **Pool by identity; filter by capability.** Three people
   serving `Qwen/Qwen3-30B-A3B` are one entry in the public catalog with
   three backends — not three models.

2. **Capabilities are additive filters, not new models.** A VL model served
   text-only still serves every text request — it just isn't a candidate for
   image requests. A request needing 40k context filters to the deployments
   that can do 40k. The *common* request (plain text, modest context) routes
   to the *whole* pool. Divergence only narrows the pool for the requests
   that actually need the divergent capability.

3. **Converge by convention, tolerate divergence by structure.**
   inference.club publishes a **recommended serving profile** per model (the
   blessed `vllm serve …` command). Most providers copy it → big
   interchangeable pools. When a provider *must* differ, the difference is
   expressed as structured capabilities so the router still pools the
   compatible ones.

## 2. Where each fact comes from (the discovery matrix)

We do **not** ask the human to hand-type every flag. Each attribute has a
source, and we reconcile with a clear precedence: **live probe > manifest
declaration > catalog/HF inference.**

| Attribute              | vLLM live probe                              | HuggingFace                                  | Manifest declare | inference.club curate |
|------------------------|----------------------------------------------|----------------------------------------------|------------------|-----------------------|
| served `max_model_len` | ✅ `GET /v1/models` returns it per model      | native `max_position_embeddings` (ceiling)   | optional override| —                     |
| concurrency `max_num_seqs` | ⚠️ not a stable field; *live load* is (`/metrics`) | —                                       | ✅ declare         | recommended value     |
| live load / queue      | ✅ `/metrics`: `num_requests_running/waiting`, `gpu_cache_usage_perc` | — | — | —                     |
| engine + version       | ✅ `/version`                                  | —                                            | engine in YAML   | —                     |
| modalities (can-do)    | ⚠️ inferable from chat template               | ✅ `architectures` / `pipeline_tag` / config | —                | normalized            |
| modalities (enabled)   | ⚠️ partially (`--limit-mm-per-prompt` in cmd) | —                                            | ✅ declare         | recommended           |
| quantization           | ⚠️ sometimes in id / cmd                      | from repo naming / config                    | optional         | normalized            |
| features (tools, reasoning, json) | —                                  | tokenizer chat template, tags                | —                | curated               |

**Key takeaway:** the most important knob (`max_model_len`) and live load
are *discoverable for free* from a running vLLM server. The agent probes
them; the human never types them. Concurrency and "which modalities did you
enable" are the main things a human still declares — and even those default
from the recommended profile.

### vLLM endpoints the agent will probe

- `GET {url}/v1/models` → confirm served id; read `max_model_len`.
- `GET {url}/metrics` (Prometheus) → `vllm:num_requests_running`,
  `vllm:num_requests_waiting`, `vllm:gpu_cache_usage_perc` for load-aware
  routing.
- `GET {url}/version` → engine version.

### HuggingFace as the metadata spine

Keyed by `hf_repo_id`, fetched from the Hub API (cached, refreshed
occasionally):

- `GET https://huggingface.co/api/models/{repo}` → `pipeline_tag`, `tags`,
  `library_name`, `gated`.
- `…/resolve/main/config.json` → `architectures`, `model_type`,
  `max_position_embeddings`, vision/audio sub-configs → **modalities**.
- `…/resolve/main/tokenizer_config.json` → chat template → tool/chat support.

## 3. Data model

Introduce a **network-level catalog model** distinct from the existing
per-provider `ProviderModel` (which becomes "a deployment").

### `CatalogModel` (new — one row per logical model)

```
slug                 # public id used in /v1 calls, e.g. "qwen/qwen3-30b-a3b"
hf_repo_id           # nullable (custom fine-tunes)
display_name
architecture         # from HF config.json
model_type
native_context_len   # max_position_embeddings — the ceiling
input_modalities     # ["text","image","audio","video"]
output_modalities
supported_features   # ["reasoning","tools","json_mode", …]
recommended_profile  # JSON: blessed vllm flags (see §5)
hf_metadata          # cached subset of Hub data
hf_synced_at
is_custom            # true → no HF id, provider-declared
```

The **public `slug` is the pooling key.** `/v1/models` lists CatalogModels;
a call to `qwen/qwen3-30b-a3b` is routed to *any* deployment of it.

### `ProviderModel` (extend existing — a deployment under a CatalogModel)

Today it has `name`, `context_window`, `metadata` JSON, `service` FK. Add /
formalize:

```
catalog_model        # FK → CatalogModel (nullable until matched)
hf_repo_id           # declared identity, used to match/create CatalogModel
served_name          # the raw id the backend actually answers to
served_max_model_len # probed from /v1/models
max_concurrency      # declared (max_num_seqs) — for load weighting
enabled_modalities   # subset actually turned on for THIS deployment
quantization
engine, engine_version
conforms_to_profile  # computed: matches recommended_profile?  "standard" vs "custom"
```

(Several of these already live loosely in the `metadata` JSON — this just
promotes the load-bearing ones to typed columns the router can query.)

## 4. Manifest evolution

The manifest already carries the real vLLM invocation in the free-form
`command` field — we just make identity + the few human-declared
capabilities first-class, and keep `command` for display.

```yaml
services:
  - name: rtx-4090-vllm
    engine: vllm
    url: http://192.168.1.10:8000/v1
    models:
      - hf: Qwen/Qwen3-30B-A3B        # canonical identity → CatalogModel
        profile: recommended           # or "custom"
        # only needed when diverging from the recommended profile:
        modalities: [text]             # this node serves text-only
        max_num_seqs: 16
      - hf: nvidia/Nemotron-Omni-…
        profile: custom
        modalities: [text, image, audio]
    command: >                         # unchanged, display-only
      vllm serve Qwen/Qwen3-30B-A3B --max-model-len 32768 --max-num-seqs 16
```

- `hf:` replaces the opaque `id:` as the recommended way to declare a model.
  (Back-compat: a bare `id:` string keeps working and is treated as a
  `served_name` we try to match to a CatalogModel by alias.)
- Everything else stays optional. A provider who follows the recommended
  profile writes just `- hf: …` and the agent + catalog fill in the rest.

## 5. Recommended profiles — the anti-fragmentation lever

For each CatalogModel, inference.club curates a **recommended profile**: the
exact command that produces a "standard" deployment, plus the capability
values it yields.

```json
{
  "command": "vllm serve Qwen/Qwen3-30B-A3B --max-model-len 32768 --max-num-seqs 16 --enable-auto-tool-choice --tool-call-parser hermes",
  "max_model_len": 32768,
  "max_num_seqs": 16,
  "modalities": ["text"],
  "min_vram_gb": 24,
  "notes": "Fits a single 24 GB card. For ≥48 GB bump --max-model-len to 65536."
}
```

This is surfaced on the model's catalog page and in docs as **"serve this
model the blessed way — copy this command."** Deployments matching it are
flagged `standard` and form one large interchangeable pool; deviations are
`custom` and still serve, just with their declared capabilities. The social
mechanism (make the easy path the uniform path) does most of the work; the
structured fallback handles the rest.

## 6. Multimodality

Modalities are capability *sets* at two levels:

- **CatalogModel** = what the weights *can* do (from HF architecture).
- **ProviderModel.enabled_modalities** = what this node *turned on*.

Routing reads the request: text-only request → any deployment; request with
image parts → only deployments with `image` enabled. So a Qwen-VL model
served text-only on a cheap node still contributes to the (large) text pool —
**no fragmentation penalty for the common case.** Media limits
(`--limit-mm-per-prompt`, max resolution, audio length) become capability
fields; an over-limit request gets a clear 4xx or routes to a node that
allows it. Output modalities (e.g. audio-out) are handled the same way once
relevant.

## 7. Custom / non-HuggingFace models

First-class, not an afterthought:

- A model with no `hf:` is allowed: `is_custom = true`, provider supplies
  `display_name` + declares capabilities directly.
- Optional `base_model:` (an HF id) lets a fine-tune **inherit** metadata and,
  if the provider asserts compatibility, alias into the base model's pool.
  Otherwise it forms its own (small) pool and is labelled "community / custom"
  in the catalog.
- Server-side probing (max_model_len, load) works regardless — it only needs
  the running endpoint.

## 8. Routing semantics (the payoff)

For a request to slug `S` with required capabilities `C` (context length,
modalities):

1. Pool = active deployments whose `catalog_model.slug == S`.
2. Filter to those satisfying `C` (`served_max_model_len ≥ needed`,
   `enabled_modalities ⊇ needed`, access policy grants the caller).
3. Among survivors, pick by **live load** (`/metrics`: fewest waiting /
   lowest KV-cache usage), tie-broken by latency history.
4. On failure, retry the next candidate (failover).

This is also the multi-node load-balancing / failover win from the roadmap —
it falls out of the same capability model.

## 9. Phased rollout (start simple)

- **Phase 0 — identity. ✅ Shipped.** Added `CatalogModel` (slug = lowercased
  HF id) + `ProviderModel.hf_repo_id`/`catalog_model`; manifest accepts `hf:`
  (validator + sync); `/v1/models` pools by slug; routing matches by slug (with
  case-insensitive served-name back-compat) and the proxy **rewrites
  `body.model` to the exact served name** before forwarding, so lowercasing
  the public id never breaks the upstream (vLLM matches ids case-sensitively).
  Existing live-discovered rows backfill their catalog link on next refresh.
  No agent changes required.
- **Phase 1 — probe.** Agent reads `/v1/models` (max_model_len), `/metrics`
  (load), `/version`; reports them; server reconciles with precedence. Kills
  the human-coordination burden for the most important setting.
- **Phase 2 — HF enrichment.** Sync `CatalogModel` from the Hub API
  (architecture, native context, modalities, features). Catalog page surfaces
  it. Author recommended profiles for the top models.
- **Phase 3 — capability routing.** Filter by context/modalities; pick by
  live load; retry on failure. (Also delivers failover + load balancing.)
- **Phase 4 — conformance.** Mark deployments `standard` vs `custom`; nudge
  convergence; badges + "copy the blessed command" UX.

## 10. Open decisions

1. **Public slug scheme.** Lowercased HF id (`qwen/qwen3-30b-a3b`) vs a curated
   short slug with the HF id as an alias. Lean: default to lowercased HF id,
   allow curated overrides. Keep raw served strings as aliases so existing
   callers don't break.
2. **Who authors recommended profiles?** Maintainer-curated to start (a fixture
   / admin), community-suggested later.
3. **HF sync trigger.** On first sighting of a new `hf_repo_id` + a periodic
   refresh, vs on-demand. Lean: on first sighting + lazy refresh past a TTL.
4. **Strictness.** Do we *reject* a deployment whose probed `max_model_len`
   contradicts its declaration, or accept-and-flag? Lean: accept, trust the
   probe, surface the mismatch to the provider.
```
