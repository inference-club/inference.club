import { mkdirSync, writeFileSync } from 'node:fs'
import { test } from '@playwright/test'
import { ROUTES } from './routes'
import { gotoSettled, resolveRoutes, checkHorizontalOverflow } from './helpers'

// The audit sweep. Unlike overflow.spec.ts this never fails: it visits every
// route on every viewport and writes what it found to
// e2e/audit/<project>/<route>.json (+ a full-page PNG), so one run gives the
// whole picture rather than stopping at the first broken page. Summarise with
// `yarn audit:report`. Findings become GitHub issues; once a class of finding
// is at zero it graduates into a failing guard like overflow.spec.ts.

let resolved: Awaited<ReturnType<typeof resolveRoutes>> = []

test.beforeAll(async ({ playwright }) => {
  const api = await playwright.request.newContext({
    storageState: 'e2e/.auth/designbot.json',
  })
  resolved = await resolveRoutes(api)
  await api.dispose()
})

for (const route of ROUTES) {
  test(`audit: ${route.name}`, async ({ page }) => {
    const project = test.info().project.name
    const dir = `e2e/audit/${project}`
    mkdirSync(dir, { recursive: true })
    const out: Record<string, unknown> = { name: route.name, path: route.path, project }

    const r = resolved.find((x) => x.name === route.name)
    if (!r?.resolved) {
      out.skipped = 'no seeded data to resolve the route'
      writeFileSync(`${dir}/${route.name}.json`, JSON.stringify(out, null, 2))
      return
    }
    out.resolved = r.resolved

    const consoleErrors: string[] = []
    const pageErrors: string[] = []
    const failedRequests: string[] = []
    page.on('console', (m) => {
      if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 300))
      // Vue warns (missing i18n keys, hydration mismatches) arrive as warnings.
      if (m.type() === 'warning' && /\[Vue warn\]|\[intlify\]|Hydration/.test(m.text()))
        consoleErrors.push('warn: ' + m.text().slice(0, 300))
    })
    page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 300)))
    page.on('response', (res) => {
      if (res.status() >= 400) failedRequests.push(`${res.status()} ${res.request().method()} ${res.url()}`)
    })

    const started = Date.now()
    await gotoSettled(page, r.resolved)
    out.loadMs = Date.now() - started
    out.finalUrl = new URL(page.url()).pathname
    out.bouncedToLogin = !!route.auth && String(out.finalUrl).startsWith('/login')

    out.overflow = await checkHorizontalOverflow(page)
    out.dom = await page.evaluate(() => {
      const vw = document.documentElement.clientWidth
      const describe = (el: Element): string => {
        const cls = typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.') : ''
        const text = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40)
        return `${el.tagName.toLowerCase()}${cls}${text ? ` "${text}"` : ''}`
      }
      const visible = (el: Element) => {
        const b = el.getBoundingClientRect()
        const cs = getComputedStyle(el)
        return b.width > 0 && b.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'
      }
      // Text cut off with no ellipsis: content wider than its box, overflow
      // hidden, and nothing telling the reader there is more.
      const clipped: string[] = []
      // Interactive targets under 32px in either axis (phones want 44).
      const smallTargets: string[] = []
      // i18n keys that leaked to the screen ("nav.dashboard.title").
      const rawKeys: string[] = []
      for (const el of Array.from(document.querySelectorAll('body *'))) {
        if (el.closest('#vue-tracer-overlay,[id^="nuxt-devtools"],svg,pre,code')) continue
        if (!visible(el)) continue
        const cs = getComputedStyle(el)
        const ownText = Array.from(el.childNodes).some((n) => n.nodeType === 3 && (n.textContent || '').trim().length > 1)
        if (ownText) {
          if (el.scrollWidth > el.clientWidth + 2 && cs.overflowX === 'hidden' && cs.textOverflow !== 'ellipsis' && cs.whiteSpace === 'nowrap')
            clipped.push(describe(el))
          const t = (el.textContent || '').trim()
          if (/^[a-z][a-zA-Z0-9]*(\.[a-zA-Z0-9_]+){1,5}$/.test(t) && !/\.(com|club|io|md|json|yaml|py|ts|vue|lan|wav|mp3|png)$/.test(t))
            rawKeys.push(t)
        }
        if (el.matches('a[href],button,[role="button"],input:not([type="hidden"]),select,textarea')) {
          const b = el.getBoundingClientRect()
          if (b.right > 0 && b.left < vw && (b.width < 32 || b.height < 32) && !el.closest('p,li,.prose'))
            smallTargets.push(`${describe(el)} [${Math.round(b.width)}x${Math.round(b.height)}]`)
        }
      }
      const h1s = Array.from(document.querySelectorAll('h1')).filter(visible).length
      const imgsNoAlt = Array.from(document.querySelectorAll('img')).filter((i) => visible(i) && !i.hasAttribute('alt')).length
      const unlabeled = Array.from(document.querySelectorAll('button,a[href]')).filter(
        (e) => visible(e) && !(e.textContent || '').trim() && !e.getAttribute('aria-label') && !e.getAttribute('title'),
      ).length
      return {
        title: document.title,
        h1s,
        imgsNoAlt,
        unlabeledControls: unlabeled,
        clipped: clipped.slice(0, 15),
        clippedCount: clipped.length,
        smallTargets: smallTargets.slice(0, 15),
        smallTargetCount: smallTargets.length,
        rawKeys: Array.from(new Set(rawKeys)).slice(0, 15),
        height: document.documentElement.scrollHeight,
      }
    })
    out.consoleErrors = Array.from(new Set(consoleErrors)).slice(0, 20)
    out.pageErrors = Array.from(new Set(pageErrors)).slice(0, 20)
    out.failedRequests = Array.from(new Set(failedRequests)).slice(0, 20)

    await page.addStyleTag({ content: '#nuxt-devtools-anchor,[id^="nuxt-devtools"]{display:none!important}' })
    await page
      .screenshot({ path: `${dir}/${route.name}.png`, fullPage: true, timeout: 20_000 })
      .catch(() => { out.screenshotFailed = true })
    writeFileSync(`${dir}/${route.name}.json`, JSON.stringify(out, null, 2))
  })
}
