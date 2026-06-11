<script setup lang="ts">
import TopBar from '@/components/TopBar.vue'

// Sidebar tree for docs. queryCollectionNavigation returns a hierarchy
// derived from the directory structure plus frontmatter (`order`, `title`).
// We sort each level by `order` ascending then by title.
type NavItem = {
  title: string
  path: string
  order?: number
  children?: NavItem[]
}

const localePath = useLocalePath()
const { collectionName, locale } = useLocalizedContent()

// Sidebar reflects the active locale's docs; falls back to English nav when the
// locale has no docs translated yet so the tree is never empty.
const { data: nav } = await useAsyncData(
  'docs-nav',
  async () => {
    const localized = await queryCollectionNavigation(collectionName('docs'))
    if (localized?.length) return localized
    return await queryCollectionNavigation(collectionName('docs', 'en'))
  },
  { watch: [locale] },
)

function sorted(items: NavItem[] | undefined): NavItem[] {
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

const tree = computed<NavItem[]>(() => sorted(nav.value as NavItem[] | undefined))
const route = useRoute()
// item paths are locale-free (/docs/x); compare against the localized form so
// the active item highlights correctly under a locale prefix (/fr/docs/x).
const isActive = (path: string) => route.path === localePath(path)
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <TopBar />
    <div class="flex flex-1">
      <aside class="hidden md:block w-64 shrink-0 border-r bg-muted/30">
        <nav class="sticky top-14 p-6 text-sm">
          <ul class="space-y-1">
            <template v-for="item in tree" :key="item.path">
              <li>
                <NuxtLink
                  :to="localePath(item.path)"
                  :class="[
                    'block px-2 py-1 rounded hover:bg-accent',
                    isActive(item.path) ? 'bg-accent text-accent-foreground font-medium' : '',
                  ]"
                >
                  {{ item.title }}
                </NuxtLink>
                <ul v-if="item.children?.length" class="mt-1 ml-3 space-y-1 border-l pl-3">
                  <li v-for="child in item.children" :key="child.path">
                    <NuxtLink
                      :to="localePath(child.path)"
                      :class="[
                        'block px-2 py-1 rounded hover:bg-accent',
                        isActive(child.path) ? 'bg-accent text-accent-foreground font-medium' : '',
                      ]"
                    >
                      {{ child.title }}
                    </NuxtLink>
                  </li>
                </ul>
              </li>
            </template>
          </ul>
        </nav>
      </aside>
      <main class="flex-1 min-w-0 break-words px-6 py-8 max-w-3xl mx-auto prose prose-neutral dark:prose-invert">
        <slot />
      </main>
    </div>
  </div>
</template>
