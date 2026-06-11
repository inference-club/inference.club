<script setup lang="ts">
// Home-page featured showcase: the most recently staff-featured PUBLIC
// request per modality. Renders nothing at all when nothing is featured —
// the section earns its place only when there's content to show.

import { useContentSharing } from '@/composables/useContentSharing'

const { t } = useI18n()
const { listFeatured } = useContentSharing()

// SSR-fetched so the landing page (and its crawlers) get the full section.
const { data: items } = await useAsyncData('home:featured-requests', async () => {
  try {
    return await listFeatured()
  } catch {
    return [] // a hiccup here must never break the landing page
  }
})
</script>

<template>
  <section v-if="items?.length" class="relative px-4 sm:px-6 lg:px-8 pb-24">
    <div class="max-w-6xl mx-auto">
      <div class="text-center mb-10">
        <p class="text-xs font-mono uppercase tracking-wider text-muted-foreground mb-3">
          {{ t('home.featuredEyebrow') }}
        </p>
        <h2 class="text-3xl sm:text-4xl font-bold tracking-tight">
          {{ t('home.featuredTitleLead') }}
          <span class="bg-gradient-to-r from-violet-500 via-fuchsia-500 to-cyan-500 bg-clip-text text-transparent">{{ t('home.featuredTitleHighlight') }}</span>
        </h2>
        <p class="mt-3 text-muted-foreground text-sm sm:text-base max-w-2xl mx-auto">
          {{ t('home.featuredSubtitle') }}
        </p>
      </div>

      <div class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 *:min-w-0">
        <FeaturedCard v-for="item in items" :key="item.id" :item="item" />
      </div>
    </div>
  </section>
</template>
