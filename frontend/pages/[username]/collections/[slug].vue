<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import type { Collection } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'

const route = useRoute()
const username = computed(() => String(route.params.username || ''))
const slug = computed(() => String(route.params.slug || ''))
const { getPublicCollection } = useContentSharing()
const { t } = useI18n()

const collection = ref<Collection | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const load = async () => {
  loading.value = true
  error.value = null
  try {
    collection.value = await getPublicCollection(username.value, slug.value)
  } catch {
    error.value = t('collectionShare.goneBody')
  } finally {
    loading.value = false
  }
}

useHead(() => ({
  title: collection.value
    ? `${collection.value.name} · @${username.value}`
    : 'Collection',
}))

onMounted(load)
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 py-6 sm:px-6 sm:py-8">
    <NuxtLink
      :to="`/${username}`"
      class="mb-6 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft class="size-4" /> @{{ username }}
    </NuxtLink>

    <div v-if="loading" class="space-y-4">
      <div class="size-44 animate-pulse rounded-2xl bg-muted" />
      <div class="h-40 animate-pulse rounded-2xl bg-muted" />
    </div>

    <div v-else-if="error" class="py-16 text-center text-muted-foreground">{{ error }}</div>

    <CollectionView v-else-if="collection" :collection="collection" />
  </div>
</template>
