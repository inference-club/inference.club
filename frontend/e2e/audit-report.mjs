// Summarise e2e/audit/**.json (written by `yarn audit`) as a markdown table
// per finding class on stdout. `--json` prints the merged rows instead.
import { readdirSync, readFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), 'audit')
if (!existsSync(root)) {
  console.error('no e2e/audit directory — run `yarn audit` first')
  process.exit(1)
}
const rows = []
for (const project of readdirSync(root)) {
  for (const f of readdirSync(join(root, project)).filter((f) => f.endsWith('.json'))) {
    rows.push(JSON.parse(readFileSync(join(root, project, f), 'utf8')))
  }
}
if (process.argv.includes('--json')) {
  console.log(JSON.stringify(rows, null, 2))
  process.exit(0)
}
const by = (pred) => rows.filter(pred).sort((a, b) => a.name.localeCompare(b.name) || a.project.localeCompare(b.project))
const section = (title, list, fmt) => {
  console.log(`\n## ${title} (${list.length})\n`)
  for (const r of list) console.log(`- **${r.name}** [${r.project}] ${fmt(r)}`)
}
console.log(`# Design audit — ${rows.length} page×viewport runs`)
section('Skipped (no seeded data)', by((r) => r.skipped), (r) => r.path)
section('Bounced to login', by((r) => r.bouncedToLogin), (r) => r.path)
section('Horizontal overflow', by((r) => r.overflow), (r) =>
  `scrollWidth ${r.overflow.scrollWidth} > ${r.overflow.clientWidth}\n  - ${r.overflow.offenders.slice(0, 4).join('\n  - ')}`)
section('Uncaught page errors', by((r) => r.pageErrors?.length), (r) => `\n  - ${r.pageErrors.join('\n  - ')}`)
section('Console errors / Vue warnings', by((r) => r.consoleErrors?.length), (r) => `\n  - ${r.consoleErrors.slice(0, 5).join('\n  - ')}`)
section('Failed requests (>=400)', by((r) => r.failedRequests?.length), (r) => `\n  - ${r.failedRequests.slice(0, 6).join('\n  - ')}`)
section('Leaked i18n keys', by((r) => r.dom?.rawKeys?.length), (r) => r.dom.rawKeys.join(', '))
section('Clipped text without ellipsis', by((r) => r.dom?.clippedCount), (r) => `${r.dom.clippedCount}: ${r.dom.clipped.slice(0, 3).join(' | ')}`)
section('Small tap targets, mobile (<32px)', by((r) => r.project === 'mobile' && r.dom?.smallTargetCount > 0), (r) =>
  `${r.dom.smallTargetCount}: ${r.dom.smallTargets.slice(0, 4).join(' | ')}`)
section('Heading structure (not exactly one h1)', by((r) => r.project === 'desktop' && r.dom && r.dom.h1s !== 1), (r) => `${r.dom.h1s} h1`)
section('Unlabeled icon controls', by((r) => r.project === 'desktop' && r.dom?.unlabeledControls > 0), (r) => `${r.dom.unlabeledControls}`)
section('Slow first load (>5s, dev server)', by((r) => r.loadMs > 5000), (r) => `${r.loadMs}ms`)
