import { test as setup, expect, request } from '@playwright/test'

// Session login for the seeded design user — pure API, no OAuth, no UI.
// Mirrors the app's own flow: GET /api/login-set-cookie/ for the csrftoken,
// POST /api/login/ for the sessionid. Cookies land on `localhost` (no port),
// so the browser at :3001 sends them to the API at :8001 exactly like the
// real app's credentialed fetches.
//
// Prereq: `cd backend && poetry run python manage.py seed_design_data`

const API = process.env.PW_API_URL || 'http://localhost:8001'
export const DESIGN_USER = {
  email: 'designbot@inference.club',
  password: 'designbot-pass-1',
}

setup('authenticate as designbot', async () => {
  const ctx = await request.newContext({ baseURL: API })
  const csrfRes = await ctx.get('/api/login-set-cookie/')
  expect(csrfRes.ok(), 'backend reachable at PW_API_URL').toBeTruthy()

  const csrf = (await ctx.storageState()).cookies.find((c) => c.name === 'csrftoken')?.value
  expect(csrf, 'csrftoken cookie from /api/login-set-cookie/').toBeTruthy()

  const res = await ctx.post('/api/login/', {
    data: DESIGN_USER,
    headers: { 'X-CSRFToken': csrf!, Referer: `${API}/` },
  })
  expect(
    res.ok(),
    'login as designbot — did you run `manage.py seed_design_data`?',
  ).toBeTruthy()

  await ctx.storageState({ path: 'e2e/.auth/designbot.json' })
  await ctx.dispose()
})
