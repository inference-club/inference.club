<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useInferenceRequestStore } from '@/stores/inferenceRequest'
import { useOffsetPagination } from '@vueuse/core'

const router = useRouter()
const store = useInferenceRequestStore()

const {
  currentPage,
  currentPageSize,
  pageCount,
  isFirstPage,
  isLastPage,
  prev,
  next,
} = useOffsetPagination({
  total: computed(() => store.pagination.count),
  page: 1,
  pageSize: 10,
  onPageChange: async ({ currentPage, currentPageSize }) => {
    const offset = (currentPage - 1) * currentPageSize
    await store.fetchRequests(currentPageSize, offset)
  },
  onPageSizeChange: async ({ currentPage, currentPageSize }) => {
    const offset = (currentPage - 1) * currentPageSize
    await store.fetchRequests(currentPageSize, offset)
  },
})

// Calculate visible page numbers
const visiblePages = computed(() => {
  const pages = []
  const maxVisiblePages = 5
  const halfVisible = Math.floor(maxVisiblePages / 2)

  let start = Math.max(1, currentPage.value - halfVisible)
  const end = Math.min(pageCount.value, start + maxVisiblePages - 1)

  if (end - start + 1 < maxVisiblePages) {
    start = Math.max(1, end - maxVisiblePages + 1)
  }

  for (let i = start; i <= end; i++) {
    pages.push(i)
  }

  return pages
})

onMounted(async () => {
  await store.fetchRequests(currentPageSize.value, 0)
})
</script>

<template>
  <div class="container mx-auto py-6">
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
        <div class="text-sm text-gray-500">
          Showing {{ store.requests.length }} of {{ store.pagination.count }} requests
        </div>
        <div class="flex items-center gap-2">
          <Button
            variant="outline"
            :disabled="isFirstPage"
            @click="prev"
          >
            Previous
          </Button>

          <!-- First Page -->
          <Button
            v-if="visiblePages[0] > 1"
            variant="outline"
            @click="currentPage = 1"
          >
            1
          </Button>

          <!-- Ellipsis -->
          <span v-if="visiblePages[0] > 2" class="px-2">...</span>

          <!-- Page Numbers -->
          <Button
            v-for="page in visiblePages"
            :key="page"
            variant="outline"
            :class="{ 'bg-primary text-primary-foreground': currentPage === page }"
            @click="currentPage = page"
          >
            {{ page }}
          </Button>

          <!-- Ellipsis -->
          <span v-if="visiblePages[visiblePages.length - 1] < pageCount - 1" class="px-2">...</span>

          <!-- Last Page -->
          <Button
            v-if="visiblePages[visiblePages.length - 1] < pageCount"
            variant="outline"
            @click="currentPage = pageCount"
          >
            {{ pageCount }}
          </Button>

          <Button
            variant="outline"
            :disabled="isLastPage"
            @click="next"
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>