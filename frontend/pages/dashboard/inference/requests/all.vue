<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { toast } from 'vue-sonner'
import { Globe } from 'lucide-vue-next'
import { useInferenceRequestStore } from '@/stores/inferenceRequest'
import { usePagination } from '@/composables/usePagination'
import PaginationControls from '@/components/PaginationControls.vue'
import InferenceRequestCard from '@/components/InferenceRequestCard.vue'

definePageMeta({
  layout: 'app',
})

const store = useInferenceRequestStore()

const pagination = usePagination(computed(() => store.allPagination.count), 10)

watch(() => store.allPagination.count, () => {
  pagination.currentPage.value = 1
})

watch([pagination.currentPage, pagination.currentPageSize], ([page, size]) => {
  const offset = (page - 1) * size
  store.fetchAllRequests(size, offset)
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
    await store.fetchAllRequests(pagination.currentPageSize.value, offset)
  } catch {
    toast.error('Failed to delete inference request')
  } finally {
    deletingId.value = null
  }
}

const onRetried = () => {
  const offset = (pagination.currentPage.value - 1) * pagination.currentPageSize.value
  store.fetchAllRequests(pagination.currentPageSize.value, offset)
}

onMounted(async () => {
  await store.fetchAllRequests(pagination.currentPageSize.value, 0)
})
</script>

<template>
  <div class="container mx-auto py-6">
    <div ref="resultsTopRef" />
    <div class="flex flex-wrap items-end justify-between gap-y-2 mb-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <Globe class="h-6 w-6" />
          All Inference Requests
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          {{ store.allPagination.count }} request{{ store.allPagination.count === 1 ? '' : 's' }}
          across the network
        </p>
      </div>
      <button
        class="text-sm text-muted-foreground hover:text-foreground"
        :disabled="store.loading"
        @click="store.fetchAllRequests(pagination.currentPageSize.value, (pagination.currentPage.value - 1) * pagination.currentPageSize.value)"
      >
        {{ store.loading ? 'Refreshing…' : 'Refresh' }}
      </button>
    </div>

    <div v-if="store.loading && store.allRequests.length === 0" class="space-y-4">
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

    <div v-else-if="store.allRequests.length === 0" class="text-center py-12 text-muted-foreground">
      No inference requests on the network yet.
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
        v-for="request in store.allRequests"
        :key="request.id"
        :request="request"
        show-owner
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
