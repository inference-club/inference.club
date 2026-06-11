<script setup lang="ts">
import { Pagination, PaginationContent, PaginationItem, PaginationPrevious, PaginationNext, PaginationFirst, PaginationLast, PaginationEllipsis } from '@/components/ui/pagination'
import type { PropType } from 'vue'

const _props = defineProps({
  currentPage: { type: Number, required: true },
  currentPageSize: { type: Number, required: true },
  pageCount: { type: Number, required: true },
  visiblePages: { type: Array as PropType<number[]>, required: true },
  isFirstPage: { type: Boolean, required: true },
  isLastPage: { type: Boolean, required: true },
  prev: { type: Function as PropType<() => void>, required: true },
  next: { type: Function as PropType<() => void>, required: true },
  onPageChange: { type: Function as PropType<(page: number) => void>, required: true },
})
</script>

<template>
  <Pagination :total="pageCount" :page="currentPage" :items-per-page="currentPageSize" class="">
    <PaginationContent>
      <PaginationFirst class="hidden sm:inline-flex" :disabled="isFirstPage" @click="onPageChange(1)" />
      <PaginationPrevious :disabled="isFirstPage" @click="prev()" />
      <PaginationEllipsis v-if="visiblePages[0] > 2" class="hidden sm:flex" />
      <PaginationItem
        v-for="page in visiblePages"
        :key="page"
        :value="page"
        :is-active="currentPage === page"
        :class="currentPage === page ? '' : 'hidden sm:inline-flex'"
        @click="onPageChange(page)"
      >
        {{ page }}
      </PaginationItem>
      <PaginationEllipsis v-if="visiblePages[visiblePages.length - 1] < pageCount - 1" class="hidden sm:flex" />
      <PaginationNext :disabled="isLastPage" @click="next()" />
      <PaginationLast class="hidden sm:inline-flex" :disabled="isLastPage" @click="onPageChange(pageCount)" />
    </PaginationContent>
  </Pagination>
</template>