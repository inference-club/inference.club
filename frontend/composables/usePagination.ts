import { ref, computed, type Ref, type ComputedRef } from 'vue'

export function usePagination(totalCount: Ref<number> | ComputedRef<number> | number, pageSize: number = 10, initialPage: number = 1) {
  const currentPage = ref(initialPage)
  const currentPageSize = ref(pageSize)
  const totalCountRef = typeof totalCount === 'number' ? ref(totalCount) : totalCount
  const pageCount = computed(() => Math.max(1, Math.ceil(totalCountRef.value / currentPageSize.value)))

  const isFirstPage = computed(() => currentPage.value === 1)
  const isLastPage = computed(() => currentPage.value === pageCount.value)

  function prev() {
    if (currentPage.value > 1) currentPage.value--
  }
  function next() {
    if (currentPage.value < pageCount.value) currentPage.value++
  }

  // Calculate visible page numbers (max 5)
  const visiblePages = computed(() => {
    const pages = []
    const maxVisiblePages = 5
    const total = pageCount.value
    if (total <= maxVisiblePages) {
      for (let i = 1; i <= total; i++) {
        pages.push(i)
      }
      return pages
    }
    const half = Math.floor(maxVisiblePages / 2)
    let start = Math.max(1, currentPage.value - half)
    let end = Math.min(total, currentPage.value + half)
    if (currentPage.value <= half) {
      start = 1
      end = maxVisiblePages
    } else if (currentPage.value + half > total) {
      start = total - maxVisiblePages + 1
      end = total
    }
    for (let i = start; i <= end; i++) {
      pages.push(i)
    }
    return pages
  })

  return {
    currentPage,
    currentPageSize,
    pageCount,
    isFirstPage,
    isLastPage,
    prev,
    next,
    visiblePages,
  }
}