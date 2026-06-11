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

export async function useDocsNav() {
  const { collectionName, locale } = useLocalizedContent()

  // Sidebar reflects the active locale's docs; falls back to English nav when
  // the locale has no docs translated yet so the tree is never empty.
  const { data: nav } = await useAsyncData(
    'docs-nav',
    async () => {
      const localized = await queryCollectionNavigation(collectionName('docs'))
      if (localized?.length) return localized
      return await queryCollectionNavigation(collectionName('docs', 'en'))
    },
    { watch: [locale] },
  )

  const tree = computed<DocsNavItem[]>(() => sorted(nav.value as DocsNavItem[] | undefined))
  const flat = computed<DocsNavItem[]>(() => flatten(tree.value))
  return { tree, flat }
}
