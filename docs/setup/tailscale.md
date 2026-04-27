# Tailscale setup

The data plane between `api.inference.club` and provider agents is a
private Tailscale tailnet. This doc covers the one-time setup —
account, tags, ACL, auth keys.

For *why* this design (vs public callback URLs), see the [blog post](https://inference.club/blog/tailscale-and-tsnet)
and the [agent integration plan](../plans/tailscale-agent-integration.md).

## 1. Create the tailnet

1. <https://login.tailscale.com> → **Sign in with GitHub**
2. The free **Personal** tier is fine — allows 100 devices, plenty of
   headroom for the MVP

That's it for account setup. Tailscale auto-creates a tailnet for you.

## 2. Find your tailnet name

Look at the top-left of the Tailscale admin console. You'll see
something like `briancaffey.github` (GitHub-org-style names) or
`tailABC123.ts.net` (random short name).

The **MagicDNS suffix** is what you actually need — it's the suffix
Tailscale uses when minting cert-eligible hostnames. To find it:

- Click any device in the admin → look at its FQDN at the top
- Format: `<hostname>.<suffix>.ts.net`
- Example: `club-host-1.tailb224b8.ts.net` → suffix is `tailb224b8`

The suffix is what goes in `TAILSCALE_TAILNET` (see [secrets.md](secrets.md)).
**This is *not* the human-friendly tailnet name** shown in the admin
header — easy mistake to make.

## 3. Create the two tags

In **Access controls** → **Tags** (or the **Tags** sub-page),
create:

- `tag:club-host` — for provider agents
- `tag:club-web` — for the central server's tailnet sidecar

For each: set **Tag owner** to your own GitHub user (so you can mint
keys with these tags).

## 4. Set the ACL policy

In **Access controls**, replace the entire policy file with:

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

Save. This is the entire trust model — `club-web` (the server) can
reach `club-host` (agents) on port 443. Nothing else is allowed.
Agents can't talk to each other, can't talk to the server, can't reach
the public internet through the tailnet.

## 5. Generate two auth keys

In **Settings → Personal Settings → Keys** (or the **Keys** sub-page
of Access controls), generate auth keys, twice. The button is
"Generate auth key".

### Key 1 — for the server-side sidecar

| Field | Value |
|---|---|
| Description | `inference.club server (club-web)` |
| Reusable | **off** |
| Ephemeral | **off** |
| Tags | `tag:club-web` (verify the picker shows this exact value, not `tag:club-host`) |

Save the value as `TAILSCALE_WEB_AUTHKEY` in repo secrets.

### Key 2 — for agents

| Field | Value |
|---|---|
| Description | `inference.club agents (club-host)` |
| Reusable | **on** |
| Ephemeral | **on** |
| Tags | `tag:club-host` |

Save the value as `TAILSCALE_STATIC_AUTHKEY` in repo secrets.

This single reusable key is handed to *every* agent that calls
`/api/inference/agent/register/`. Per-agent OAuth-minted keys are on
the [backlog](../../BACKLOG.md#agent-integration); using a static key
is fine for the MVP.

## 6. Verify

After running `infra-deploy` and bringing up an agent, check the
**Machines** tab. You should see at minimum:

- `club-web` with tag `tag:club-web`, **Connected**
- One or more `club-host-N` machines with tag `tag:club-host`,
  **Connected**

If a machine shows the wrong tag (we hit this twice during early
setup), either edit it via `…` → **Edit ACL tags** for a one-off
fix, *or* regenerate the auth key with the right tag stamped on it
and update the repo secret. The secret is what determines the tag of
all *future* registrations.

## What goes wrong

- **`TAILSCALE_TAILNET` is wrong.** Has to be the MagicDNS suffix
  (`tailb224b8`), not the human-friendly tailnet name
  (`briancaffey.github`). Check by clicking any device in the admin
  and looking at its FQDN
- **Auth key tagged wrong.** The key generation form's tag picker is
  easy to mis-click. Verify after generating — the key detail page
  shows what tag it stamps on devices that join with it
- **Old machines not cleaned up.** Tailscale gives the next-joining
  agent a `-1` suffix when its requested hostname is already taken,
  so a stale `club-host-1` machine in the tailnet means the new agent
  becomes `club-host-1-1` and your DB pointer to `club-host-1` is now
  resolving to the offline old machine. Solution: delete offline
  duplicates in the **Machines** tab
- **ACL doesn't accept the right direction.** The rule is one-way:
  `tag:club-web → tag:club-host:443`, not the reverse. If both tags
  appear on the wrong machines, the server can't reach the agents
  even though everything looks "connected"

## Userspace mode and SOCKS5

The central server's tailnet sidecar runs Tailscale in **userspace
mode** (`TS_USERSPACE=true`) so it doesn't need `NET_ADMIN` or a tun
device. It exposes a SOCKS5 proxy on `:1055` (`TS_SOCKS5_SERVER=":1055"`).
Django reaches the tailnet by setting `proxies={"https": "socks5h://tailscale:1055"}`
on `requests.get/post`. The `socks5h://` scheme tells `requests` to
resolve hostnames through the proxy, which is what makes
`club-host-1` MagicDNS-resolve.

Don't set both `TS_SOCKS5_SERVER` and `TS_OUTBOUND_HTTP_PROXY_LISTEN`
to the same port — they'll collide. We use SOCKS5 only.

## Migrating off Tailscale (later)

The agent already accepts a `TAILSCALE_LOGIN_SERVER` env var, so
pointing it at a self-hosted Headscale instance is a server-side
config flip. The server doesn't care which control plane the tailnet
uses; it just talks to whatever resolves the agents' MagicDNS names.
