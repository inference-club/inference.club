import { test } from '@playwright/test'
import { ROUTES } from './routes'
import { gotoSettled, resolveRoutes, expectNotBouncedToLogin } from './helpers'

// Capture-only sweep: full-page PNG of every route per viewport, written to
// e2e/screenshots/{desktop,mobile}/<name>.png (gitignored — regenerate any
// time with `npm run shots`). This is the eyeball-review artifact for the
// redesign: run before a change, run after, compare.

let resolved: Awaited<ReturnType<typeof resolveRoutes>> = []

test.beforeAll(async ({ playwright }) => {
  const api = await playwright.request.newContext({
    storageState: 'e2e/.auth/designbot.json',
  })
  resolved = await resolveRoutes(api)
  await api.dispose()
})

for (const route of ROUTES) {
  test(`screenshot: ${route.name}`, async ({ page }) => {
    const r = resolved.find((x) => x.name === route.name)
    const path = r?.resolved
    test.skip(!path, `could not resolve ${route.path} from seeded data`)

    await gotoSettled(page, path!)
    expectNotBouncedToLogin(page, route)
    await page.screenshot({
      path: `e2e/screenshots/${test.info().project.name}/${route.name}.png`,
      fullPage: true,
    })
  })
}
