import { test, expect } from '@playwright/test'
import { ROUTES } from './routes'
import {
  gotoSettled,
  resolveRoutes,
  checkHorizontalOverflow,
  expectNotBouncedToLogin,
} from './helpers'

// The side-scroll killer: every route, both viewports, the document must not
// scroll horizontally. Failures name the offending elements; fix those and
// re-run. Seeded worst-case requests (300-char unbroken tokens, long URLs)
// exercise the failure mode on list/detail/profile pages.

let resolved: Awaited<ReturnType<typeof resolveRoutes>> = []

test.beforeAll(async ({ playwright }) => {
  const api = await playwright.request.newContext({
    storageState: 'e2e/.auth/designbot.json',
  })
  resolved = await resolveRoutes(api)
  await api.dispose()
})

for (const route of ROUTES) {
  test(`no horizontal overflow: ${route.name}`, async ({ page }) => {
    const r = resolved.find((x) => x.name === route.name)
    const path = r?.resolved
    test.skip(!path, `could not resolve ${route.path} from seeded data`)

    await gotoSettled(page, path!)
    expectNotBouncedToLogin(page, route)

    const report = await checkHorizontalOverflow(page)
    expect(
      report,
      report
        ? `Page scrolls sideways (scrollWidth ${report.scrollWidth} > viewport ${report.clientWidth}). Offenders:\n  ${report.offenders.join('\n  ')}`
        : undefined,
    ).toBeNull()
  })
}
