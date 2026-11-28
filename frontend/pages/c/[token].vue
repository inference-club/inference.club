<script setup lang="ts">
// The page a collection share link opens: an album, a gallery or a mixed set,
// playable and passable on. Shows only what the viewer may see.
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useContentSharing } from '@/composables/useContentSharing'

const { t } = useI18n()
const route = useRoute()
const token = computed(() => String(route.params.token || ''))
const { getSharedCollection } = useContentSharing()

// SSR-fetch so the link unfurls with the collection's name and cover.
const { data: collection, pending: loading, error, refresh } = await useAsyncData(
  () => `shared-collection-${token.value}`,
  () => getSharedCollection(token.value),
)
// The server render has no session, so something only its owner (or a member)
// may see fails there. Ask again from the browser, which has the cookie.
onMounted(() => {
  if (error.value) refresh()
})

const owner = computed(() => collection.value?.github_login || collection.value?.owner || '')
const about = computed(() => {
  const c = collection.value
  if (!c) return t('collectionShare.fallback')
  const n = c.items?.length ?? c.item_count
  const line = t('collectionShare.about', { n, owner: owner.value ? `@${owner.value}` : 'inference.club' }, n)
  return c.description ? `${c.description} · ${line}` : line
})
const image = computed(
  () =>
    collection.value?.cover_image_url ||
    collection.value?.items?.find((r) => r.image_urls?.length)?.image_urls?.[0] ||
    undefined,
)

useSeoMeta({
  title: () => (collection.value ? `${collection.value.name} · inference.club` : 'inference.club'),
  description: () => about.value,
  ogTitle: () => collection.value?.name || 'inference.club',
  ogDescription: () => about.value,
  ogSiteName: 'inference.club',
  ogImage: () => image.value,
  twitterCard: () => (image.value ? 'summary_large_image' : 'summary'),
})
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 py-6 sm:px-6 sm:py-10">
    <div v-if="loading" class="space-y-4">
      <div class="size-44 animate-pulse rounded-2xl bg-muted" />
      <div class="h-40 animate-pulse rounded-2xl bg-muted" />
    </div>

    <div v-else-if="error || !collection" class="py-20 text-center">
      <h1 class="mb-2 text-xl font-semibold">{{ t('collectionShare.goneTitle') }}</h1>
      <p class="text-muted-foreground">{{ t('collectionShare.goneBody') }}</p>
      <Button as-child variant="outline" class="mt-6">
        <NuxtLink to="/">{{ t('request.sharePage.home') }}</NuxtLink>
      </Button>
    </div>

    <CollectionView v-else :collection="collection" />
  </div>
</template>
