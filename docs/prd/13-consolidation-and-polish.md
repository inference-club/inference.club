# PRD 13 — Consolidation & Polish (get inference.club back on track)

**Status:** in progress (started 2026-06-15)
**Owner:** Brian (primary + only user for now)
**Why now:** The last few weeks added a lot of surface area fast — narration
studio, workflows/nodes, cluster viz, async jobs, voice cloning. The platform
is capable but uneven: stale data leaks into the UI, pages overlap, mobile is
rough, and internal integer IDs leak to the user. This PRD is a deliberate
*consolidation* pass: make what exists correct, coherent, and pleasant, so the
real goal — **producing valuable content by composing the LLM/image/video/audio
services** — gets easier, not harder.

The north star is **Brian's own daily use**, not user growth. Every item below is
judged by "does this make it nicer / faster / more correct for me to make
content here."

---

## Status (2026-06-16) — first pass complete

All six concrete items below shipped as verified, committed changes (local
checkpoints, not yet pushed). Each was checked in the running app via the
Playwright harness in `.captures/` (before/after screenshots + video).

| # | Item | Commit | State |
|---|------|--------|-------|
| 1 | Mobile music player (scrub bar + compact bar) | d66a2e5 | done |
| 2 | Hide stale/offline models from catalog | 269694c | done |
| 3 | Pulsing readiness dot (catalog + playground) | d1ab552 | done |
| 4 | Request → node/owner/GPU links | 453e455 | done |
| 6 | Opaque public_id for InferenceRequest URLs | 22fba01 | done (1 model) |
| 5 | Fold Models into Compute nav group | a343a06 | first step |

**Follow-ups carried forward:** extend public_id (#6) to Workflow / Episode /
Segment / Batch (same additive pattern, one model at a time); deeper #5 —
merge my-nodes + all-nodes into one "Nodes" page with a mine/all toggle (the
two backend list views are near-identical) and add a provider/node detail
page (request cards now link to `/{owner}` + `/{owner}/cluster`, but a
dedicated node page would be richer). Extend the readiness dot to the other
playground pages (images/video/tts/etc.) using the shared `ReadinessDot`.

## Tonight's execution queue (concrete, user-requested)

Each ships as a focused change, verified in the running app and captured on video
(Playwright → `.captures/`, gitignored).

1. **Mobile music page + player** — compact, usable layout on small screens.
   Player bar currently hides seek/volume/shuffle below `sm`, fixed 80px height,
   no `<sm` grid fallback. Make it phone-first: visible seek, tighter rows,
   1-col grid fallback, smaller controls. *(self-contained frontend)*

2. **Playground data quality** — stop showing stale/retired services & models.
   Playground model dropdowns must reflect only services that are *currently
   advertised by an online provider*. Audit the discovery endpoint + liveness
   window; prune/segregate offline entries. *(backend + frontend)*

3. **Playground readiness indicator** — per selected model, show a live
   "reachable & ready" signal (pulsing green dot when an online provider can
   serve it; amber/gray otherwise). Builds on #2's liveness data.

4. **Inference request → agent / GPU / provider links.** Today the card/detail
   show provider *name* as plain text. Make provider a link (to a provider
   page), surface the GPU/host it ran on, and link the provider's owner/public
   page. Requires: expose `dispatch_meta.host_id` + GPU on the serializer; add a
   provider detail route; (optional) `Provider.public_url`.

5. **Consolidate service-listing pages.** `my-nodes`, `all-nodes`, cluster viz,
   playground selectors, and `/models` all show overlapping "what can run"
   data. Define one canonical "Services/Network" surface and make the others
   link into it rather than re-implement.

6. **Opaque public IDs (non-destructive).** Stop exposing sequential integer PKs
   in URLs/API for user-facing models (InferenceRequest, Workflow, Episode,
   Segment, Batch, etc.). Reuse the existing `share_token` precedent: add a
   `public_id = token_urlsafe(...)` field per model, look up by it, keep old int
   routes working as fallback/redirect. **No PK swap** — additive only, so it's
   non-destructive in prod. Roll out one model at a time, starting with
   InferenceRequest.

---

## Broader improvement backlog (the areas you named)

### A. Data quality & correctness (foundational — unblocks everything)
- Single source of truth for "what services/models are available right now":
  one endpoint, liveness-filtered, used by playground + cluster + home.
- Prune or clearly mark retired providers/services/models; never silently show
  dead ones in pickers.
- Liveness window + prober coverage audit (PROVIDER_LAST_SEEN_WINDOW); make the
  "online" definition explicit and consistent across pages.

### B. Content production (the actual goal)
- Make the URL→video / narration→video pipelines first-class and reliable end
  to end (they exist from PRD 12 but need polish + a "make content" entry point).
- A "New content" launcher that composes services (LLM script → TTS → images →
  compose) without hand-wiring a workflow each time. Templates as starting points.
- Better preflight: before a run, show exactly which services are missing and a
  one-click path to bring them online (scale-from-zero hint).

### C. Agentic-coding leverage (your productivity as an engineer)
- Codify parallel-Claude workflows: worktree-per-task conventions, a short
  CONTRIBUTING/AGENTS doc describing how to run the stack, where things live,
  and the verify loop (this PRD + the memory files are the seed).
- Standard "verify in the running app" harness (the Playwright capture helper
  added this session) reusable across changes.
- Lean on the existing roadmap.py board as the shared task ledger across agents.

### D. Tooling & home-lab friction (sudo-over-ssh, manual one-offs, k3s)
- Inventory the recurring manual steps (the "I fix it up front then hit it
  again" class) and turn each into a script or a k8s Job/CronJob so it's
  declarative and repeatable. Keep leaning on k3s as the control plane.
- Document the kubeconfig / port / agent-discovery facts in one place (seeded in
  memory already) so they stop being re-derived.

### E. Secrets & key management (recurring pain)
- One inventory of every key (GitHub, inference.club tokens, provider/API keys,
  registry) — what it's for, where it lives, how it's rotated.
- Move toward a single source (sealed-secrets / external-secrets in k3s, or a
  password manager + a sync script) instead of scattered `.env` files.
- Stop committing the pattern of "solve once, forget, re-hit."

---

## Principles
- **Non-destructive.** Additive migrations, no PK swaps, no data deletion without
  explicit ask. Old routes keep working.
- **Verify in the real app.** Every UI change gets a before/after capture.
- **Consolidate before adding.** Prefer linking into one canonical surface over
  building a parallel one.
- **Correctness first.** Stale/incorrect data is the highest-leverage fix because
  it undermines trust in everything else.
</content>
</invoke>
