// Docs navigation tree, shared by the docs layout (sidebar) and doc pages
// (prev/next links) so both follow the same reading order: `order` frontmatter
// ascending, then title. The useAsyncData key dedupes the fetch between the
// layout and the page within one request.

export interface DocsNavItem {
  title: string
  path: string
  order?: number
  children?: DocsNavItem[]
}

function sorted(items: DocsNavItem[] | undefined): DocsNavItem[] {
  if (!items) return []
  return [...items]
    .sort((a, b) => {
      const ao = a.order ?? Number.POSITIVE_INFINITY
      const bo = b.order ?? Number.POSITIVE_INFINITY
      if (ao !== bo) return ao - bo
      return a.title.localeCompare(b.title)
    })
    .map((item) => ({ ...item, children: sorted(item.children) }))
}

// Reading order = leaf pages in sidebar order. Parent nodes that are pure
// folders (no index.md, e.g. /docs/api) are skipped — linking prev/next to
// them would 404.
function flatten(items: DocsNavItem[], out: DocsNavItem[] = []): DocsNavItem[] {
  for (const item of items) {
    if (item.children?.length) flatten(item.children, out)
    else out.push(item)
  }
  return out
}

// The single fetch — called by the docs LAYOUT only. Pages read the same
// data through useDocsReadingOrder below; registering a second useAsyncData
// under the same key would warn about mismatched handlers.
export async function useDocsNav() {
  const { collectionName, locale } = useLocalizedContent()

  // Sidebar reflects the active locale's docs; falls back to English nav when
  // the locale has no docs translated yet so the tree is never empty.
  const { data: nav } = await useAsyncData(
    'docs-nav',
    async () => {
      // `order` must be requested explicitly — navigation items only carry
      // title/path by default, which would silently fall back to title sort.
      const localized = await queryCollectionNavigation(collectionName('docs'), ['order'])
      if (localized?.length) return localized
      return await queryCollectionNavigation(collectionName('docs', 'en'), ['order'])
    },
    { watch: [locale] },
  )

  const tree = computed<DocsNavItem[]>(() => sorted(nav.value as DocsNavItem[] | undefined))
  const flat = computed<DocsNavItem[]>(() => flatten(tree.value))
  return { tree, flat }
}

// Reading order for prev/next links, from the nav the layout already fetched.
// Safe because the docs layout's setup (and its await) completes before the
// page inside it is rendered.
export function useDocsReadingOrder() {
  const { data: nav } = useNuxtData('docs-nav')
  return computed<DocsNavItem[]>(() =>
    flatten(sorted(nav.value as DocsNavItem[] | undefined)),
  )
}
