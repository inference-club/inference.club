---
title: "One app, three environments: self-hosting inference.club on my home cluster"
description: "inference.club is a hosted app, but it's also something you can run yourself — to catalog your own inference across LLM, image, video, music, voice, and 3D. Here's how the same Django + Nuxt app runs unchanged across a laptop, a cloud VPS, and a home k3s cluster, deployed by a fully self-hosted GitOps loop (Forgejo → Harbor → Argo CD) with no managed cloud in the path."
publishedAt: "2026-07-09"
author: briancaffey
tags: [homelab, k3s, gitops, self-hosting, architecture, deep-dive]
image_prompt: "Wide cinematic abstract illustration: three distinct glowing portals on the left — a small laptop, a distant cloud, and a cluster of home servers — each streaming a river of cyan and violet light that converges into a single luminous crystalline core on the right, one unified application forming from three sources, subtle circuit and orbital motifs, dark moody futuristic, soft glow, no text, no words, no letters"
---

If you have more than one PC with a GPU in it, you eventually hit the same wall I did. You've got a 4090 making images on one box, an LLM serving on another, maybe a Mac or a Spark doing something in the corner. Each one is genuinely useful. Together they're a drawer full of loose parts. You run a generation, you get a file, and three weeks later you have no idea which model made it, on which machine, with what prompt, or how to do it again.

[inference.club](https://github.com/inference-club/inference.club) started as the hosted network you already know — share your home GPU, call it from a public OpenAI-compatible API. But the app underneath it turns out to be exactly the thing that drawer of parts is missing: a place that *catalogs* your inference. Every request across every modality — LLM, image, video, music, voice, 3D mesh — lands in one backend with a record. What model, what hardware, what parameters, what came out. A trail you can search, reproduce, star, and study.

So this post is about a different way to run it: **not** as a member of the public network, but as your own private instance, on your own hardware, for your own use. The [last post](/blog/from-docker-sprawl-to-k3s) was about moving my inference *services* onto a home k3s cluster. This one is the natural sequel — once your GPUs are a cluster, you put the management layer on top of them. And the interesting part isn't the deployment; it's what it took to make **one app run correctly in three completely different environments** without forking a single line of code.

## The five-second version

inference.club runs in three places, and the *only* thing that differs between them is configuration:

```
                 ONE codebase (Django backend + Nuxt frontend)
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
  DEVELOPMENT                  PRODUCTION                    HOME LAB
  laptop                       Hetzner VPS                  k3s cluster
  docker compose               cloud, public               club.lan, private
  ──────────────               ─────────────               ────────────
  GitHub sign-in (dev)         GitHub OAuth                 email + confirm link
  local images                 images from GHCR             images from Harbor
  hot reload                   two subdomains               one host, path-routed
                               (api. + app)                 (Traefik)
                                                              │
                                             self-hosted GitOps loop:
                                    push → Forgejo CI → Harbor → Argo CD → club.lan
                                                              │
                                    same fleet already serving inference:
                                    a1 · a2 · a3 (RTX 4090) + spark (DGX GB10)
```

No `if HOMELAB:` branches in the code. Auth, email, storage, image source, hostnames — all of it is read from the environment at boot. The home-lab deployment is a folder of Kubernetes manifests and a Secret, and the app never knows it's special.

## The niche: cataloging your own inference

If you've been down the self-hosting road, you know the shape of the good software out there. [Immich](https://immich.app/) gives your photos a home that isn't someone's cloud. [Jellyfin](https://jellyfin.org/) does it for your movies, [Audiobookshelf](https://www.audiobookshelf.org/) for your audiobooks and podcasts. (I run the last two on this very cluster, next to the GPU services — the media server and the audiobook server are one `kubectl apply` away from the thing making the videos.)

Each of those tools owns one category of *media*. What none of them do — what nothing I could find does well — is own your **inference**. The generations themselves: the prompt, the model, the seed, the machine, the latency, the output. That's the niche inference.club fills when you self-host it. It's the Immich of "I made this with a model," across every modality at once.

Why would you want that? A few reasons that are all really the same reason:

- **Reproducibility.** "This exact GLB came out of TRELLIS on the Spark, from this image, in 243 seconds." The record is the receipt.
- **Research and study.** If you're trying to actually *understand* how these models behave — logprobs, sampler settings, how the same prompt lands on different hardware — you need the runs saved and comparable, not scattered across five web UIs.
- **A backend for your own tools.** Once every generation has a stable ID and a URL, you can build on top: collections, playlists, workflows, a 3D map of your own cluster.
- **Plain interest.** It's genuinely nice to open one page and see everything your machines have made.

The hosted network and the self-hosted instance are the same app pointed at different hardware. On the public network your requests fan out to other people's GPUs; on your private instance they stay home. The catalog works identically either way.

## The real work: one app, three environments

Here's the design decision the whole thing rests on, and it's the part worth stealing even if you never touch inference.club: **the app changes behavior by configuration, not by code.** Every environment-specific choice is a capability flag or a URL read from the environment, with a sane default. There is no build for "the home-lab version."

Authentication is the cleanest example. In the cloud, you sign in with GitHub — that's what a public app wants. But in my house, making a GitHub OAuth app just so I can log into my own server is absurd; I don't want my private inference catalog to depend on GitHub being reachable at all. So auth is two independent flags:

```yaml
# home-lab ConfigMap — the entire auth story
AUTH_GITHUB_ENABLED: "False"      # cloud sets this True
AUTH_EMAIL_ENABLED:  "True"       # email + confirmation-link signup
DEPLOY_ENV:          "homelab"    # local | cloud | homelab
```

The backend reads those at startup. The sign-in page asks the backend which methods are live (`{ "github": false, "email": true }`) and renders accordingly. In the home lab you get an email-and-password flow with a confirmation link — and because I don't have (or want) a real outbound mail provider on my LAN, that confirmation email goes to **Mailpit**, a tiny SMTP sink running in the cluster with a web UI at `mailpit.lan`. Sign up, flip to the Mailpit tab, click the link, you're in. No external dependency, no secrets leaving the house.

Nothing about email auth is "the home-lab code path." It's a capability the app has always had, switched on by config. The same is true of storage (MinIO in-cluster vs. GCS in the cloud), the email backend, the allowed hosts, and the image source. Each environment is just a different set of answers to questions the app already knows how to ask.

::blog-note{type="tip"}
If you're designing an app you might one day self-host, make the deployment-specific decisions *capabilities*, not branches. "Which auth methods are enabled" as runtime flags beats `if settings.SELF_HOSTED` scattered through the codebase every time — the self-hosted build and the cloud build stay byte-for-byte identical, which means you're testing one app, not three.
::

## The fun part: a GitOps loop with no cloud in it

This is the part that'll appeal to anyone who's caught the home-lab bug. The production instance builds its images on GitHub Actions and pulls them from GitHub's registry. That's fine — but it means my private, on-prem app depends on GitHub to *change*. For a home lab whose entire point is self-reliance and practice, that felt wrong. So the home-lab deployment closes the loop entirely on-prem:

```
  push to the app repo's Forgejo mirror (main)
        │
        ▼
  Forgejo Actions runner (in the cluster)
        │   docker build ./backend  ./frontend
        ▼
  Harbor  (self-hosted registry, harbor.lan)
        │   push inference-club-{backend,frontend}:<sha12>
        ▼
  bump image tag + APP_VERSION in the deploy repo  [skip ci]
        │
        ▼
  Argo CD  reconciles the change
        │   PreSync migrate Job → roll backend / frontend / celery
        ▼
  club.lan  is running the new commit
```

Every box in that diagram is software running on my own machines. [**Forgejo**](https://forgejo.org/) is the git server *and* the CI — a push to `main` triggers an in-cluster runner that builds both images. [**Harbor**](https://goharbor.io/) is the registry they get pushed to, at `harbor.lan`. A separate `inference-club-deploy` repo holds nothing but the Kubernetes manifests; CI bumps the image tag there and commits it (`[skip ci]`, so it doesn't loop). [**Argo CD**](https://argo-cd.readthedocs.io/) watches that repo and reconciles the cluster to match — running the database migration as a pre-sync job, then rolling the backend, frontend, and Celery workers.

I push code from my laptop; a couple of minutes later `club.lan` is serving it, and GitHub was never in the path. This is deliberately more machinery than a `docker compose pull` would need. That's the point. The reason to build it this way in a home lab is the same reason to lift weights: the reps are the reward. You come out the other side actually understanding GitOps, self-hosted CI, and private registries — on a real app you use every day, not a toy.

Keeping app code and deploy manifests in **separate repos** is the one structural choice I'd insist on. The app repo never contains a cluster hostname or an image tag; the deploy repo never contains application code. CI is the only thing that writes to the deploy repo, and Argo CD is the only thing that reads it. The boundary keeps "what the app is" and "where it runs" from ever bleeding into each other — which is the whole reason the same app can also run on a laptop and a cloud VPS without noticing.

## Networking: match the environment's grain

The cloud instance lives at two subdomains: `api.inference.club` for the backend and the app domain for the frontend. That split makes sense on the public internet, where the API is a product surface with its own TLS cert and its own rate limits.

My first instinct was to mirror that at home — `api.club.lan` and `club.lan`, two certs, two ingresses. Then I stopped, because it's solving a problem I don't have. On my LAN there's exactly one audience (me), one trust boundary, and one wildcard `*.lan` certificate already minted by mkcert for every service in the house. Reproducing the cloud's two-subdomain topology would be over-engineering for its own sake.

So the home-lab instance is a **single host, path-routed**. One `club.lan`, one cert, and Traefik (which k3s ships built-in) sends the API-shaped paths to the backend and everything else to the Nuxt frontend:

```yaml
# club.lan ingress — Traefik prioritises longer prefixes,
# so the specific backend paths win over the frontend catch-all
rules:
  - host: club.lan
    http:
      paths:
        - { path: /api,   backend: backend }
        - { path: /v1,    backend: backend }   # the OpenAI-compatible surface
        - { path: /admin, backend: backend }
        - { path: /media, backend: backend }
        - { path: /,      backend: frontend }  # everything else
```

The insight generalizes past this one app: **match the grain of the environment you're in, don't import the shape of a different one.** The cloud's two-subdomain layout is correct for the cloud. On a single-tenant LAN, one host with path routing is correct, and it's less to run, less to break, and less to hold in your head. Same app, same code, a topology that fits where it lives.

## Knowing exactly what's running

One small thing that matters more in a self-hosted, reproducible setup than it does in the cloud: knowing *which version* you're looking at. When you're the one who pushed the commit ten minutes ago, "is this running my change yet?" is a question you ask constantly.

The backend exposes a tiny public endpoint, `/api/meta/`, that reports its own build:

```json
{ "name": "inference.club", "version": "5ffa0bca7cd3", "env": "homelab" }
```

That `version` is the same 12-character commit SHA that CI stamped onto the image tag and into the ConfigMap — so the string in the URL, the running container, and the git history are guaranteed to agree. The frontend reads it and renders a small version chip. It's a few lines of code, but in a GitOps loop it's the difference between trusting the pipeline and refreshing Argo CD's UI wondering if the sync landed. The `env` field (`local` / `cloud` / `homelab`) is the app telling you, out loud, which of its three lives it's currently living.

## Reaching it from anywhere

A private app that only works when you're home is a fraction as useful as one you can reach from the train. The home-lab instance rides the same [Tailscale](/blog/tailscale-and-tsnet) tailnet the rest of the fleet already lives on. `club.lan` resolves and serves over the mesh from wherever I am — my laptop in a coffee shop, my phone on cellular — with no port forwarding, no public exposure, and the same mkcert-trusted TLS I get at home.

That's what makes it a genuinely nice daily-use tool instead of a science project. I can kick off a video generation from my phone, and it lands in the same catalog I browse from my desk, served by a 4090 in my apartment, reachable from anywhere, visible to no one but me.

## What's next

The foundation is in place: the app runs in the cluster, the GitOps loop is closed, and the catalog is filling up with runs from every modality the fleet serves. The threads I'm pulling on next:

- **Secrets that live in the cluster.** Right now the app's Secret is created out-of-band by hand. Moving it into the Vaultwarden-backed secret store already running on the cluster closes the last "typed by a human" gap in the deploy.
- **The catalog as a substrate for tools.** With every generation carrying a stable ID, the [3D cluster visualization](/blog/from-docker-sprawl-to-k3s) and the workflow engine both get to treat the home instance as a real backend — including assets generated *by* the cluster being visualized.
- **A documented path for you to do this.** The deploy repo is small and the pattern is general. The goal is a self-host guide clean enough that anyone with a couple of GPU boxes and k3s can stand up their own private inference catalog in an afternoon.

If you run local AI on more than one machine, the pitch is simple: your generations deserve a backend. You already built the hard part — the GPUs, the models, the network. This is the layer that remembers what they made. The code is open — [`inference.club`](https://github.com/inference-club/inference.club) — and the self-hosting story is only getting easier from here.
