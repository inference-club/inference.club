# PRD 05 — Design Quality & Visual Testing

**Status:** in progress (started 2026-06-11)
**Decisions confirmed:** in-app `/design` gallery (no Storybook/Histoire) · Playwright with
overflow guards + curated pixel baselines · tighten the existing shadcn-vue design (no rebrand) ·
local-first, promote to CI once stable.

## Problem

1. **Mobile overflow.** Long unbroken text (prompts, model names, URLs, mono badges) overflows
   cards and makes whole pages scroll sideways on phones. There is no guardrail, so fixes
   regress silently.
2. **No design feedback loop.** No way to see every page/component at desktop + mobile sizes
   without manually clicking through the app in two browser widths. No record of what anything
   looked like before a change.
3. **Inconsistent polish.** Ad-hoc type sizes (`text-[11px]`), uneven spacing rhythm, and
   per-page one-off patterns accumulated across seven modalities shipped fast.
4. **Hidden information.** The API returns more than the UI shows (usage details, provider
   info, generation params, timing). We want density without chaos.

## Approach — five phases, each independently shippable

### Phase 0 — Harness (foundation)
- **Playwright** in `frontend/e2e/`: two projects — `desktop` (1440×900 Chromium) and `mobile`
  (iPhone 14 viewport). `PW_BASE_URL` / `PW_API_URL` env-driven (defaults: bare-metal
  3001/8001).
- **Auth:** seeded password user + existing `/api/login/` session endpoint → `storageState`.
  No OAuth in tests, no backend auth changes.
- **Seed data:** `manage.py seed_design_data` (dev-only) creates the `designbot` user, a
  provider/model, and one request of every inference type with real media (generated
  PNG/WAV, committed tiny MP4/GLB fixtures), plus **worst-case variants**: 300-char unbroken
  token, long URL, max-length model name. The worst cases ARE the regression suite for
  overflow.
- **Route inventory** in one file (`e2e/routes.ts`): every page × auth requirement; new pages
  must be added there (overflow + screenshot coverage comes free).

### Phase 1 — Overflow guardrails (kill side-scroll permanently)
- `overflow.spec.ts`: for every route × viewport, hard-assert
  `document.scrollWidth <= viewport width`; on failure, walk the DOM and **name the offending
  elements** (selector + width) so the fix is mechanical.
- Fix everything it finds. Canonical fixes: `min-w-0` on flex children, `break-words` on
  prose, `break-all` on mono/URLs, `truncate` + `title` on badges, `overflow-x-auto` on
  tables/code, `max-w-full` on media.

### Phase 2 — `/design` component gallery
- Dev/staff-gated route group rendering each component family in **all states** with mock
  fixtures: `InferenceRequestCard` × 7 types × (owner/public/worst-case), badges, players,
  pagination, empty/error/loading states, `ui/` primitives.
- Lives in the real app: real Tailwind config, dark/light, i18n. Playwright screenshots the
  gallery pages too — component-level before/after on every change.

### Phase 3 — Design-system tightening
- Audit + codify: type scale (kill ad-hoc sizes), spacing rhythm, radii, icon sizes, color
  token usage in both themes. Small PR series, each verified by gallery screenshots.

### Phase 4 — Page-by-page refresh (the visible redesign)
Order: request cards & list pages → playgrounds → profile/share (public faces) → dashboard
home → settings/admin. Per page: before screenshots → redesign → after screenshots → overflow
suite green. Information density via progressive disclosure (stat chips, tooltips, expandable
detail rows) — not more simultaneous text.

### Phase 5 — Surface more information
- Inventory API fields the UI drops (usage breakdowns, provider/node details, generation
  params, queue/latency split, visibility/star context); add compact disclosure patterns.
  Backend serializer additions where the data exists but isn't exposed.

### Later / explicitly out of scope now
- CI job for overflow guard (promote when stable), pixel baselines in CI, Storybook,
  rebranding, new marketing pages.

## Artifacts
- `frontend/e2e/screenshots/{desktop,mobile}/<route>.png` — full-page captures, gitignored,
  regenerated on demand (`npm run shots`).
- `frontend/e2e/__screenshots__/` — committed curated baselines (`toHaveScreenshot`, masked
  dynamic regions).
- `npm run test:design` — overflow + baselines. `npm run shots` — capture-only sweep.

## Risks
- Pixel-baseline flake → curated set only, mask timestamps/animations, generous
  `maxDiffPixelRatio`, local-first.
- Seeded media realism (GLB/MP4 fixtures are tiny) → fine for layout; revisit if 3D/video
  design work needs richer content.
- Gallery drift from real usage → gallery fixtures typed as `InferenceRequest`, so type
  changes force fixture updates.
