<script setup lang="ts">
import { ArrowLeft, ArrowRight } from 'lucide-vue-next'

definePageMeta({ layout: 'docs' })

const route = useRoute()
const { t } = useI18n()
const localePath = useLocalePath()
const { findByPath } = useLocalizedContent()

// Active-locale docs page, falling back to English when untranslated.
const { data } = await useAsyncData(
  `docs:${route.path}`,
  () => findByPath('docs', route.path),
)
const page = computed(() => data.value?.doc ?? null)
const fellBack = computed(() => data.value?.fellBack ?? false)

if (!page.value) {
  throw createError({ statusCode: 404, statusMessage: 'Doc not found' })
}

// Prev/next follow the sidebar's reading order (same tree, same sort).
const { flat } = await useDocsNav()
const surroundings = computed(() => {
  const idx = flat.value.findIndex((item) => localePath(item.path) === route.path)
  if (idx === -1) return { prev: null, next: null }
  return {
    prev: flat.value[idx - 1] ?? null,
    next: flat.value[idx + 1] ?? null,
  }
})

interface TocLink {
  id: string
  text: string
  depth: number
  children?: TocLink[]
}
const toc = computed<TocLink[]>(() => page.value?.body?.toc?.links ?? [])

useSeoMeta({
  title: page.value.title ? `${page.value.title} · inference.club docs` : 'inference.club docs',
  description: page.value.description,
})
</script>

<template>
  <div class="mx-auto flex max-w-5xl justify-center gap-10">
    <div class="min-w-0 max-w-3xl flex-1">
      <article class="prose prose-neutral dark:prose-invert min-w-0 max-w-none break-words">
        <ContentFallbackBanner v-if="fellBack" />
        <ContentRenderer v-if="page" :value="page" />
      </article>

      <!-- Prev / next, in sidebar reading order -->
      <nav
        v-if="surroundings.prev || surroundings.next"
        class="mt-10 flex gap-3 border-t pt-5 text-sm"
      >
        <NuxtLink
          v-if="surroundings.prev"
          :to="localePath(surroundings.prev.path)"
          class="group flex min-w-0 items-center gap-2 rounded-lg border px-4 py-3 hover:bg-muted/50 transition-colors"
        >
          <ArrowLeft class="size-4 shrink-0 text-muted-foreground" />
          <span class="min-w-0">
            <span class="block text-xs text-muted-foreground">{{ t('docs.previous') }}</span>
            <span class="block truncate font-medium group-hover:text-primary">{{ surroundings.prev.title }}</span>
          </span>
        </NuxtLink>
        <NuxtLink
          v-if="surroundings.next"
          :to="localePath(surroundings.next.path)"
          class="group ml-auto flex min-w-0 items-center gap-2 rounded-lg border px-4 py-3 text-right hover:bg-muted/50 transition-colors"
        >
          <span class="min-w-0">
            <span class="block text-xs text-muted-foreground">{{ t('docs.next') }}</span>
            <span class="block truncate font-medium group-hover:text-primary">{{ surroundings.next.title }}</span>
          </span>
          <ArrowRight class="size-4 shrink-0 text-muted-foreground" />
        </NuxtLink>
      </nav>
    </div>

    <!-- Table of contents (wide screens) -->
    <aside v-if="toc.length" class="hidden w-52 shrink-0 xl:block">
      <nav class="sticky top-20 text-sm">
        <p class="mb-2 text-xs font-medium text-muted-foreground">{{ t('docs.onThisPage') }}</p>
        <ul class="space-y-1.5 border-l pl-3">
          <li v-for="link in toc" :key="link.id">
            <a
              :href="`#${link.id}`"
              class="block text-muted-foreground hover:text-foreground transition-colors"
            >
              {{ link.text }}
            </a>
            <ul v-if="link.children?.length" class="mt-1.5 space-y-1.5 pl-3">
              <li v-for="child in link.children" :key="child.id">
                <a
                  :href="`#${child.id}`"
                  class="block text-muted-foreground hover:text-foreground transition-colors"
                >
                  {{ child.text }}
                </a>
              </li>
            </ul>
          </li>
        </ul>
      </nav>
    </aside>
  </div>
</template>
