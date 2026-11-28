import type { APIRequestContext, Page } from '@playwright/test'
import { ROUTES, type RouteSpec } from './routes'

// Default = the docker compose dev stack (backend :8101). Bare-metal: PW_API_URL=http://localhost:8001
const API = process.env.PW_API_URL || 'http://localhost:8101'

/** Navigate and let the page settle: network quiet + animations disabled. */
export async function gotoSettled(page: Page, path: string) {
  await page.goto(path, { waitUntil: 'domcontentloaded' })
  // Capped: pages with a live poll, an SSE stream or a WebGL scene never go
  // network-idle, and an uncapped wait burned the whole test timeout.
  await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => {})
  // Loading skeletons mean the page is still waiting on auth or data. Under a
  // loaded machine the network-idle cap above can pass first, and the sweep
  // then shoots a signed-out skeleton instead of the page.
  await page
    .waitForFunction(() => !document.querySelector('.animate-pulse'), null, { timeout: 20_000 })
    .catch(() => {})
  await page.addStyleTag({
    content:
      '*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }',
  })
  // One settle frame for client-only mounts (charts, viewers).
  await page.waitForTimeout(250)
}

/**
 * Resolve `:id`/`:slug` placeholders from seeded data via the API (using the
 * designbot session from storageState). Routes that can't resolve are
 * returned with `path: null` so specs can skip them with a clear reason
 * instead of shooting a 404.
 */
export async function resolveRoutes(
  api: APIRequestContext,
): Promise<Array<RouteSpec & { resolved: string | null }>> {
  let requestId: string | null = null
  let videoRequestId: string | null = null
  let collectionSlug: string | null = null

  try {
    const res = await api.get(`${API}/api/inference/requests/?page=1`)
    if (res.ok()) {
      const body = await res.json()
      requestId = body?.results?.[0]?.id != null ? String(body.results[0].id) : null
    }
  } catch {
    /* leave null */
  }
  try {
    const res = await api.get(`${API}/api/inference/requests/?page=1&type=VIDEO`)
    if (res.ok()) {
      const body = await res.json()
      videoRequestId =
        body?.results?.[0]?.id != null ? String(body.results[0].id) : null
    }
  } catch {
    /* leave null */
  }
  try {
    const res = await api.get(`${API}/api/inference/collections/`)
    if (res.ok()) {
      const body = await res.json()
      const first = Array.isArray(body) ? body[0] : body?.results?.[0]
      collectionSlug = first?.slug ?? null
    }
  } catch {
    /* leave null */
  }

  // First id from a list endpoint, whatever its envelope (array, DRF
  // `results`, or OpenAI-style `data`). null when empty or unreachable.
  const firstId = async (url: string): Promise<string | null> => {
    try {
      const res = await api.get(`${API}${url}`)
      if (!res.ok()) return null
      const body = await res.json()
      const list = Array.isArray(body) ? body : body?.results ?? body?.data ?? []
      return list?.[0]?.id != null ? String(list[0].id) : null
    } catch {
      return null
    }
  }
  const extra: Record<string, string | null> = {
    ':threadId': await firstId('/api/inference/threads/'),
    ':workflowId': await firstId('/v1/workflows'),
    ':runId': await firstId('/v1/workflows/runs'),
    ':episodeId': await firstId('/v1/episodes'),
  }

  return ROUTES.map((r) => {
    if (!r.dynamic) return { ...r, resolved: r.path }
    let p: string | null = r.path
    for (const [token, value] of Object.entries(extra)) {
      if (p && p.includes(token)) p = value ? p.replace(token, value) : null
    }
    p = p && p.includes(':videoId') ? (videoRequestId ? p.replace(':videoId', videoRequestId) : null) : p
    p = p && p.includes(':id') ? (requestId ? p.replace(':id', requestId) : null) : p
    p = p && p.includes(':slug') ? (collectionSlug ? p.replace(':slug', collectionSlug) : null) : p
    return { ...r, resolved: p }
  })
}

export interface OverflowReport {
  scrollWidth: number
  clientWidth: number
  offenders: string[]
}

/**
 * The core guard: returns null when the document doesn't scroll sideways,
 * otherwise a report naming the widest offending elements so the fix is
 * mechanical (find selector, add min-w-0 / break-words / truncate).
 */
export async function checkHorizontalOverflow(page: Page): Promise<OverflowReport | null> {
  return page.evaluate(() => {
    const doc = document.documentElement
    const vw = doc.clientWidth
    if (doc.scrollWidth <= vw + 1) return null

    const describe = (el: Element): string => {
      const tag = el.tagName.toLowerCase()
      const id = el.id ? `#${el.id}` : ''
      const cls = el.className && typeof el.className === 'string'
        ? '.' + el.className.trim().split(/\s+/).slice(0, 4).join('.')
        : ''
      const text = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40)
      return `${tag}${id}${cls}${text ? ` "${text}"` : ''}`
    }

    const offenders: Array<{ right: number; desc: string }> = []
    for (const el of Array.from(document.querySelectorAll('body *'))) {
      // Dev-mode overlays (Nuxt devtools / Vue tracer) mirror the document
      // width — noise, never the cause.
      if ((el as HTMLElement).id === 'vue-tracer-overlay' || el.closest('#vue-tracer-overlay')) continue
      const r = el.getBoundingClientRect()
      if (r.width === 0) continue
      if (r.right > vw + 1 || r.left < -1) {
        offenders.push({
          right: Math.round(r.right),
          desc: `${describe(el)} [left=${Math.round(r.left)} right=${Math.round(r.right)} vw=${vw}]`,
        })
      }
    }
    offenders.sort((a, b) => b.right - a.right)
    return {
      scrollWidth: doc.scrollWidth,
      clientWidth: vw,
      // Deepest/widest few are enough to locate the culprit.
      offenders: offenders.slice(0, 12).map((o) => o.desc),
    }
  })
}

/** Fails loudly when an auth page bounced to /login (broken session ≠ design pass). */
export function expectNotBouncedToLogin(page: Page, route: RouteSpec) {
  if (route.auth && new URL(page.url()).pathname.startsWith('/login')) {
    throw new Error(
      `${route.path} redirected to /login — storageState missing or expired. ` +
        'Re-run: seed_design_data, then the setup project.',
    )
  }
}
