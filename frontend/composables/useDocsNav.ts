// Docs navigation, shared by the docs layout (grouped sidebar + mobile drawer)
// and doc pages (prev/next links). Pages are grouped into ordered SECTIONS by
// their `category` frontmatter — not by directory — so the sidebar reads as a
// curated table of contents. Within a section, items sort by `order` then
// title. The same ordering drives the flat reading order for prev/next.

export interface DocsNavItem {
  title: string
  path: string
  order?: number
}

export interface DocsNavSection {
  title: string
  items: DocsNavItem[]
}

// Section render order. Categories not listed here fall to the end (alpha).
const SECTION_ORDER = [
  'Getting started',
  'Playground',
  'Services',
  'Providers',
  'API reference',
  'Architecture',
  'Reference',
]

// The landing page (/docs) is reached from the brand link / breadcrumb, so it
// is kept out of the section list to avoid a redundant "Welcome" row.
const HIDDEN_PATHS = new Set(['/docs'])

interface RawPage { title?: string; path: string; category?: string; order?: number }

function byOrderThenTitle(a: DocsNavItem, b: DocsNavItem) {
  const ao = a.order ?? Number.POSITIVE_INFINITY
  const bo = b.order ?? Number.POSITIVE_INFINITY
  if (ao !== bo) return ao - bo
  return a.title.localeCompare(b.title)
}

function buildSections(pages: RawPage[]): DocsNavSection[] {
  const groups = new Map<string, DocsNavItem[]>()
  for (const p of pages) {
    if (!p?.path || HIDDEN_PATHS.has(p.path)) continue
    const cat = p.category || 'Reference'
    if (!groups.has(cat)) groups.set(cat, [])
    groups.get(cat)!.push({ title: p.title ?? p.path, path: p.path, order: p.order })
  }
  for (const items of groups.values()) items.sort(byOrderThenTitle)
  const sectionRank = (name: string) => {
    const i = SECTION_ORDER.indexOf(name)
    return i === -1 ? SECTION_ORDER.length : i
  }
  return [...groups.keys()]
    .sort((a, b) => sectionRank(a) - sectionRank(b) || a.localeCompare(b))
    .map((title) => ({ title, items: groups.get(title)! }))
}

function flatten(sections: DocsNavSection[]): DocsNavItem[] {
  return sections.flatMap((s) => s.items)
}

// The single fetch — called by the docs LAYOUT. Pages read the same data via
// useDocsReadingOrder below (same useAsyncData key, deduped within a request).
export async function useDocsNav() {
  const { collectionName, locale } = useLocalizedContent()

  const { data: pages } = await useAsyncData(
    'docs-nav',
    async () => {
      const fields = ['title', 'path', 'category', 'order'] as const
      // Active locale, falling back wholesale to English when untranslated so
      // the tree is never empty (matches the page-level fallback).
      let rows = (await queryCollection(collectionName('docs'))
        .select(...fields)
        .all()) as RawPage[]
      if (!rows?.length) {
        rows = (await queryCollection(collectionName('docs', 'en'))
          .select(...fields)
          .all()) as RawPage[]
      }
      return rows
    },
    { watch: [locale] },
  )

  const sections = computed<DocsNavSection[]>(() => buildSections((pages.value as RawPage[]) ?? []))
  const flat = computed<DocsNavItem[]>(() => flatten(sections.value))
  return { sections, flat }
}

// Reading order for prev/next links, from the data the layout already fetched.
export function useDocsReadingOrder() {
  const { data: pages } = useNuxtData('docs-nav')
  return computed<DocsNavItem[]>(() => flatten(buildSections((pages.value as RawPage[]) ?? [])))
}
