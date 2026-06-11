import { test, expect } from '@playwright/test'
import { gotoSettled } from './helpers'

// Curated pixel baselines — the small set of pages stable enough to gate on.
// Committed under e2e/__screenshots__/. Regenerate intentionally with:
//   npx playwright test baselines --update-snapshots
//
// Gallery pages qualify because their fixtures are deterministic (relative
// timestamps are computed from fixed offsets, so "2h ago" stays "2h ago").
// Keep volatile pages (live request lists, status) out of this set — they
// belong to the capture-only sweep instead.

const BASELINE_PAGES: Array<{ name: string; path: string }> = [
  // Not the homepage: its animated WebGL network scene isn't pixel-stable.
  { name: 'login', path: '/login' },
  { name: 'terms', path: '/terms-of-service' },
  { name: 'design-cards', path: '/design/cards' },
  { name: 'design-primitives', path: '/design/primitives' },
]

for (const { name, path } of BASELINE_PAGES) {
  test(`baseline: ${name}`, async ({ page }) => {
    await gotoSettled(page, path)
    await expect(page).toHaveScreenshot(`${name}.png`, { fullPage: true })
  })
}
