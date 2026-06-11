import { defineConfig, devices } from '@playwright/test'

// Design-quality suite (docs/prd/05-design-quality-and-visual-testing.md).
// Runs against a locally running stack: backend on PW_API_URL (default
// bare-metal :8001, seeded via `manage.py seed_design_data`) and frontend on
// PW_BASE_URL (default bare-metal :3001).
//
//   npm run test:design   - overflow guards + curated pixel baselines
//   npm run shots         - full-page screenshot sweep of every route
//
// Both viewports are Chromium so a single browser install covers the suite;
// the mobile project uses a Pixel 7 profile (412px, touch, mobile UA) since
// viewport width — not engine — is what layout bugs key on.
export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/test-results',
  fullyParallel: true,
  // Generous timeout + capped workers: the Nuxt DEV server compiles routes
  // on first hit, and a full-parallel stampede over 43 cold routes blows
  // 45s budgets with false "failures".
  timeout: 90_000,
  workers: 4,
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: './e2e/report', open: 'never' }]],
  expect: {
    toHaveScreenshot: { maxDiffPixelRatio: 0.02, animations: 'disabled' },
  },
  snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{arg}{ext}',
  use: {
    baseURL: process.env.PW_BASE_URL || 'http://localhost:3001',
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
        storageState: 'e2e/.auth/designbot.json',
      },
      dependencies: ['setup'],
    },
  ],
})
