<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { toast } from 'vue-sonner'
import { useInferenceRequestStore } from '@/stores/inferenceRequest'
import { usePagination } from '@/composables/usePagination'
import PaginationControls from '@/components/PaginationControls.vue'
import InferenceRequestCard from '@/components/InferenceRequestCard.vue'

definePageMeta({
  layout: 'app',
})

const store = useInferenceRequestStore()

const pagination = usePagination(computed(() => store.pagination.count), 10)

// 'recent' (default, newest first) | 'popular' (most-starred first).
const sort = ref<'recent' | 'popular'>('recent')
const sortFilters = computed(() => (sort.value === 'popular' ? { sort: 'popular' } : {}))

watch(() => store.pagination.count, () => {
  pagination.currentPage.value = 1 // reset to first page on data change
})

watch([pagination.currentPage, pagination.currentPageSize], ([page, size]) => {
  const offset = (page - 1) * size
  store.fetchRequests(size, offset, sortFilters.value)
})

watch(sort, () => {
  pagination.currentPage.value = 1
  store.fetchRequests(pagination.currentPageSize.value, 0, sortFilters.value)
})

const resultsTopRef = ref<HTMLElement | null>(null)

watch(pagination.currentPage, () => {
  resultsTopRef.value?.scrollIntoView({ behavior: 'smooth' })
})

const deletingId = ref<string | null>(null)

const remove = async (id: string) => {
  deletingId.value = id
  try {
    await store.deleteRequest(id)
    toast.success('Inference request deleted')
    const offset = (pagination.currentPage.value - 1) * pagination.currentPageSize.value
    await store.fetchRequests(pagination.currentPageSize.value, offset)
  } catch {
    toast.error('Failed to delete inference request')
  } finally {
    deletingId.value = null
  }
}

// Refresh the current page after an in-place retry so the row shows its result.
const onRetried = () => {
  const offset = (pagination.currentPage.value - 1) * pagination.currentPageSize.value
  store.fetchRequests(pagination.currentPageSize.value, offset, sortFilters.value)
}

onMounted(async () => {
  await store.fetchRequests(pagination.currentPageSize.value, 0)
})
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-4 sm:px-6 py-6">
    <div ref="resultsTopRef" />
    <div class="flex flex-wrap items-end justify-between gap-y-2 mb-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">Your Inference Requests</h1>
        <p class="text-sm text-muted-foreground mt-1">
          {{ store.pagination.count }} request{{ store.pagination.count === 1 ? '' : 's' }}
        </p>
      </div>
      <div class="flex items-center gap-3">
        <div class="inline-flex rounded-md border p-0.5 text-sm">
          <button
            class="px-2.5 py-1 rounded-sm transition-colors"
            :class="sort === 'recent' ? 'bg-muted font-medium' : 'text-muted-foreground hover:text-foreground'"
            @click="sort = 'recent'"
          >
            Recent
          </button>
          <button
            class="px-2.5 py-1 rounded-sm transition-colors"
            :class="sort === 'popular' ? 'bg-muted font-medium' : 'text-muted-foreground hover:text-foreground'"
            @click="sort = 'popular'"
          >
            Most popular
          </button>
        </div>
        <button
          class="text-sm text-muted-foreground hover:text-foreground"
          :disabled="store.loading"
          @click="store.fetchRequests(pagination.currentPageSize.value, (pagination.currentPage.value - 1) * pagination.currentPageSize.value, sortFilters)"
        >
          {{ store.loading ? 'Refreshing…' : 'Refresh' }}
        </button>
      </div>
    </div>

    <div v-if="store.loading && store.requests.length === 0" class="space-y-4">
      <Card v-for="i in 3" :key="i" class="p-4 animate-pulse">
        <div class="space-y-3 w-full">
          <div class="flex items-center gap-2">
            <div class="h-6 w-20 bg-muted rounded"/>
            <div class="h-6 w-24 bg-muted rounded"/>
          </div>
          <div class="h-4 bg-muted rounded w-3/4"/>
          <div class="h-4 bg-muted rounded w-1/2"/>
        </div>
      </Card>
    </div>

    <div v-else-if="store.error" class="text-destructive text-center py-8">
      {{ store.error }}
    </div>

    <div v-else-if="store.requests.length === 0" class="text-center py-12 text-muted-foreground">
      No inference requests yet — send a chat/completions request through the proxy and it'll show up here.
    </div>

    <div v-else class="space-y-4">
      <PaginationControls
        :current-page="pagination.currentPage.value"
        :current-page-size="pagination.currentPageSize.value"
        :page-count="pagination.pageCount.value"
        :visible-pages="pagination.visiblePages.value"
        :is-first-page="pagination.isFirstPage.value"
        :is-last-page="pagination.isLastPage.value"
        :prev="pagination.prev"
        :next="pagination.next"
        :on-page-change="(page) => { pagination.currentPage.value = page }"
      />

      <InferenceRequestCard
        v-for="request in store.requests"
        :key="request.id"
        :request="request"
        :deleting="deletingId === String(request.id)"
        @delete="remove"
        @retried="onRetried"
      />

      <PaginationControls
        :current-page="pagination.currentPage.value"
        :current-page-size="pagination.currentPageSize.value"
        :page-count="pagination.pageCount.value"
        :visible-pages="pagination.visiblePages.value"
        :is-first-page="pagination.isFirstPage.value"
        :is-last-page="pagination.isLastPage.value"
        :prev="pagination.prev"
        :next="pagination.next"
        :on-page-change="(page) => { pagination.currentPage.value = page }"
      />
    </div>
  </div>
</template>
