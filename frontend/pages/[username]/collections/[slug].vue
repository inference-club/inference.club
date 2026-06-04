<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import type { Collection } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'
import InferenceRequestCard from '@/components/InferenceRequestCard.vue'

const route = useRoute()
const username = computed(() => String(route.params.username || ''))
const slug = computed(() => String(route.params.slug || ''))
const { getPublicCollection } = useContentSharing()

const collection = ref<Collection | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const load = async () => {
  loading.value = true
  error.value = null
  try {
    collection.value = await getPublicCollection(username.value, slug.value)
  } catch {
    error.value = 'Collection not found or not public.'
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
  <div class="container mx-auto py-8 max-w-5xl px-4">
    <NuxtLink
      :to="`/${username}`"
      class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6"
    >
      <ArrowLeft class="size-4" /> @{{ username }}
    </NuxtLink>

    <div v-if="loading" class="space-y-4">
      <div class="h-8 w-64 bg-muted rounded animate-pulse" />
      <Card class="p-4 animate-pulse h-40" />
    </div>

    <div v-else-if="error" class="text-center py-16 text-muted-foreground">{{ error }}</div>

    <template v-else-if="collection">
      <div class="mb-6">
        <div class="flex items-center gap-2 flex-wrap">
          <h1 class="text-2xl font-bold">{{ collection.name }}</h1>
          <VisibilityBadge :visibility="collection.visibility" />
        </div>
        <p v-if="collection.description" class="text-muted-foreground mt-1">
          {{ collection.description }}
        </p>
        <p class="text-sm text-muted-foreground mt-1">
          by
          <NuxtLink :to="`/${collection.github_login || username}`" class="underline font-mono">
            @{{ collection.github_login || username }}
          </NuxtLink>
          · {{ collection.item_count }} item{{ collection.item_count === 1 ? '' : 's' }}
        </p>
      </div>

      <div
        v-if="!collection.items?.length"
        class="text-center py-12 text-muted-foreground"
      >
        Nothing public in this collection yet.
      </div>

      <div v-else class="space-y-4">
        <InferenceRequestCard
          v-for="request in collection.items"
          :key="request.id"
          :request="request"
          :linkable="false"
          :actions="false"
          show-owner
        />
      </div>
    </template>
  </div>
</template>
