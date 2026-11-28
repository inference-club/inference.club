import { defineConfig, devices } from '@playwright/test'

// Design-quality suite (docs/prd/05-design-quality-and-visual-testing.md).
// Runs against a locally running stack. Defaults are the docker compose dev
// stack: backend on :8101 (seeded via `docker compose exec backend python
// manage.py seed_design_data`), frontend on :3101. Bare-metal: set
// PW_API_URL=http://localhost:8001 PW_BASE_URL=http://localhost:3001.
//
//   yarn test:design   - overflow guards + curated pixel baselines
//   yarn shots         - full-page screenshot sweep of every route
//   yarn audit         - non-failing sweep: overflow, console errors, failed
//                        requests, clipped text, small tap targets, written
//                        to <repo>/.captures/audit/ and summarised by `yarn audit:report`
//
// All viewports are Chromium so a single browser install covers the suite;
// the mobile project uses a Pixel 7 profile (412px, touch, mobile UA) since
// viewport width — not engine — is what layout bugs key on.
export default defineConfig({
  testDir: './e2e',
  // Run output goes outside frontend/: the compose dev server bind-mounts and
  // watches this directory, and every file written under it during a run made
  // Nuxt regenerate its templates and stall the pages under test.
  outputDir: '../.captures/playwright/test-results',
  fullyParallel: true,
  // Generous timeout + capped workers: the Nuxt DEV server compiles routes
  // on first hit, and a full-parallel stampede over 43 cold routes blows
  // 45s budgets with false "failures".
  timeout: 90_000,
  workers: 4,
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: '../.captures/playwright/report', open: 'never' }]],
  expect: {
    toHaveScreenshot: { maxDiffPixelRatio: 0.02, animations: 'disabled' },
  },
  snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{arg}{ext}',
  use: {
    baseURL: process.env.PW_BASE_URL || 'http://localhost:3101',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'desktop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
        storageState: 'e2e/.auth/designbot.json',
      },
      dependencies: ['setup'],
    },
    {
      name: 'mobile',
      use: {
        ...devices['Pixel 7'],
        // Narrower than the Pixel 7 default (412): iPhones are 375-390pt and
        // 412 let real-device overflow through. 375 = the strictest common
        // width (iPhone SE/mini); pass here and every phone passes.
        viewport: { width: 375, height: 812 },
        storageState: 'e2e/.auth/designbot.json',
      },
      dependencies: ['setup'],
    },
    {
      // iPad portrait. The width where the sidebar, two-column playgrounds
      // and card grids change shape — neither phone nor desktop rules apply
      // cleanly, so it gets its own pass.
      name: 'tablet',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 768, height: 1024 },
        hasTouch: true,
        storageState: 'e2e/.auth/designbot.json',
      },
      dependencies: ['setup'],
    },
  ],
})
