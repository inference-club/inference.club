<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Images as ImagesIcon, Search, X } from 'lucide-vue-next'
import { useInferenceRequest } from '@/composables/useInferenceRequest'
import { usePagination } from '@/composables/usePagination'
import PaginationControls from '@/components/PaginationControls.vue'
import type { InferenceRequest } from '@/types'

definePageMeta({ layout: 'app' })

const { listAllInferenceRequests } = useInferenceRequest()

const PAGE_SIZE = 24
const requests = ref<InferenceRequest[]>([])
const count = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

// `search` is the live input; `activeSearch` is what's actually queried (only
// updated on submit) so we don't fire a request on every keystroke.
const search = ref('')
const activeSearch = ref('')

const pager = usePagination(computed(() => count.value), PAGE_SIZE)

// One tile per generated image (a request may hold several).
const tiles = computed(() =>
  requests.value.flatMap((r) =>
    (r.image_urls ?? []).map((url) => ({
      url,
      id: String(r.id),
      prompt: r.prompt_preview || '',
      owner: r.github_login || r.owner || '',
    })),
  ),
)

const load = async () => {
  loading.value = true
  error.value = null
  try {
    const offset = (pager.currentPage.value - 1) * PAGE_SIZE
    const res = await listAllInferenceRequests(PAGE_SIZE, offset, {
      type: 'IMAGE',
      search: activeSearch.value || undefined,
    })
    requests.value = res.results
    count.value = res.count
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load gallery'
  } finally {
    loading.value = false
  }
}

const submitSearch = () => {
  activeSearch.value = search.value.trim()
  pager.currentPage.value = 1
}
const clearSearch = () => {
  search.value = ''
  submitSearch()
}

// Both refs may change in the same tick (submit resets the page); the array
// watcher coalesces that into a single reload.
watch([pager.currentPage, activeSearch], load)
onMounted(load)
</script>

<template>
  <div class="container mx-auto py-6">
    <div class="flex flex-wrap items-end justify-between gap-3 mb-6">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <ImagesIcon class="size-6" /> Gallery
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Every image generated across the network{{ count ? ` — ${count.toLocaleString()} so far` : '' }}.
        </p>
      </div>

      <form class="flex items-center gap-2" @submit.prevent="submitSearch">
        <div class="relative">
          <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            v-model="search"
            placeholder="Search prompts…"
            class="h-9 w-56 pl-8 pr-8 text-sm"
          />
          <button
            v-if="search"
            type="button"
            class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            @click="clearSearch"
          >
            <X class="size-4" />
          </button>
        </div>
        <Button type="submit" size="sm">Search</Button>
      </form>
    </div>

    <!-- Loading skeleton -->
    <div
      v-if="loading && tiles.length === 0"
      class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3"
    >
      <div v-for="i in 12" :key="i" class="aspect-square rounded-lg bg-muted animate-pulse" />
    </div>

    <div v-else-if="error" class="text-destructive text-center py-12">{{ error }}</div>

    <div
      v-else-if="tiles.length === 0"
      class="rounded-lg border bg-card p-12 text-center text-sm text-muted-foreground"
    >
      <template v-if="activeSearch">No images match “{{ activeSearch }}”.</template>
      <template v-else>No images have been generated on the network yet.</template>
    </div>

    <template v-else>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        <NuxtLink
          v-for="(t, i) in tiles"
          :key="`${t.id}-${i}`"
          :to="`/dashboard/inference/requests/${t.id}`"
          class="group relative block aspect-square overflow-hidden rounded-lg border bg-muted"
        >
          <img
            :src="t.url"
            loading="lazy"
            class="size-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
          <!-- Prompt overlay along the bottom for readability over any image -->
          <div
            v-if="t.prompt"
            class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 via-black/45 to-transparent p-2.5 pt-6"
          >
            <p class="text-xs text-white/95 line-clamp-2 leading-snug">{{ t.prompt }}</p>
          </div>
        </NuxtLink>
      </div>

      <PaginationControls
        v-if="pager.pageCount.value > 1"
        class="mt-6"
        :current-page="pager.currentPage.value"
        :current-page-size="pager.currentPageSize.value"
        :page-count="pager.pageCount.value"
        :visible-pages="pager.visiblePages.value"
        :is-first-page="pager.isFirstPage.value"
        :is-last-page="pager.isLastPage.value"
        :prev="pager.prev"
        :next="pager.next"
        :on-page-change="(page) => { pager.currentPage.value = page }"
      />
    </template>
  </div>
</template>
