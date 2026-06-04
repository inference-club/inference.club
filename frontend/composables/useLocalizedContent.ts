import type { Collections } from '@nuxt/content'

// Locale-aware querying for the per-locale Nuxt Content collections
// (blog_en, blog_fr, docs_en, …). Centralizes two things every blog/docs page
// needs:
//   1. Stripping the locale prefix that `prefix_except_default` adds to
//      non-default routes (/fr/blog/x → /blog/x) so we can match stored paths,
//      which are locale-free.
//   2. Falling back to English when the active locale has no translation, with
//      a `fellBack` flag so the page can show a notice banner.
export function useLocalizedContent() {
  const { locale, defaultLocale } = useI18n()

  type Base = 'blog' | 'docs'
  const collectionName = (base: Base, code?: string) =>
    `${base}_${code ?? locale.value}` as keyof Collections

  // Remove the leading /<locale> segment for non-default locales.
  function toContentPath(routePath: string): string {
    if (locale.value === defaultLocale) return routePath
    const prefix = `/${locale.value}`
    if (routePath === prefix) return '/'
    return routePath.startsWith(`${prefix}/`) ? routePath.slice(prefix.length) : routePath
  }

  // Fetch one page by route path, falling back to English.
  async function findByPath(base: Base, routePath: string) {
    const path = toContentPath(routePath)
    let doc = await queryCollection(collectionName(base)).path(path).first()
    let fellBack = false
    if (!doc && locale.value !== defaultLocale) {
      doc = await queryCollection(collectionName(base, defaultLocale)).path(path).first()
      fellBack = !!doc
    }
    return { doc, fellBack }
  }

  // List pages for the active locale, merged with English entries that have no
  // translation yet (each English entry flagged `isFallback` so listings can
  // show an "EN" badge). Keeps a sparse locale's index full and useful.
  async function listMerged<T extends { path: string }>(
    base: Base,
    apply: (q: ReturnType<typeof queryCollection>) => ReturnType<typeof queryCollection>,
  ): Promise<Array<T & { isFallback: boolean }>> {
    const localized = (await apply(queryCollection(collectionName(base))).all()) as T[]
    if (locale.value === defaultLocale) {
      return localized.map(d => ({ ...d, isFallback: false }))
    }
    const english = (await apply(queryCollection(collectionName(base, defaultLocale))).all()) as T[]
    const have = new Set(localized.map(d => d.path))
    const merged = [
      ...localized.map(d => ({ ...d, isFallback: false })),
      ...english.filter(d => !have.has(d.path)).map(d => ({ ...d, isFallback: true })),
    ]
    return merged
  }

  return { collectionName, toContentPath, findByPath, listMerged, locale, defaultLocale }
}
