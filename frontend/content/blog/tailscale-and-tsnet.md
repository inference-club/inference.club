---
title: "Putting your home GPU on the internet with Tailscale and tsnet"
description: "How inference.club uses an embedded Tailscale stack on the agent and a userspace sidecar on the server to route LLM traffic from a public OpenAI-compatible API into a private GPU on someone's home network — with no port forwarding, no public callback URLs, and no shared secrets per device."
publishedAt: 2026-04-26
author: briancaffey
tags: [architecture, tailscale, networking, deep-dive]
image: /images/blog/tailscale-and-tsnet.png
image_prompt: "Wide cinematic abstract illustration: a secure glowing tunnel of cyan and violet light connecting a cloud API icon to a small house containing a glowing GPU, encrypted private mesh network, subtle shield and lock motif, dark moody futuristic, soft glow, no text, no words, no letters"
---

The hard problem in a community-run inference network isn't the inference. There are five mature open-source LLM servers (vLLM, Ollama, LM Studio, llama.cpp, TGI) and they all speak OpenAI's HTTP shape out of the box. The hard problem is *routing* — getting a request from `api.inference.club` (a public Hetzner VPS in Nuremberg) into a 4090 sitting under someone's desk in San Francisco, with no port forwarding, no public hostname on the home end, and no shared password per device.

The naive design works locally and breaks the moment you deploy it: have each provider expose a public callback URL, register it with the platform, and have the server proxy requests there. That gets you a NAT problem (most home networks aren't reachable from the internet), a security problem (the agent's HTTP endpoint is now on the public internet), and a trust problem (anyone who finds the hostname can hit the agent).

This is the post about how we made the routing problem disappear by using **Tailscale** as the data plane and `tsnet` to embed it directly in the agent's Go binary. Both repos are open source — [`inference.club`](https://github.com/inference-club/inference.club) (this server) and [`inference-club-agent`](https://github.com/inference-club/inference-club-agent) (the home-side agent) — so you can read the actual code as you read this.

## The five-second version

```
Your client (OpenAI SDK, Open WebUI, curl)
       │
       │  Authorization: Bearer ic-…
       ▼
api.inference.club            ┌── tailscale sidecar
 (Django + gunicorn  ◄────────┤   (userspace, joined as `club-web`)
  on Hetzner)                 └── SOCKS5 :1055 → tailnet
       │
       │  proxies via SOCKS5 to club-host-N over tailnet
       ▼
   ╭─── inference.club tailnet (private WireGuard mesh) ───╮
   │                                                       │
   │   club-host-1   club-host-2   club-host-3   …         │
   │   (your laptop) (your homelab) (rented box)           │
   ╰───────────────────────────────────────────────────────╯
       │
       │  reverse-proxy /v1/* to LOCAL_LLM_URL
       ▼
vLLM / Ollama / LM Studio / llama.cpp
 (the actual GPU)
```

There are exactly two new pieces of code you wouldn't find in a normal "Django app proxies to a private API" setup:

1. **`tsnet`** — Tailscale's library form, embedded into the agent's Go binary so the agent *is* a Tailscale node without needing the user to install anything Tailscale-specific.
2. **A Tailscale userspace sidecar** alongside the server, exposing a SOCKS5 proxy that the Django process uses to reach the tailnet by name.

Everything else is existing tools doing what they already do.

## Why Tailscale specifically

The first prototype of inference.club had `Provider.callback_url` as a free-form public URL — agents would heartbeat in saying "I'm at `https://my-rig.example.com:8443/v1`" and the server would proxy there. We shipped that to nobody because it has three painful problems:

**The NAT problem.** Most home networks don't have a public IP per device. Provider has to choose between port-forwarding (router config that varies by ISP, fragile, sometimes literally not allowed), buying a static-IP plan, or running a tunnel like Cloudflare Tunnel or ngrok. Each of these is a step the provider has to do *before* they can install the agent — i.e., before they have any signal that the rest of the system works.

**The exposure problem.** A public HTTP endpoint that proxies straight to your local LLM server is a shaped charge pointing at your GPU box. Even if the LLM server itself is hardened, you've added an attack surface that didn't need to exist.

**The shared-secret problem.** The agent now needs to verify that incoming requests really came from the platform — otherwise a random caller from the internet just gets free inference on your GPU. So you ship a per-agent shared secret, the agent checks signatures on every request, and you're maintaining yet another credential store.

Tailscale collapses all three. The agent joins a private mesh; the server joins the same mesh; nothing is exposed to the public internet. Tailscale's ACLs handle "the server can talk to agents, agents can't talk to anything else" with a four-line policy. WireGuard handles the encryption. MagicDNS handles the addressing. We don't write code for any of those things.

## tsnet on the agent: one Go binary, no Tailscale install

The standard way to put a machine on a tailnet is `tailscaled` — Tailscale's daemon. That's a real install. For an agent we want a one-Docker-command experience:

```bash
docker run -d --name club-host \
  -e INFERENCE_CLUB_API_KEY=ic-… \
  -e LOCAL_LLM_URL=http://192.168.5.253:8000/v1 \
  ghcr.io/inference-club/inference-club-agent:latest
```

`tsnet` is Tailscale-as-a-library. You import it from Go, give it a hostname and an auth key, and it stands up its own Tailscale node *inside your process* — its own WireGuard endpoint, its own IP on the tailnet, its own MagicDNS name. The user doesn't install Tailscale; our Go binary `is` Tailscale.

The agent's whole tailnet-side setup is about a dozen lines:

```go
srv := &tsnet.Server{
    Hostname: cfg.Hostname,        // "club-host"
    Dir:      cfg.StateDir,        // /var/lib/club-host
    AuthKey:  cachedAuthKey,       // tskey-auth-...
}
listener, err := srv.Listen("tcp", ":443")
if err != nil { log.Fatal(err) }

mux := http.NewServeMux()
mux.HandleFunc("/healthz", okHandler)
mux.Handle("/v1/", newOpenAIProxy(localLLM))

http.Server{Handler: mux}.Serve(listener)
```

`srv.Listen("tcp", ":443")` returns a normal Go `net.Listener` — but it's listening *on the tailnet*, not on any local interface. There is no port 443 on the host machine to scan. Other tailnet nodes can reach it as `club-host-N:443`; nobody else can.

The auth key isn't built into the agent — the agent gets it from inference.club on first run. More on that below.

## The userspace sidecar on the server: SOCKS5 into the tailnet

The server side of this is more interesting because Django is Python, not Go, and we're not going to embed Tailscale in CPython. Instead we run a Tailscale container alongside the backend in `docker compose`:

```yaml
services:
  tailscale:
    image: tailscale/tailscale:stable
    hostname: club-web
    environment:
      TS_AUTHKEY: ${TAILSCALE_WEB_AUTHKEY}
      TS_USERSPACE: "true"
      TS_EXTRA_ARGS: "--advertise-tags=tag:club-web"
      TS_SOCKS5_SERVER: ":1055"
    volumes:
      - tailscale-state:/var/lib/tailscale

  backend:
    image: ghcr.io/inference-club/inference-club-backend:latest
    environment:
      TAILNET_PROXY_URL: socks5h://tailscale:1055
    depends_on: [tailscale]
```

`TS_USERSPACE=true` is the magic flag. Normally Tailscale wants to create a `tailscale0` network interface on the host kernel — but we're inside a container, the host kernel isn't ours, and we don't actually want a tun device. Userspace mode runs the WireGuard stack entirely in user space and exposes the tailnet via a SOCKS5 proxy on `:1055` instead. From Django's perspective, reaching the tailnet is just a SOCKS proxy — no kernel networking, no special privileges, no `--cap-add NET_ADMIN`.

Django speaks SOCKS5 with a one-line `requests` install (`pip install 'requests[socks]'`) and a `proxies=` argument:

```python
def _tailnet_proxies():
    url = settings.TAILNET_PROXY_URL  # "socks5h://tailscale:1055"
    return {"http": url, "https": url} if url else None

def refresh_provider_models(provider):
    resp = requests.get(
        provider.tailnet_base_url + "/models",     # http://club-host-1:443/v1/models
        proxies=_tailnet_proxies(),
        timeout=10,
    )
    ...
```

The `socks5h://` scheme (note the `h`) tells the proxy to *resolve hostnames remotely* — the SOCKS server (Tailscale) does the DNS lookup, which is what makes `club-host-1` MagicDNS-resolve to the right tailnet IP. Plain `socks5://` resolves locally, which doesn't know anything about the tailnet.

## The trust model: ACLs, not shared secrets

The sidecar is tagged `tag:club-web`. Each agent's tailnet node is tagged `tag:club-host`. The Tailscale policy is four lines:

```jsonc
{
  "tagOwners": {
    "tag:club-host": ["autogroup:admin"],
    "tag:club-web":  ["autogroup:admin"]
  },
  "acls": [
    { "action": "accept", "src": ["tag:club-web"], "dst": ["tag:club-host:443"] }
  ]
}
```

That's the entire authorization story between the central server and every agent on the network. `club-web` can reach `club-host` on port 443. Not the other way around (so a compromised agent can't pivot to the central server, or to a peer agent). Not on any other port. Nothing else.

Per-agent shared secrets, request signing, mTLS — none of it. The mesh itself is the perimeter.

## How the auth key gets to the agent: register-once

The agent's `tsnet` needs a Tailscale auth key to join. We don't want users creating Tailscale accounts to use inference.club, so the platform mints keys on their behalf.

The first time the agent boots, it has nothing cached. It POSTs to inference.club's HTTP API:

```http
POST https://api.inference.club/api/inference/agent/register/
Authorization: Bearer ic-<user's API key>
Content-Type: application/json

{ "name": "club-host", "agent_port": 443 }
```

The server authenticates the bearer token (it's the same API key the user uses to call `/v1/chat/completions` — one credential covers consumer and provider roles), creates a `Provider` row keyed on `(user, name)`, and mints a Tailscale auth key for it. The response:

```json
{
  "provider_id": 17,
  "tailscale_authkey": "tskey-auth-...",
  "tailnet_hostname": "club-host-17"
}
```

The agent persists `tailscale_authkey` to disk and never asks again. Subsequent restarts use the cached key. The user's inference.club API key isn't needed after the first register.

Auth-key minting has two paths in the server:

**Production:** a Tailscale OAuth client mints a *fresh ephemeral, preauthorized, tagged* key per provider. The key is single-use (ephemeral means the device is auto-deleted when it goes offline), tagged `tag:club-host` so the ACL applies, and preauthorized so the user doesn't need to click anything.

**Bootstrap (what we're running today):** a single static reusable+ephemeral+tagged auth key, configured server-side as `TAILSCALE_STATIC_AUTHKEY`, returned to every agent that registers. Less per-agent isolation, but trivial to set up while iterating.

The fallback path is there because it lets us prove the architecture works before we wire up an OAuth client.

## A request, end-to-end

Here's what happens when you do this from your laptop:

```bash
curl https://api.inference.club/v1/chat/completions \
  -H "Authorization: Bearer ic-…" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-8b","messages":[{"role":"user","content":"hi"}]}'
```

1. **Caddy on the Hetzner VPS** terminates TLS on `api.inference.club:443`, reverse-proxies to the `backend` container.
2. **Django + DRF** authenticates the bearer token against `rest_framework.authtoken`, looks up the user, finds an online `Provider` they own that serves `qwen3-8b`. (For the MVP, "online" just means the provider has been seen in the last 2 minutes; there's a synchronous discovery fallback that hits `/v1/models` on the agent if no models are cached yet.)
3. **The proxy view** constructs the upstream URL: `http://club-host-17:443/v1/chat/completions`. Plain HTTP, short MagicDNS hostname.
4. **Python `requests`** sees `proxies={"https": "socks5h://tailscale:1055"}` in the call and routes the request through the SOCKS5 proxy on the sidecar.
5. **The sidecar** resolves `club-host-17` via Tailscale's MagicDNS to the tailnet IP `100.x.y.z`, opens a WireGuard tunnel, sends the HTTP request bytes through it.
6. **The agent's `tsnet`** receives the bytes on its tailnet listener, hands them to the Go HTTP server, which routes `/v1/*` to the reverse proxy.
7. **The reverse proxy** forwards to `LOCAL_LLM_URL` — `http://192.168.5.253:8000/v1/chat/completions` on the user's LAN.
8. **vLLM (or whatever)** does the actual inference and streams the response back along the same path. SSE streams pass through unbuffered both at the agent's reverse proxy (`FlushInterval: -1`) and at Caddy on the way back out (`flush_interval -1`), so completions arrive in real time.

Latency overhead from the platform side is two TCP RTTs (browser → Caddy → backend → sidecar → tailnet) plus whatever Tailscale's WireGuard adds, which in practice is dominated by the geographic distance between the server and the agent. The Hetzner box is in Nuremberg, so European agents see ~30ms of overhead and US agents see ~100ms — small relative to the seconds-to-minutes of actual generation time.

## What we *don't* have

The agent's `/v1/*` endpoint trusts any caller that can reach it on the tailnet. The Tailscale ACL is the only thing keeping randos out — there's no per-request HMAC, no signed token from the central server. That's fine *because* of the ACL — only one tagged source can reach `tag:club-host:443` — but a defense-in-depth pass before public launch is on the [backlog](https://github.com/inference-club/inference.club/blob/main/BACKLOG.md).

There's also no per-agent OAuth-minted key yet — every agent gets the same static key. Same backlog.

And there's no cross-user routing yet: your requests only hit your agents. The whole point of a community network is shared compute, but locking it down per-user for v0 lets us figure out the trust and accounting story before we have to.

## Why this design ages well

The same pattern works whether you have 5 providers or 5000. Adding a new provider means: agent boots, calls `/api/inference/agent/register/`, gets a tailnet identity, joins. The server doesn't need to know the agent's IP, doesn't need to manage port forwarding rules, doesn't need to provision DNS. The mesh grows itself.

If we ever need to migrate off Tailscale (Headscale for self-hosted, or rolling our own mesh later), the abstraction is small enough to swap. The agent already has a `TAILSCALE_LOGIN_SERVER` env var so it can point at a Headscale endpoint instead. The server side is just "the URL we give to `requests.get()`" — change the protocol and it follows.

Most importantly, the security boundary is something we didn't design and don't maintain. WireGuard is audited. Tailscale's coordination server is audited. Their ACL evaluator is audited. We get to focus on the parts of the system that are actually *ours* — the API, the routing logic, the dashboard — and let the network plumbing be someone else's problem.

That's the post. The whole thing is ~50 lines of Go in the agent and ~100 lines of Python in the server. The ratio of "lines we wrote" to "capability we got" is the best I've felt about an architecture decision in a long time.

If you want to try it: [quickstart](/docs/quickstart) for using the API, [run-an-agent](/docs/providers/run-an-agent) for putting your hardware on the network. Or read the code: [`inference.club`](https://github.com/inference-club/inference.club) and [`inference-club-agent`](https://github.com/inference-club/inference-club-agent).
