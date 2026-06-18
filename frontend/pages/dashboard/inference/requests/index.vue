<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { toast } from 'vue-sonner'
import {
  LayoutGrid, Rows3, MessageSquare, Image as ImageIcon, Clapperboard, Mic, Mic2,
  AudioLines, Music, Box, Waves, Globe,
} from 'lucide-vue-next'
import { useInferenceRequestStore } from '@/stores/inferenceRequest'
import { usePagination } from '@/composables/usePagination'
import PaginationControls from '@/components/PaginationControls.vue'
import InferenceRequestCard from '@/components/InferenceRequestCard.vue'
import InferenceRequestRow from '@/components/InferenceRequestRow.vue'

definePageMeta({
  layout: 'app',
})

const store = useInferenceRequestStore()

const pagination = usePagination(computed(() => store.pagination.count), 10)

// 'recent' (default, newest first) | 'popular' (most-starred first).
const sort = ref<'recent' | 'popular'>('recent')

// Toggleable inference-type filters. Each carries its ModalityBadge identity
// (icon + tint) so the active chip matches how the type reads elsewhere. 'ALL'
// is the unfiltered state; clicking the active chip toggles back to it.
const TYPE_FILTERS: { value: string; label: string; icon: unknown; active: string }[] = [
  { value: 'LLM', label: 'Chat', icon: MessageSquare, active: 'bg-sky-500/10 text-sky-700 dark:text-sky-400 border-sky-500/40' },
  { value: 'IMAGE', label: 'Image', icon: ImageIcon, active: 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/40' },
  { value: 'VIDEO', label: 'Video', icon: Clapperboard, active: 'bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/40' },
  { value: 'STT', label: 'Transcription', icon: Mic, active: 'bg-teal-500/10 text-teal-700 dark:text-teal-400 border-teal-500/40' },
  { value: 'TTS', label: 'Speech', icon: AudioLines, active: 'bg-violet-500/10 text-violet-700 dark:text-violet-400 border-violet-500/40' },
  { value: 'MUSIC', label: 'Music', icon: Music, active: 'bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-400 border-fuchsia-500/40' },
  { value: 'MESH', label: '3D', icon: Box, active: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/40' },
  { value: 'VOICE', label: 'Voice', icon: Mic2, active: 'bg-violet-500/10 text-violet-700 dark:text-violet-400 border-violet-500/40' },
  { value: 'ENHANCE', label: 'Enhance', icon: Waves, active: 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-400 border-cyan-500/40' },
  { value: 'SCRAPE', label: 'Scrape', icon: Globe, active: 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/40' },
]
const type = ref('ALL')
const toggleType = (v: string) => { type.value = type.value === v ? 'ALL' : v }

// 'full' = the rich InferenceRequestCard; 'narrow' = dense one-line rows.
// Persisted so the preference sticks across visits.
const view = ref<'full' | 'narrow'>('full')

const activeFilters = computed(() => {
  const f: { type?: string; sort?: string } = {}
  if (type.value && type.value !== 'ALL') f.type = type.value
  if (sort.value === 'popular') f.sort = 'popular'
  return f
})

const reload = (page = pagination.currentPage.value) => {
  const size = pagination.currentPageSize.value
  return store.fetchRequests(size, (page - 1) * size, activeFilters.value)
}

watch([pagination.currentPage, pagination.currentPageSize], ([page, size]) => {
  store.fetchRequests(size, (page - 1) * size, activeFilters.value)
})

// Changing a filter resets to the first page and refetches.
watch([sort, type], () => {
  pagination.currentPage.value = 1
  reload(1)
})

watch(view, (v) => {
  if (import.meta.client) localStorage.setItem('ir-view', v)
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
    await reload()
  } catch {
    toast.error('Failed to delete inference request')
  } finally {
    deletingId.value = null
  }
}

// Refresh the current page after an in-place retry so the row shows its result.
const onRetried = () => reload()

onMounted(async () => {
  if (import.meta.client) {
    const saved = localStorage.getItem('ir-view')
    if (saved === 'narrow' || saved === 'full') view.value = saved
  }
  await reload(1)
})
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-3 sm:px-6 py-6">
    <div ref="resultsTopRef" />
    <div class="flex flex-wrap items-end justify-between gap-y-2 mb-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">Your Inference Requests</h1>
        <p class="text-sm text-muted-foreground mt-1">
          {{ store.pagination.count }} request{{ store.pagination.count === 1 ? '' : 's' }}
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <!-- Sort -->
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

        <!-- View density toggle -->
        <div class="inline-flex rounded-md border p-0.5">
          <button
            class="p-1.5 rounded-sm transition-colors"
            :class="view === 'full' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'"
            title="Full view"
            aria-label="Full view"
            @click="view = 'full'"
          >
            <LayoutGrid class="size-4" />
          </button>
          <button
            class="p-1.5 rounded-sm transition-colors"
            :class="view === 'narrow' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'"
            title="Narrow view"
            aria-label="Narrow view"
            @click="view = 'narrow'"
          >
            <Rows3 class="size-4" />
          </button>
        </div>

        <button
          class="text-sm text-muted-foreground hover:text-foreground"
          :disabled="store.loading"
          @click="reload()"
        >
          {{ store.loading ? 'Refreshing…' : 'Refresh' }}
        </button>
      </div>
    </div>

    <!-- Type filter: a row of toggleable chips. On mobile they center and
         collapse to icon-only so the row stays compact; labels return at sm+. -->
    <div class="flex flex-wrap items-center justify-center sm:justify-start gap-1.5 mb-6">
      <button
        class="inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium transition-colors"
        :class="type === 'ALL' ? 'bg-foreground text-background border-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
        @click="type = 'ALL'"
      >
        All
      </button>
      <button
        v-for="f in TYPE_FILTERS"
        :key="f.value"
        class="inline-flex items-center gap-1.5 rounded-full border px-2 sm:px-2.5 py-1 text-xs font-medium transition-colors"
        :class="type === f.value ? f.active : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
        :aria-pressed="type === f.value"
        :aria-label="f.label"
        :title="f.label"
        @click="toggleType(f.value)"
      >
        <component :is="f.icon" class="size-3.5 shrink-0" />
        <span class="hidden sm:inline">{{ f.label }}</span>
      </button>
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
      <template v-if="type !== 'ALL'">
        No {{ TYPE_FILTERS.find((o) => o.value === type)?.label.toLowerCase() }} requests yet.
      </template>
      <template v-else>
        No inference requests yet — send a chat/completions request through the proxy and it'll show up here.
      </template>
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

      <!-- Narrow (dense) view -->
      <div v-if="view === 'narrow'" class="space-y-1.5">
        <InferenceRequestRow
          v-for="request in store.requests"
          :key="request.id"
          :request="request"
          :deleting="deletingId === String(request.id)"
          @delete="remove"
        />
      </div>

      <!-- Full (card) view -->
      <template v-else>
        <InferenceRequestCard
          v-for="request in store.requests"
          :key="request.id"
          :request="request"
          :deleting="deletingId === String(request.id)"
          @delete="remove"
          @retried="onRetried"
        />
      </template>

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
