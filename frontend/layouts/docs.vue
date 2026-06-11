<script setup lang="ts">
import TopBar from '@/components/TopBar.vue'

const localePath = useLocalePath()
// Sidebar tree (order frontmatter ascending, then title), shared with doc
// pages' prev/next links via useDocsNav.
const { tree } = await useDocsNav()
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
      <!-- Width + prose styling live in the pages so a doc page can put a
           table of contents beside the article. -->
      <main class="flex-1 min-w-0 break-words px-6 py-8">
        <slot />
      </main>
    </div>
  </div>
</template>
