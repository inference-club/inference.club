# PRD 19 — External LLM Providers (OpenRouter, NVIDIA, Groq)

> **Status:** Drafted (2026-06-26), in progress. Let users bring their own API
> keys for **OpenRouter**, **build.nvidia.com (NVIDIA NIM)**, and **Groq**, pin
> the models they want, and use them for LLM inference everywhere inference.club
> does LLM inference (chat, agent, …) — on both **inference.club** and
> **api.inference.club**. The model picker shows who serves each model, and a
> single configurable **fallback model** rescues requests when the chosen model
> has no available node or the call errors.
>
> **Builds on:** the per-user encrypted external-key manager (`external_keys.py`
> registry + `UserApiKey` + `get_user_api_key`; PRD: External API keys), the
> OpenAI-compatible `/v1` proxy + per-user `/v1/models`, `CustomUser.routing_preference`
> (the fallback preference sits alongside it), and the `EngineLogo`/`useEngines`
> brand system for provider badges.
>
> **Author:** Brian (product direction) · drafted with Claude Code.

> **Progress** — **V0–V3 implemented (2026-06-26), branch
> `feat/external-llm-providers-prd-19`:** registry entries for the 3 providers
> (V0); `PinnedModel` + browse/pin API + `external_providers.py` resolver +
> catalog cache, the chat proxy refactored into a shared `_create_and_forward`
> that routes pinned `provider:model` ids to the cloud (HTTPS + user Bearer key),
> `/v1/models` injection, and the picker provider badge + Browse-&-pin UI (V1);
> the agent loop's shared `_agent_dispatch` so external models work in the agent
> too (V2); `CustomUser.fallback_model` + a `/dashboard/settings/fallback` page +
> proxy/agent fallback on no-provider/transport-error, one hop, 4xx pass through
> (V3). Migrations `inference 0044`, `accounts 0009`. Tests in
> `test_external_providers.py`. **Not done:** V4 (async/title/narration external
> support, key validation).

---

## 1. Summary

Today every model inference.club can route to is served by a **user-owned
Tailscale agent** — reached over the tailnet by IP, `http://`, no upstream auth
(the WireGuard tunnel is the trust boundary). This PRD adds a second provider
archetype: **external cloud LLM APIs reached directly over HTTPS with the user's
own API key**. Three to start — OpenRouter, NVIDIA NIM (build.nvidia.com), Groq —
all OpenAI-compatible, so the existing `/v1/chat/completions` shape carries over.

The four moving parts:

1. **Keys** — register the three providers in the existing external-key registry;
   the keys UI, Fernet encryption, and `get_user_api_key` come for free. (§4)
2. **Pinned models** — a user browses a provider's catalog (fetched with their
   key) and **pins** the handful they want. Only pinned models appear in the
   picker, namespaced `provider:<id>` and badged with the provider. (§5)
3. **Routing** — one shared LLM-forward resolver branches tailnet-agent vs
   external-cloud (HTTPS, `Authorization: Bearer <user key>`, `verify=True`, no
   SOCKS proxy). The chat proxy and the agent loop both use it. (§6)
4. **Fallback** — a single `fallback_model` per user, used when the requested
   model has no available node **or** the call errors. Configured in settings. (§7)

External providers are **LLM-only**, so this touches the LLM forward path (chat
proxy + agent), not the image/audio/video modality views.

---

## 2. Goals & non-goals

**Goals**
- Store keys for OpenRouter / NVIDIA / Groq; never expose them after entry.
- Pin specific models per provider; they appear in every LLM picker (chat,
  agent) clearly badged with their provider, and work via `api.inference.club`
  by their namespaced id.
- One configurable fallback model (may be external), used on no-provider + error.
- Reuse all existing key/encryption/UI plumbing; centralize the LLM forward so
  tailnet and external share one path.

**Non-goals (this PRD)**
- External providers for non-LLM modalities (image/audio/video stay tailnet).
- Cost/budget tracking or spend caps (their key, their bill — surface model names
  honestly; metering of tokens is best-effort from the response).
- Load-balancing / multi-key rotation per provider.
- Provider-side fine-tuning, batch, or non-chat endpoints.

---

## 3. Current state (verified)

| Concern | Where | Today |
|---|---|---|
| Provider archetype | `Provider` (`models.py:88`) | Only tailnet agents: `tailnet_base_url` = `http://{dial_host}:{port}/v1`, **no upstream auth**, liveness via heartbeat. No base-URL/key field. |
| Forward | `_ChatOrCompletionsProxy.post` (`openai_views.py:659`) | `requests.post(endpoint, json=body, verify=False, proxies=_tailnet_proxies())` — no `Authorization` ever attached. Re-implemented in `agent.py`, `jobs.py`, `chat_threads.py`, `narration.py`. |
| Routing | `_find_provider_for_model` (`openai_views.py:439`) | Resolves a slug → one `ProviderModel`; hard-filters `.exclude(provider__tailnet_hostname="")` + `is_online`. |
| Catalog | `/v1/models` `ModelsView` (`openai_views.py:476`) | Per-user, from `ProviderModel` rows; entry = `{id, owned_by, **caps}`. No `provider`/`external` field. |
| Keys | `external_keys.py` + `UserApiKey` (`accounts/models.py:253`) | Registry of `ExternalService(slug,name,description,docs_url,env_setting)`; Fernet-encrypted, write-only, per `(user,service)`; `get_user_api_key(user,slug)`. Entries: brave/elevenlabs/openai. **No base_url/category/validation.** |
| Keys UI | `/dashboard/settings/api-keys` | Server-driven cards; new registry entries render automatically. |
| Picker | `ModelPicker.vue` + `usePlayground.ts` | Takes `ModelInfo[]`; shows id + modality icons + readiness. **No provider badge.** `listModels()` maps `/v1/models`. |
| Fallback pref | `CustomUser.routing_preference` (`accounts/models.py`) | `ANY/PREFER_OWN/ONLY_OWN`. Good neighbor for a `fallback_model` field. |
| Brand badges | `EngineLogo.vue` + `useEngines.ts` | Brand tile + registry; add `openrouter`/`nvidia`/`groq` entries for badges. |

---

## 4. Keys — extend the registry

Widen `ExternalService` with the fields LLM providers need (tools like brave never
did): `category` (`"tool"` | `"llm_provider"`), `base_url` (OpenAI-compatible root,
e.g. `https://openrouter.ai/api/v1`), `models_path` (default `/models`), and an
optional `key_test_path`. Add three entries:

| slug | base_url | docs |
|---|---|---|
| `openrouter` | `https://openrouter.ai/api/v1` | openrouter.ai/keys |
| `nvidia` | `https://integrate.api.nvidia.com/v1` | build.nvidia.com |
| `groq` | `https://api.groq.com/openai/v1` | console.groq.com/keys |

The keys page renders them automatically. The "LLM provider" category lets the UI
group them and gate model-pinning behind a set key. **Optional** light validation:
a `GET {base_url}{models_path}` with the key on save (200 → valid) — best-effort,
non-blocking.

---

## 5. Pinned models

New model `PinnedModel(user, provider, model_id, display_name, context_length,
input_modalities, supported_features, metadata, created_on)`, unique
`(user, provider, model_id)`. `model_id` is the **upstream** id (e.g.
`anthropic/claude-3.7-sonnet`); the public/namespaced id is
**`{provider}:{model_id}`** (colon-separated — upstream ids contain `/`).

API (owner-scoped, `IsAuthenticated`):
- `GET /api/inference/providers/<slug>/models?q=` — fetch the provider's catalog
  with the user's key (cached per-provider ~1 h; the list is user-agnostic),
  annotate each with `pinned`. 400 if no key set.
- `POST /api/inference/providers/<slug>/pins` `{model_id}` — pin (snapshots
  display name/caps from the catalog).
- `DELETE /api/inference/providers/<slug>/pins/<model_id>` — unpin.

UI: each LLM-provider card on the keys page (once a key is set) gets a **Browse &
pin models** panel — search the catalog, toggle pins. Pinned models then flow into
the picker.

---

## 6. Routing — one shared forward

Introduce `resolve_llm_target(user, model_id) -> LlmTarget` (new
`external_providers.py`), the single resolver both the proxy and the agent call:

```
LlmTarget = {
  kind: "tailnet" | "external",
  base_url, upstream_model, headers, verify, proxies,
  provider_model (tailnet) | provider_slug+label (external),
}
```

- `model_id` is `slug:upstream` for a known LLM-provider slug **and** the user has
  a key → external target (`base_url` from registry, `headers={Authorization:
  Bearer <key>}`, `upstream_model=upstream`, `verify=True`, `proxies=None`).
- otherwise → wrap the existing tailnet `_find_provider_for_model`.

A companion `forward_llm(target, body, stream)` centralizes the `requests.post`
(the one place that knows verify/proxies/headers), so the proxy and agent stop
duplicating it. `/v1/models` appends the user's pinned external models with
`{id: "slug:upstream", owned_by: label, provider: slug, provider_label, external:
true, service_type:"llm", **caps}`.

`InferenceRequest` logging for external calls: `provider=None`,
`dispatch_meta={"external_provider": slug, "model": upstream}`, `model_name` = the
namespaced id; token usage still parsed from the response. Request-detail shows
the provider label.

**api.inference.club** works automatically — same `/v1` proxy, same resolver; a
Bearer-token API client just sends `model: "groq:llama-3.3-70b-versatile"`.

---

## 7. Fallback

`CustomUser.fallback_model` (CharField, blank = off) — any model id, including an
external `slug:upstream`. Behavior (the chosen policy): the proxy/agent fall back
when the requested model **has no available node** (`no_provider`) **or** the
call **errors/times out** (`upstream_error`). Exactly one fallback hop (no
fallback-of-fallback); skipped if the fallback equals the requested model or is
itself unresolvable. Settings page (`/dashboard/settings/fallback`, cloned from
the routing page) picks it from the user's available + pinned models, with a
clear "off" option and a note that an external fallback spends the user's key.

---

## 8. Frontend

- `ModelInfo` gains `provider?`, `provider_label?`, `external?`; `ModelPicker`
  rows + trigger show a provider badge (`EngineLogo`/`Badge`); external models may
  group under a provider header. `useEngines` gains brand entries.
- Keys page: provider cards grouped (LLM providers vs tools) + the browse/pin
  panel (§5).
- Fallback settings page (§7); `useAuth.updateAccount` allow-list + `/api/account/`
  serializer gain `fallback_model`.

---

## 9. Phasing

| Phase | Theme | Gate |
|---|---|---|
| **V0** | Keys: registry (`category`/`base_url`) + 3 providers + brand badges + optional validation. | Store an OpenRouter/Groq/NVIDIA key in settings; it round-trips masked. |
| **V1** | Pinned models + browse/pin API & UI + `/v1/models` injection + `resolve_llm_target`/`forward_llm` + chat proxy routes external + picker badge. | Pin a Groq model, pick it in chat, get a reply — on inference.club **and** via `api.inference.club`. |
| **V2** | Agent loop uses the shared resolver → external models work in the agent. | Run the playground agent on a pinned OpenRouter model. |
| **V3** | `fallback_model` + settings page + proxy/agent fallback on no-provider + error. | Kill your local node; the request transparently completes on the fallback. |
| **V4** | Polish: async jobs / chat-title / narration external support; key validation; surface that external = your spend. | Async + title-gen work with external models. |

---

## 10. Open questions

1. **Catalog cache** — per-provider global cache (user-agnostic list) vs per-user?
   (Lean: per-provider, ~1 h TTL; any user's key can refresh it.)
2. **NVIDIA model ids** — NIM ids look like `meta/llama-3.1-405b-instruct`; confirm
   the `/models` shape matches OpenAI's `{data:[{id}]}`. (It does, but caps are
   sparse — default modalities to text.)
3. **Reasoning/tools capability** — external `/models` rarely declares
   `supported_features`; assume `tools` for chat models and let failures degrade
   (the agent already retries tool-less on 400).
4. **Rate-limit/billing errors** — pass the provider's 429/402 through verbatim so
   the user sees "insufficient credits" etc.
