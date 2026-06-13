// Screenshot harness for the Living Cluster scene workbench (/design/cluster).
// Shoots the #cluster-stage element against the compose dev stack (frontend
// :3100) using the designbot storageState. Not part of the Playwright suite —
// run directly while art-directing the scene:
//
//   node e2e/cluster-shots.mjs                # default light/dark × live/degraded
//   node e2e/cluster-shots.mjs dark-live      # subset by shot name
import { chromium } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs'

const here = path.dirname(fileURLToPath(import.meta.url))
const BASE = process.env.CLUSTER_SHOT_BASE ?? 'http://localhost:3100'
const OUT = path.join(here, 'screenshots', 'cluster')

const SHOTS = [
  { name: 'dark-live', query: 'theme=dark&scenario=live' },
  { name: 'light-live', query: 'theme=light&scenario=live' },
  { name: 'dark-degraded', query: 'theme=dark&scenario=degraded' },
  { name: 'light-degraded', query: 'theme=light&scenario=degraded' },
]

const wanted = process.argv.slice(2)
const shots = wanted.length ? SHOTS.filter(s => wanted.includes(s.name)) : SHOTS
if (!shots.length) {
  console.error(`no matching shots; available: ${SHOTS.map(s => s.name).join(', ')}`)
  process.exit(1)
}

fs.mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const context = await browser.newContext({
  storageState: path.join(here, '.auth', 'designbot.json'),
  viewport: { width: 1680, height: 1000 },
  deviceScaleFactor: 2,
})
const page = await context.newPage()

// Dev-server quirks: networkidle never settles (websockets retry forever),
// domcontentloaded can be interrupted by vite dep re-optimization or HMR
// reloads, and cold compiles of the three.js chunks take ~30s. So: commit,
// poll for the canvas, clip-screenshot (element screenshots wait for
// "stability" that an animating scene never reaches), and retry the whole
// attempt on any failure.
async function shootOnce(shot) {
  // SSR with the auth cookie can take ~20s on a cold dev server.
  await page.goto(`${BASE}/design/cluster?${shot.query}`, { waitUntil: 'commit', timeout: 120_000 })
  let seen = false
  for (let i = 0; i < 30 && !seen; i++) {
    await page.waitForTimeout(2000)
    seen = (await page.locator('#cluster-stage canvas').count()) > 0
  }
  if (!seen) throw new Error('canvas never appeared')
  // Let the camera damping settle, assets load, and a few pulses spawn —
  // then make sure a dev-server reload didn't land mid-settle (SSR takes
  // ~20s, so a reload here leaves a stage-less page for a while).
  await page.waitForTimeout(4500)
  if ((await page.locator('#cluster-stage canvas').count()) === 0) throw new Error('page reloaded mid-settle')
  // getBoundingClientRect, not locator.boundingBox: the latter's actionability
  // wait flakes on a perpetually-animating element.
  const box = await page.evaluate(() => {
    const r = document.querySelector('#cluster-stage')?.getBoundingClientRect()
    return r ? { x: r.x, y: r.y, width: r.width, height: r.height } : null
  })
  if (!box) throw new Error('stage has no bounding box')
  const file = path.join(OUT, `${shot.name}.png`)
  await page.screenshot({ path: file, clip: box })
  return file
}

for (const shot of shots) {
  let file = null
  for (let attempt = 1; attempt <= 3 && !file; attempt++) {
    file = await shootOnce(shot).catch((e) => {
      console.warn(`attempt ${attempt} failed for ${shot.name}: ${e.message.split('\n')[0]}`)
      return null
    })
  }
  if (!file) throw new Error(`all attempts failed for ${shot.name}`)
  console.log(`✓ ${file}`)
}

await browser.close()
