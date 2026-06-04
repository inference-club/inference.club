# PRD 02 — Internationalization (i18n) of the frontend

> **Status:** Draft for review. Not yet implemented.
>
> **Author:** Brian (spec) · drafted with Claude Code.
>
> **Scope:** Make the entire Nuxt frontend multilingual — public
> marketing site, blog, docs, legal pages, login, **and** the full
> authenticated dashboard — across 7 launch languages, with a polished
> language picker sitting next to the existing theme toggle. Built so
> that adding an 8th+ language later is a small, mechanical change.
> **Explicitly out of scope (this PRD):** localizing the Django backend /
> API responses, currency/payment localization, and right-to-left (RTL)
> layout work (none of the launch languages are RTL).

---

## 1. Summary

Today the frontend (`/frontend`, Nuxt 3.17.1) is English-only. All
user-facing copy is hardcoded in `.vue` files (~6,000 lines across 31
routes) and in `@nuxt/content` markdown (blog + docs). There is no
locale routing, no language state, and no translation tooling.

This PRD introduces a complete i18n layer:

1. **`@nuxtjs/i18n` module** for UI-string translation, locale routing,
   browser detection, persistence, and SEO (`hreflang`, localized
   `og:locale`, per-locale sitemap).
2. **Per-locale URL routing** — English stays at clean paths (`/blog`,
   `/docs`); other languages are prefixed (`/fr/blog`, `/ja/docs`).
3. **Per-locale Nuxt Content collections** so blog posts and docs can
   exist in any language, **falling back to English** (with a banner)
   when a translation is missing.
4. **A language picker** in the `TopBar`, immediately left of the
   theme toggle, mirroring its look and behavior.
5. **AI-seeded, human-reviewable translations** for all 7 languages,
   committed as editable JSON locale files + translated markdown, so
   native speakers can correct them over time.

---

## 2. Launch languages

| Code | Language   | Native name | `og:locale` |
|------|------------|-------------|-------------|
| `en` | English    | English     | `en_US`     |
| `zh` | Chinese    | 中文 (简体)  | `zh_CN`     |
| `ja` | Japanese   | 日本語       | `ja_JP`     |
| `ru` | Russian    | Русский     | `ru_RU`     |
| `fr` | French     | Français    | `fr_FR`     |
| `ko` | Korean     | 한국어       | `ko_KR`     |
| `es` | Spanish    | Español     | `es_ES`     |

`en` is the **default locale** and the **fallback** for every missing
string and every untranslated content page. All launch languages are
left-to-right; RTL is deliberately deferred.

> **Adding a language later** = (a) add one entry to the `locales`
> array in `nuxt.config`, (b) add `i18n/locales/<code>.json`, (c) add a
> `content_<code>` collection + `content/<code>/` folder. No code
> changes. This 3-step recipe is a hard design constraint.

---

## 3. Decisions (resolved with stakeholder)

These four were confirmed before drafting and drive the rest of the doc:

1. **URL strategy → "prefix except default."** English keeps its
   current clean URLs (no redirects, no broken links, no SEO regression);
   every other locale is path-prefixed. Strategy:
   `prefix_except_default`.
2. **Scope → everything at once.** Public site *and* the full
   authenticated dashboard (playground, settings, providers, inference —
   30+ routes) are translated in the first implementation. (Still
   delivered in phases internally — see §11 — but all of it is in scope.)
3. **Content fallback → fall back to English.** A blog/docs page with no
   translation in the active locale renders the English version with a
   subtle "not yet available in <language> — showing English" banner.
   Nothing 404s; content can be translated gradually.
4. **Translation source → AI-seeded, human-reviewable.** I generate
   machine translations for all 6 non-English locales as a starting
   point, committed as editable JSON / markdown. Native speakers refine
   them later; the structure is built for that.

---

## 4. Package selection

### 4.1 UI strings — `@nuxtjs/i18n`

**Chosen:** [`@nuxtjs/i18n`](https://i18n.nuxtjs.org) (v9+, the
Nuxt 3 / Vite-native line built on `vue-i18n@10`).

Why this and not raw `vue-i18n` or a hand-rolled composable (like the
current `useTheme`):

- It's the de-facto standard for Nuxt and the only option that gives us,
  out of the box: locale-prefixed routing, `<NuxtLinkLocale>` /
  `useLocalePath()` (so links stay in-locale automatically), lazy-loaded
  message bundles, `detectBrowserLanguage` with cookie persistence, and
  **SEO helpers** (`useLocaleHead()` emits `hreflang` + canonical tags).
- A hand-rolled solution would re-implement all of the above (routing
  and SEO especially are non-trivial) — not worth it.

> **Version note / risk:** some `@nuxtjs/i18n` v10.x releases have a
> reported production-SSR bug loading `/_i18n/.../messages.json`
> (nuxt-modules/i18n#3940). We will **pin a known-good version**, prefer
> `bundle.optimizeTranslationDirective` defaults, and smoke-test SSR in
> staging before shipping. If v10 is unstable at implementation time,
> fall back to the latest stable v9. Decide the exact pin during Phase 0.

### 4.2 Content — native `@nuxt/content` v3 per-locale collections

Nuxt Content **v3 has no built-in i18n** (unlike v2's `locales` option).
The official, documented approach is **one collection per locale** that
sources a language subfolder. We adopt it exactly (see §7).

### 4.3 Supporting packages

- **`@nuxtjs/sitemap`** (or Nuxt's built-in sitemap via `@nuxt/content`
  integration) — to emit per-locale URLs with `hreflang` alternates.
- No separate date/number lib needed — `vue-i18n` provides
  `$d()` / `$n()` (Intl-backed) for any future date/number formatting.

---

## 5. Architecture overview

Three independent layers, each with its own translation source:

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1 — UI strings (buttons, labels, nav, dashboard copy)  │
│   source: i18n/locales/{en,zh,ja,ru,fr,ko,es}.json           │
│   engine: @nuxtjs/i18n / vue-i18n  → t('key')                │
├─────────────────────────────────────────────────────────────┤
│ Layer 2 — Routing & locale state                             │
│   strategy: prefix_except_default                            │
│   detection: browser → cookie → default(en)                  │
│   helpers: useLocalePath(), <NuxtLinkLocale>, switchLocale   │
├─────────────────────────────────────────────────────────────┤
│ Layer 3 — Long-form content (blog + docs markdown)           │
│   source: content/{en,zh,ja,...}/**                          │
│   engine: @nuxt/content per-locale collections + EN fallback │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. UI-string i18n (Layer 1)

### 6.1 `nuxt.config.ts` additions

```ts
modules: [
  // ...existing...
  '@nuxtjs/i18n',
],
i18n: {
  langDir: 'locales',
  defaultLocale: 'en',
  strategy: 'prefix_except_default',
  lazy: true,                       // load only the active locale bundle
  locales: [
    { code: 'en', language: 'en-US', name: 'English',  file: 'en.json' },
    { code: 'zh', language: 'zh-CN', name: '中文',      file: 'zh.json' },
    { code: 'ja', language: 'ja-JP', name: '日本語',    file: 'ja.json' },
    { code: 'ru', language: 'ru-RU', name: 'Русский',   file: 'ru.json' },
    { code: 'fr', language: 'fr-FR', name: 'Français',  file: 'fr.json' },
    { code: 'ko', language: 'ko-KR', name: '한국어',    file: 'ko.json' },
    { code: 'es', language: 'es-ES', name: 'Español',   file: 'es.json' },
  ],
  detectBrowserLanguage: {
    useCookie: true,
    cookieKey: 'i18n_locale',
    redirectOn: 'root',             // detect on first visit, don't fight deep links
    alwaysRedirect: false,
  },
  bundle: { optimizeTranslationDirective: false }, // avoid known v10 directive edge-cases
},
```

### 6.2 Locale file structure

Namespaced JSON, one file per locale, keys grouped by surface so the
file maps onto the app and stays reviewable:

```jsonc
// i18n/locales/en.json
{
  "nav":       { "dashboard": "Dashboard", "network": "Network",
                 "docs": "Docs", "blog": "Blog", "login": "Login" },
  "home":      { "heroTitle": "A distributed inference network…", "…": "…" },
  "footer":    { "copyright": "© {year} inference.club", "…": "…" },
  "auth":      { "…": "…" },
  "dashboard": { "settings": { "…": "…" }, "playground": { "…": "…" } },
  "common":    { "save": "Save", "cancel": "Cancel", "loading": "Loading…" }
}
```

Every non-English file mirrors this exact key tree. A small CI check
(§12) fails the build if any locale is missing a key that `en.json` has.

### 6.3 String extraction

The work is mechanical but large: replace hardcoded strings with
`{{ $t('namespace.key') }}` (template) / `t('namespace.key')` (script,
via `const { t } = useI18n()`). Approach:

- Go surface-by-surface (homepage → nav/footer → legal → blog/docs
  chrome → login → dashboard sections), not file-by-file randomly, so
  each PR is reviewable and ships a fully-translated screen.
- Pluralization (`t('x.items', n)`) and interpolation (`t('footer.copyright', { year })`)
  use vue-i18n syntax. Audit for English-only assumptions (e.g.
  concatenated sentence fragments) and convert to single keys with
  placeholders.

---

## 7. Content i18n — blog & docs (Layer 3)

### 7.1 Directory restructure

Today: `content/blog/*.md`, `content/docs/**/*.md`.
New: language subfolders mirroring the same structure.

```
content/
  en/
    blog/{getting-started,…}.md
    docs/**/*.md
  zh/ blog/… docs/…
  ja/ blog/… docs/…
  …                       # ru, fr, ko, es
```

English content moves into `content/en/` (a one-time `git mv`). Other
languages start sparse and fill in over time.

### 7.2 `content.config.ts` — per-locale collections

Keep the existing `blog` / `docs` schemas, but generate one collection
per locale. To honor the "adding a language = 1 array entry" constraint,
build the collections from a list rather than copy-pasting:

```ts
import { defineContentConfig, defineCollection, z } from '@nuxt/content'

const LOCALES = ['en', 'zh', 'ja', 'ru', 'fr', 'ko', 'es'] as const

const blogSchema = z.object({
  publishedAt: z.string(),
  author: z.string().optional(),
  tags: z.array(z.string()).optional(),
  image: z.string().optional(),
  image_prompt: z.string().optional(),
  featured: z.boolean().optional(),
})
const docsSchema = z.object({
  order: z.number().optional(),
  category: z.string().optional(),
})

const collections = {}
for (const code of LOCALES) {
  collections[`blog_${code}`] = defineCollection({
    type: 'page',
    source: { include: `${code}/blog/**/*.md`, prefix: '' },
    schema: blogSchema,
  })
  collections[`docs_${code}`] = defineCollection({
    type: 'page',
    source: { include: `${code}/docs/**/*.md`, prefix: '' },
    schema: docsSchema,
  })
}

export default defineContentConfig({ collections })
```

### 7.3 Querying with English fallback

A tiny composable centralizes locale-aware queries so every blog/docs
page uses the same fallback logic:

```ts
// composables/useLocalizedContent.ts
export function useLocalizedCollection(base: 'blog' | 'docs') {
  const { locale, defaultLocale } = useI18n()
  const collection = (suffix: string) =>
    `${base}_${suffix}` as keyof Collections

  async function findByPath(path: string) {
    let doc = await queryCollection(collection(locale.value)).path(path).first()
    let fellBack = false
    if (!doc && locale.value !== defaultLocale) {
      doc = await queryCollection(collection(defaultLocale)).path(path).first()
      fellBack = !!doc
    }
    return { doc, fellBack }   // page shows a banner when fellBack === true
  }
  // …list() variant for index pages, sorted by publishedAt/order…
  return { findByPath, /* list */ }
}
```

- **Detail page** (`blog/[...slug].vue`, `docs/[...slug].vue`): query
  active locale → fall back to `en` → render the
  **`<ContentFallbackBanner>`** when `fellBack` is true.
- **Listing pages** (`blog/index.vue`, docs sidebar nav): show the union
  — translated items where available, English where not — each English
  item flagged with a small "EN" badge, so a sparse locale still has a
  full, useful index (this is the agreed "fall back to English"
  behavior, not "hide").
- **Slugs stay identical across locales** (e.g. `getting-started.md` in
  every language folder) so a post's path is stable and the language
  picker can swap locale in-place on the same article.

### 7.4 Authoring translated content

AI-seed the highest-value pages first (the 4 blog posts + top docs),
committed as real markdown in each `content/<code>/` folder with
frontmatter (`title`, `description`) translated too. Everything else
falls back to English until translated — no blocker to shipping.

---

## 8. The language picker (emphasis)

Goal: a picker that feels native next to the theme toggle — same ghost
button styling, same height, same spacing — not a bolted-on `<select>`.

### 8.1 Placement

In `components/TopBar.vue`, inside the right-side action cluster
(`<div class="flex flex-1 items-center justify-end space-x-2">`),
positioned **immediately before** the theme toggle button:

```
[ 🌐 EN ▾ ]  [ ☀️/🌙 ]  [ Login / 👤 ]
   picker      theme       auth
```

It will also be added to the dashboard chrome (the `app.vue` layout
top bar) so the dashboard is switchable too.

### 8.2 Component design — `components/LanguagePicker.vue`

Built from the existing **shadcn/reka-ui `Popover`** (same primitive the
auth menu already uses) — guarantees visual + a11y consistency:

- **Trigger:** ghost `Button size="sm"`, a `Languages`/`Globe` icon
  (`lucide-vue-next`) + the current locale's short code (`EN`, `日本語`),
  with a `ChevronDown`. Matches the theme button's footprint.
- **Content:** `PopoverContent align="end"`, a vertical list of all
  locales. Each row shows the **native name** (中文, 日本語, Русский…) —
  never the English exonym — with a `Check` on the active one. Keyboard
  navigable, `aria-label`, `sr-only` "Select language", focus-visible
  rings (free from reka-ui).
- For 7 languages a flat list is ideal; if the list grows past ~12
  later, add an inline filter input. (No flags — flags ≠ languages and
  are an accessibility/locale-politics footgun.)

### 8.3 Switch behavior

Use the module's locale-preserving navigation so the user **stays on the
same page** in the new language:

```ts
const { locale, locales, setLocale } = useI18n()
const switchLocalePath = useSwitchLocalePath()
function choose(code) {
  // navigate to the same route in the target locale; cookie is updated
  navigateTo(switchLocalePath(code))
}
```

This rewrites `/docs/getting-started` ↔ `/ja/docs/getting-started`,
persists the choice to the `i18n_locale` cookie, and — because slugs are
shared (§7.3) — keeps the reader on the same article.

### 8.4 No-flash on first paint

Locale is resolved server-side by `@nuxtjs/i18n` (unlike the current
client-only `useTheme`, which can flash). So the correct language is in
the SSR HTML; no hydration flash. (Optional follow-up: move theme
detection server-side too for parity — noted, not required here.)

---

## 9. SEO & metadata

- **`useLocaleHead()`** in the default + docs + app layouts to emit
  `<html lang>`, canonical, and `hreflang` alternate links for every
  locale automatically.
- **`og:locale`** + `og:locale:alternate` per §2 table on shareable
  pages (home, blog posts, docs).
- **Sitemap:** per-locale URLs with `xhtml:link` hreflang alternates via
  `@nuxtjs/sitemap` (integrates with both i18n and content).
- **`x-default`** hreflang → English.
- Translate `<title>` / meta description per page via i18n keys and per
  content-page frontmatter.

---

## 10. Locale detection & persistence

1. **First visit:** `detectBrowserLanguage` reads `Accept-Language`,
   matches to a supported locale (else `en`), redirects on root only.
2. **Explicit choice:** picker writes the `i18n_locale` cookie;
   thereafter the cookie wins over the browser header.
3. **Deep links:** a `/fr/...` URL always renders French regardless of
   cookie (URL is the source of truth for prefixed locales).
4. **Logged-in users (future):** optionally persist `preferred_locale`
   on the user record so the choice follows them across devices —
   noted as a backend follow-up, **not in this PRD** (would need a
   Django migration + settings UI; the cookie covers the common case).

---

## 11. Implementation phases

All phases are in scope; phasing is for reviewable, shippable PRs.

- **Phase 0 — Plumbing & version pin.** Install `@nuxtjs/i18n` (pin a
  smoke-tested version), configure `nuxt.config`, create empty
  `en.json` + stubs, verify SSR + routing on a throwaway string. Add the
  missing-key CI check. *No visible change yet.*
- **Phase 1 — Language picker + nav/footer.** Build
  `LanguagePicker.vue`, wire into `TopBar` and `app.vue` layout,
  translate nav + footer + `common`. First user-visible multilingual
  surface. (English + AI-seeded 6.)
- **Phase 2 — Public marketing pages.** Homepage (the big one), legal
  pages, login. Extract → key → translate.
- **Phase 3 — Content i18n.** `git mv` content into `content/en/`,
  per-locale collections, `useLocalizedContent` composable,
  `ContentFallbackBanner`, EN-badge on listings; AI-seed translations of
  the 4 blog posts + top docs.
- **Phase 4 — Dashboard.** Settings, playground, providers, inference,
  leaderboard, manifest — section by section (each its own PR).
- **Phase 5 — SEO polish.** `useLocaleHead`, sitemap hreflang,
  `og:locale`, per-page titles; staging SSR audit across all 7 locales.

---

## 12. Quality, testing & tooling

- **Missing-key CI check:** script diffs every locale file's key set
  against `en.json`; build fails on missing keys (prevents silent
  English leakage). Extra keys → warning.
- **No-hardcoded-string lint (best-effort):** an ESLint rule / grep in
  CI flagging literal non-whitespace text in `<template>` outside
  `$t(...)`, to catch regressions as new features land.
- **Visual smoke per locale:** render home + one blog post + one
  dashboard page in each locale in staging; check layout doesn't break
  with longer strings (German-style overflow risk — Russian/French run
  long; CJK runs short but needs correct fonts via `@nuxt/fonts`).
- **Fallback test:** request a `ja` blog post with no JA file → asserts
  English renders + banner shows.
- **Font coverage:** confirm `@nuxt/fonts` serves glyphs for CJK +
  Cyrillic (may need an additional subset/font for zh/ja/ko/ru).

---

## 13. Risks & open questions

- **`@nuxtjs/i18n` v10 SSR bug** (§4.1) — mitigated by version pinning +
  staging smoke test; v9 fallback ready.
- **Translation quality** — AI seed will have errors, especially product
  terms ("inference", "node", "GPU", "Tailscale"). Maintain a small
  **glossary** of do-not-translate / preferred terms to feed the AI pass
  and guide reviewers.
- **Dashboard scope is large** — 30+ routes, many strings. Phase 4 is
  the bulk of the effort; budget accordingly. Per-section PRs keep it
  moving.
- **Content maintenance burden** — every new blog post is now 7 files
  (1 real + 6 fallbacks-or-translations). Fallback design means only the
  English file is *required*; that keeps publishing friction at ~zero.
- **CJK/Cyrillic fonts** — verify before launch (see §12).

---

## 14. Out of scope (this PRD)

- Backend / API response localization.
- RTL languages (Arabic, Hebrew) and bidi layout.
- Currency / payment / number-format localization beyond what
  `vue-i18n` `$n`/`$d` give for free.
- Persisting locale to the user record (cookie-only for now).
- Localized email / notifications.

---

## 15. References

- [Nuxt Content v3 — i18n integration](https://content.nuxt.com/docs/integrations/i18n)
  (per-locale collections, the pattern in §7)
- [`@nuxtjs/i18n` docs](https://i18n.nuxtjs.org) ·
  [lazy-load translations](https://i18n.nuxtjs.org/docs/guide/lazy-load-translations) ·
  [options](https://i18n.nuxtjs.org/docs/api/options)
- [nuxt-modules/i18n#3940](https://github.com/nuxt-modules/i18n/issues/3940) — v10 SSR bug to test against
- Current code touchpoints: `frontend/nuxt.config.ts`,
  `frontend/components/TopBar.vue`, `frontend/composables/useTheme.ts`
  (picker pattern to mirror), `frontend/content.config.ts`,
  `frontend/content/{blog,docs}/`.
