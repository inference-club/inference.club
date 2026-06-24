---
title: The platform
description: The cloud control plane — the Hetzner deployment, Django and Celery, object storage, auth, and CI/CD.
category: Architecture
order: 3
---

# The platform

The control plane is one small cloud server doing a lot of coordination and no GPU work. It's deliberately replaceable: everything durable lives in the database and object storage, so the box itself can be torn down and rebuilt.

## Where it runs

A single **Hetzner** VPS runs the whole control plane as a Docker Compose stack, with a cloud firewall that allows only ports 22, 80, and 443 — every other path in is closed, so the tailnet is the only way to reach compute. **Caddy** sits in front: it issues Let's Encrypt certificates, serves the Nuxt frontend at the apex domain, and proxies the API at `api.` with response buffering disabled so streaming works.

The whole server is described as code with **Pulumi** (TypeScript). Provisioning the box, rendering the Compose/Caddy/env files, generating secrets, and rolling a new release are all `pulumi up` — there's no hand-configured server to drift.

## The backend

The API is **Django**. One container image runs four roles with different commands:

- the **web** process (gunicorn) serving the API and dashboard,
- a **Celery worker** running [async jobs](/docs/services/direct-vs-async),
- a **Celery beat** tick that dispatches queued work,
- a **prober** that checks each provider's health over the tailnet.

Behind them: **Postgres** as the source of truth, and **Redis** as both the shared cache (rate limiting and usage metering across workers) and the Celery broker. Async is opt-in — it only turns on when a broker is present, and the synchronous proxy path is completely independent of it.

::callout{type="note" title="One image, four jobs"}
Because the web, worker, beat, and prober all run the same backend image, a single backend change rebuilds and redeploys all of them together — there's no version skew between the API and the jobs that run alongside it.
::

## Media storage

Generated media never round-trips through the small VPS. Images, audio, video, and 3D are written to **Google Cloud Storage** and served straight from Google's edge:

- a **public** bucket holds generated output and is world-readable, so browsers fetch results directly from storage — keeping the heavy bytes off the VPS;
- a **private** bucket holds owner-gated inputs (like uploaded voice samples) and is reachable only through an authenticated route with short-lived signed URLs.

Object keys embed a UUID so public URLs are unguessable, and the buckets are retained even if the server is rebuilt — tearing down the box never takes user media with it.

## Auth & access {#auth}

Sign-in is **GitHub OAuth** for full members; a member's API token is what authenticates both inference calls and the agent. Two lighter pathways exist for trying the playground without a GitHub account — one-click **guests** and admin-issued **passcodes** — both playground-only: they never hold API tokens or register compute, and they're off by default. Every account carries a canonical handle, and members can run in an alias mode that keeps nothing public tied to their GitHub identity. A membership check gates compute and token endpoints; most public reads are open.

## CI/CD

Pushing to `main` builds the frontend and backend images and pushes them to the GitHub Container Registry, which triggers a Pulumi deploy that ships the rendered config to the VPS and rolls the new image. The cluster side deploys separately, by applying manifests from its own repo. The two never share a pipeline — they only meet over the tailnet at runtime.

::callout{type="note" title="Self-hosting"}
The whole platform is open source. If you'd rather run your own instance than use the hosted one, the deploy is the same Pulumi + Hetzner + Compose path described here — see the [FAQ](/docs/faq#is-there-a-self-hosted-option).
::
