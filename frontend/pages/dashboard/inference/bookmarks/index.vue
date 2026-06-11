<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Bookmark } from 'lucide-vue-next'
import type { InferenceRequest } from '@/types'
import { useContentSharing } from '@/composables/useContentSharing'
import InferenceRequestCard from '@/components/InferenceRequestCard.vue'

definePageMeta({ layout: 'app' })

const { listBookmarked } = useContentSharing()

const requests = ref<InferenceRequest[]>([])
const count = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
const PAGE = 12

const load = async (reset = false) => {
  loading.value = true
  error.value = null
  try {
    const offset = reset ? 0 : requests.value.length
    const res = await listBookmarked(PAGE, offset)
    count.value = res.count
    requests.value = reset ? res.results : [...requests.value, ...res.results]
  } catch {
    error.value = 'Failed to load bookmarks'
  } finally {
    loading.value = false
  }
}

onMounted(() => load(true))
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-3 sm:px-6 py-6">
    <div class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
        <Bookmark class="size-6 text-primary" /> Bookmarks
      </h1>
      <p class="text-sm text-muted-foreground mt-1">
        {{ count }} bookmarked request{{ count === 1 ? '' : 's' }}. These appear on your public profile.
      </p>
    </div>

    <div v-if="error" class="text-destructive text-center py-8">{{ error }}</div>

    <div
      v-else-if="!loading && requests.length === 0"
      class="text-center py-12 text-muted-foreground"
    >
      No bookmarks yet — bookmark a request to feature it on your public profile.
    </div>

    <div v-else class="space-y-4">
      <InferenceRequestCard
        v-for="request in requests"
        :key="request.id"
        :request="request"
      />
      <div v-if="requests.length < count" class="text-center pt-2">
        <Button variant="outline" :disabled="loading" @click="load(false)">
          {{ loading ? 'Loading…' : 'Load more' }}
        </Button>
      </div>
    </div>
  </div>
</template>
