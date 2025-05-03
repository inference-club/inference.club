<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useInferenceRequestStore } from '@/stores/inferenceRequest'
import { usePagination } from '@/composables/usePagination'
import PaginationControls from '@/components/PaginationControls.vue'

definePageMeta({
  layout: 'app',
})

const router = useRouter()
const store = useInferenceRequestStore()

const pagination = usePagination(computed(() => store.pagination.count), 10)

watch(() => store.pagination.count, () => {
  pagination.currentPage.value = 1 // reset to first page on data change
})

watch([pagination.currentPage, pagination.currentPageSize], ([page, size]) => {
  const offset = (page - 1) * size
  store.fetchRequests(size, offset)
})

const resultsTopRef = ref<HTMLElement | null>(null)

// Scroll to top of results when page changes
watch(pagination.currentPage, () => {
  if (resultsTopRef.value) {
    resultsTopRef.value.scrollIntoView({ behavior: 'smooth' })
  } else {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
})

onMounted(async () => {
  await store.fetchRequests(pagination.currentPageSize.value, 0)
})
</script>

<template>
  <div class="container mx-auto py-6">
    <div ref="resultsTopRef" />
    <div class="flex justify-between items-center mb-6">
      <h1 class="text-2xl font-bold">Inference Requests</h1>
      <Button @click="router.push('/inference-requests/create')">
        Create New Request
      </Button>
    </div>

    <!-- Loading Skeleton -->
    <div v-if="store.loading" class="space-y-4">
      <Card v-for="i in 3" :key="i" class="p-4 animate-pulse">
        <div class="flex justify-between items-start">
          <div class="space-y-3 w-full">
            <div class="flex items-center gap-2">
              <div class="h-6 w-20 bg-gray-200 rounded"/>
              <div class="h-6 w-24 bg-gray-200 rounded"/>
            </div>
            <div class="h-4 bg-gray-200 rounded w-3/4"/>
            <div class="h-4 bg-gray-200 rounded w-1/2"/>
          </div>
        </div>
      </Card>
    </div>

    <div v-else-if="store.error" class="text-red-500 text-center py-8">
      {{ store.error }}
    </div>

    <div v-else-if="store.requests.length === 0" class="text-center py-8 text-gray-500">
      No inference requests found
    </div>

    <div v-else class="space-y-4">
      <!-- Pagination Controls -->
      <div class="flex justify-between items-center mt-6">
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
      <Card v-for="request in store.requests" :key="request.id" class="p-4">
        <div class="flex justify-between items-start">
          <div>
            <div class="flex items-center gap-2">
              <Badge variant="outline">{{ request.inference_type }}</Badge>
              <Badge :variant="request.status === 'PROCESSED' ? 'default' : 'secondary'">
                {{ request.status }}
              </Badge>
            </div>
            <p class="text-sm text-gray-500 mt-2">{{ request.payload.prompt }}</p>
          </div>
        </div>
        <div class="mt-4 text-sm text-gray-500">
          Created: {{ new Date(request.created_on).toLocaleString() }}
        </div>
      </Card>

      <!-- Pagination Controls -->
      <div class="flex justify-between items-center mt-6">
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
  </div>
</template>