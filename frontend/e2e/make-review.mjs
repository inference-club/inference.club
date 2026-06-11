#!/usr/bin/env node
// Builds e2e/review.html: before/after screenshots side by side, per route,
// desktop + mobile. "Before" = e2e/screenshots-before/ (copy the sweep there
// prior to a design pass: cp -r e2e/screenshots e2e/screenshots-before),
// "after" = e2e/screenshots/ (regenerate with `npm run shots`). Open the
// HTML straight from disk — images are relative paths.
import { readdirSync, existsSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const before = join(here, 'screenshots-before')
const after = join(here, 'screenshots')

const names = new Set()
for (const root of [before, after]) {
  for (const proj of ['desktop', 'mobile']) {
    const dir = join(root, proj)
    if (existsSync(dir)) for (const f of readdirSync(dir)) names.add(f)
  }
}

const img = (root, proj, f, label) =>
  existsSync(join(root, proj, f))
    ? `<figure><figcaption>${label}</figcaption><img loading="lazy" src="${root.endsWith('screenshots') ? 'screenshots' : 'screenshots-before'}/${proj}/${f}"></figure>`
    : `<figure><figcaption>${label}</figcaption><div class="missing">no shot</div></figure>`

let sections = ''
for (const f of [...names].sort()) {
  const name = f.replace(/\.png$/, '')
  sections += `<section id="${name}"><h2>${name}</h2>`
  for (const proj of ['desktop', 'mobile']) {
    sections += `<div class="pair ${proj}">${img(before, proj, f, `${proj} · before`)}${img(after, proj, f, `${proj} · after`)}</div>`
  }
  sections += `</section>`
}

const toc = [...names]
  .sort()
  .map((f) => `<a href="#${f.replace(/\.png$/, '')}">${f.replace(/\.png$/, '')}</a>`)
  .join(' · ')

writeFileSync(
  join(here, 'review.html'),
  `<!doctype html><meta charset="utf-8"><title>design review — before/after</title>
<style>
  body{font:14px/1.5 -apple-system,sans-serif;margin:0;background:#111;color:#ddd}
  nav{position:sticky;top:0;background:#111d;padding:10px 16px;border-bottom:1px solid #333;backdrop-filter:blur(6px);font-size:12px}
  nav a{color:#9cf;text-decoration:none}
  section{padding:24px 16px;border-bottom:1px solid #222}
  h2{margin:0 0 12px;font-size:16px;color:#fff}
  .pair{display:flex;gap:12px;margin-bottom:16px;align-items:flex-start}
  figure{margin:0;flex:1;min-width:0}
  figcaption{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#888;margin-bottom:4px}
  img{width:100%;border:1px solid #333;border-radius:6px;display:block}
  .mobile figure{max-width:340px}
  .missing{border:1px dashed #444;border-radius:6px;padding:40px;text-align:center;color:#666}
</style>
<nav>${toc}</nav>
${sections}`,
)
console.log(`review.html written (${names.size} routes)`)
