import type { APIRequestContext, Page } from '@playwright/test'
import { ROUTES, type RouteSpec } from './routes'

const API = process.env.PW_API_URL || 'http://localhost:8001'

/** Navigate and let the page settle: network quiet + animations disabled. */
export async function gotoSettled(page: Page, path: string) {
  await page.goto(path, { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle').catch(() => {})
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
    const res = await api.get(`${API}/api/inference/collections/`)
    if (res.ok()) {
      const body = await res.json()
      const first = Array.isArray(body) ? body[0] : body?.results?.[0]
      collectionSlug = first?.slug ?? null
    }
  } catch {
    /* leave null */
  }

  return ROUTES.map((r) => {
    if (!r.dynamic) return { ...r, resolved: r.path }
    let p: string | null = r.path
    p = p.includes(':id') ? (requestId ? p.replace(':id', requestId) : null) : p
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
