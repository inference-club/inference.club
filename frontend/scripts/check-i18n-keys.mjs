#!/usr/bin/env node
// CI guard: every locale file under i18n/locales/ must define exactly the same
// key set as en.json (the source of truth). Missing keys would silently leak
// English (via vue-i18n fallback) — fine at runtime, but we want to *know*.
// Extra keys are reported as warnings (stale keys to prune). Also validates
// that interpolation placeholders ({like_this}) match the English string.
//
// Usage: node scripts/check-i18n-keys.mjs   (exit 1 on missing keys)
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const dir = join(dirname(fileURLToPath(import.meta.url)), '..', 'i18n', 'locales')
const BASE = 'en.json'

const flatten = (obj, prefix = '', out = {}) => {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) flatten(v, key, out)
    else out[key] = v
  }
  return out
}

const placeholders = (s) =>
  typeof s === 'string' ? [...s.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort() : []

const base = flatten(JSON.parse(readFileSync(join(dir, BASE), 'utf8')))
const baseKeys = Object.keys(base)
const locales = readdirSync(dir).filter(f => f.endsWith('.json') && f !== BASE)

let hadError = false
console.log(`Checking ${locales.length} locales against ${BASE} (${baseKeys.length} keys)\n`)

for (const file of locales) {
  const data = flatten(JSON.parse(readFileSync(join(dir, file), 'utf8')))
  const keys = new Set(Object.keys(data))
  const missing = baseKeys.filter(k => !keys.has(k))
  const extra = [...keys].filter(k => !base[k] && !(k in base))
  const badPlaceholders = baseKeys.filter(
    k => keys.has(k) && placeholders(base[k]).join() !== placeholders(data[k]).join(),
  )

  if (missing.length === 0 && extra.length === 0 && badPlaceholders.length === 0) {
    console.log(`✓ ${file}`)
    continue
  }
  if (missing.length) {
    hadError = true
    console.error(`✗ ${file} — missing ${missing.length} key(s): ${missing.join(', ')}`)
  }
  if (badPlaceholders.length) {
    hadError = true
    console.error(`✗ ${file} — placeholder mismatch: ${badPlaceholders.join(', ')}`)
  }
  if (extra.length) {
    console.warn(`⚠ ${file} — ${extra.length} extra key(s): ${extra.join(', ')}`)
  }
}

if (hadError) {
  console.error('\ni18n key check FAILED')
  process.exit(1)
}
console.log('\ni18n key check passed')
