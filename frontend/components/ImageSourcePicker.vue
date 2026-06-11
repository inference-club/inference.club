<script setup lang="ts">
// A dialog for choosing the source image of an image-to-3D (mesh) generation
// from existing inference.club image generations — the user's own recent
// images, ones they've starred or bookmarked, images in a collection, or a
// search across every public image on the network. Picking a tile fetches the
// stored image into a blob and emits it, so the caller can treat it exactly
// like an uploaded file.

import { computed, ref, watch } from 'vue'
import { ChevronLeft, FolderOpen, ImageOff, Loader2, Search, X } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'
import { useInferenceRequest } from '@/composables/useInferenceRequest'
import { useContentSharing } from '@/composables/useContentSharing'
import type { Collection, InferenceRequest } from '@/types'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'select', payload: { blob: Blob; name: string }): void
}>()

const { t } = useI18n()
const { listInferenceRequests, listAllInferenceRequests } = useInferenceRequest()
const { listStarred, listBookmarked, listCollections, getCollection } = useContentSharing()

type TabKey = 'recent' | 'starred' | 'bookmarked' | 'collections' | 'search'
const TABS: TabKey[] = ['recent', 'starred', 'bookmarked', 'collections', 'search']
const tab = ref<TabKey>('recent')

interface Tile { url: string; prompt: string; id: string }
const PAGE = 24

// One tile per generated image — a request can hold several.
const toTiles = (reqs: InferenceRequest[]): Tile[] =>
  reqs.flatMap((r) =>
    (r.image_urls ?? []).map((url) => ({ url, prompt: r.prompt_preview || '', id: String(r.id) })),
  )

// --- image grid state (recent / starred / bookmarked / search) -------------
const tiles = ref<Tile[]>([])
const loading = ref(false)
const error = ref('')
const reqOffset = ref(0)
const reqCount = ref(0)
const hasMore = computed(() => reqOffset.value < reqCount.value)

// Search is committed on submit, not per keystroke.
const search = ref('')
const activeSearch = ref('')

// --- collections (two-level: list, then a chosen collection's images) ------
const collections = ref<Collection[]>([])
const activeCollection = ref<Collection | null>(null)

const fetchPage = (offset: number) => {
  const f = { type: 'IMAGE' }
  if (tab.value === 'starred') return listStarred(PAGE, offset, f)
  if (tab.value === 'bookmarked') return listBookmarked(PAGE, offset, f)
  if (tab.value === 'search')
    return listAllInferenceRequests(PAGE, offset, { type: 'IMAGE', search: activeSearch.value || undefined })
  return listInferenceRequests(PAGE, offset, f)
}

const loadGrid = async (reset: boolean) => {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const offset = reset ? 0 : reqOffset.value
    const res = await fetchPage(offset)
    const next = toTiles(res.results)
    tiles.value = reset ? next : [...tiles.value, ...next]
    reqOffset.value = offset + res.results.length
    reqCount.value = res.count
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('model3d.picker.loadFailed')
  } finally {
    loading.value = false
  }
}

const loadCollections = async () => {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    collections.value = await listCollections()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('model3d.picker.loadFailed')
  } finally {
    loading.value = false
  }
}

const openCollection = async (col: Collection) => {
  loading.value = true
  error.value = ''
  try {
    const full = await getCollection(col.slug)
    activeCollection.value = full
    tiles.value = toTiles((full.items ?? []).filter((i) => i.inference_type === 'IMAGE'))
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('model3d.picker.loadFailed')
  } finally {
    loading.value = false
  }
}

const backToCollections = () => {
  activeCollection.value = null
  tiles.value = []
}

// Reset the active view and (re)load whenever the tab changes.
const refreshTab = () => {
  tiles.value = []
  error.value = ''
  reqOffset.value = 0
  reqCount.value = 0
  activeCollection.value = null
  if (tab.value === 'collections') loadCollections()
  else loadGrid(true)
}

watch(tab, refreshTab)

// Open with a clean slate on the default tab.
watch(
  () => props.open,
  (o) => {
    if (!o) return
    search.value = ''
    activeSearch.value = ''
    if (tab.value === 'recent') refreshTab()
    else tab.value = 'recent' // triggers refreshTab via the tab watcher
  },
)

const submitSearch = () => {
  activeSearch.value = search.value.trim()
  loadGrid(true)
}
const clearSearch = () => {
  search.value = ''
  if (activeSearch.value) submitSearch()
}

// --- picking ---------------------------------------------------------------
const fileName = (tile: Tile): string => {
  const ext = tile.url.split('?')[0].match(/\.(png|jpe?g|webp|gif)$/i)?.[1] || 'png'
  const base = tile.prompt
    ? tile.prompt.slice(0, 40).replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '')
    : ''
  return `${base || `image-${tile.id}`}.${ext}`
}

const picking = ref<string | null>(null)
const pick = async (tile: Tile) => {
  if (picking.value) return
  picking.value = tile.url
  try {
    // Media assets allow credentialed GETs from our origins (same path the
    // download helper uses), so the bytes come back as a blob we can reuse.
    const res = await fetch(tile.url, { credentials: 'include' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    emit('select', { blob, name: fileName(tile) })
    emit('update:open', false)
  } catch {
    toast.error(t('model3d.picker.fetchFailed'))
  } finally {
    picking.value = null
  }
}

const emptyMessage = computed(() => {
  if (tab.value === 'collections') {
    return activeCollection.value
      ? t('model3d.picker.emptyCollectionImages')
      : t('model3d.picker.emptyCollections')
  }
  return t(
    {
      recent: 'model3d.picker.emptyRecent',
      starred: 'model3d.picker.emptyStarred',
      bookmarked: 'model3d.picker.emptyBookmarked',
      search: 'model3d.picker.emptySearch',
    }[tab.value],
  )
})

// The collection list view is the only state that shows folders instead of a
// tile grid.
const showingCollectionList = computed(
  () => tab.value === 'collections' && !activeCollection.value,
)
</script>

<template>
  <Dialog :open="open" @update:open="(v: boolean) => emit('update:open', v)">
    <DialogContent class="sm:max-w-3xl">
      <DialogHeader>
        <DialogTitle>{{ t('model3d.picker.title') }}</DialogTitle>
        <DialogDescription>{{ t('model3d.picker.description') }}</DialogDescription>
      </DialogHeader>

      <!-- min-w-0: DialogContent is a grid, and without it this row's
           non-wrapping tabs would widen the implicit column past the dialog
           on phones (every sibling then overflows with it). -->
      <Tabs v-model="tab" class="min-w-0">
        <!-- h-auto + wrap: on phones the five pills flow onto a second row
             instead of scrolling out of sight (triggers need an explicit
             height — their default is 100% of the fixed-height list). -->
        <TabsList class="h-auto w-full flex-wrap justify-start gap-0.5">
          <TabsTrigger v-for="k in TABS" :key="k" :value="k" class="h-7 flex-none">
            {{ t(`model3d.picker.${k}`) }}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <!-- Search bar (search tab only) -->
      <form
        v-if="tab === 'search'"
        class="flex items-center gap-2"
        @submit.prevent="submitSearch"
      >
        <div class="relative flex-1">
          <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            v-model="search"
            :placeholder="t('model3d.picker.searchPlaceholder')"
            class="h-9 w-full pl-8 pr-8 text-sm"
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
        <Button type="submit" size="sm">{{ t('model3d.picker.searchAction') }}</Button>
      </form>

      <!-- Back link inside a collection -->
      <button
        v-if="tab === 'collections' && activeCollection"
        type="button"
        class="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        @click="backToCollections"
      >
        <ChevronLeft class="size-4" />
        {{ t('model3d.picker.allCollections') }}
        <span class="font-medium text-foreground">· {{ activeCollection.name }}</span>
      </button>

      <div class="min-h-[18rem] max-h-[60vh] min-w-0 overflow-y-auto">
        <!-- Error -->
        <p v-if="error" class="py-12 text-center text-sm text-destructive">{{ error }}</p>

        <!-- Loading skeleton -->
        <div
          v-else-if="loading && tiles.length === 0 && !collections.length"
          class="grid grid-cols-3 sm:grid-cols-4 gap-2"
        >
          <div v-for="i in 8" :key="i" class="aspect-square rounded-lg bg-muted animate-pulse" />
        </div>

        <!-- Collection list -->
        <div v-else-if="showingCollectionList">
          <p
            v-if="!collections.length"
            class="flex flex-col items-center gap-2 py-12 text-center text-sm text-muted-foreground"
          >
            <ImageOff class="size-8 opacity-40" />
            {{ emptyMessage }}
          </p>
          <div v-else class="grid sm:grid-cols-2 gap-2">
            <button
              v-for="col in collections"
              :key="col.slug"
              type="button"
              class="flex items-center gap-3 rounded-lg border p-3 text-left transition-colors hover:bg-muted/50"
              @click="openCollection(col)"
            >
              <div
                class="size-12 shrink-0 overflow-hidden rounded-md border bg-muted flex items-center justify-center"
              >
                <img
                  v-if="col.cover_image_url"
                  :src="col.cover_image_url"
                  class="size-full object-cover"
                  loading="lazy"
                />
                <FolderOpen v-else class="size-5 text-muted-foreground" />
              </div>
              <div class="min-w-0">
                <div class="truncate text-sm font-medium">{{ col.name }}</div>
                <div class="text-xs text-muted-foreground">
                  {{ t('model3d.picker.itemCount', col.item_count) }}
                </div>
              </div>
            </button>
          </div>
        </div>

        <!-- Empty image grid -->
        <p
          v-else-if="tiles.length === 0"
          class="flex flex-col items-center gap-2 py-12 text-center text-sm text-muted-foreground"
        >
          <ImageOff class="size-8 opacity-40" />
          {{ emptyMessage }}
        </p>

        <!-- Image grid -->
        <div v-else class="grid grid-cols-3 sm:grid-cols-4 gap-2">
          <button
            v-for="(tile, i) in tiles"
            :key="`${tile.id}-${i}`"
            type="button"
            class="group relative aspect-square overflow-hidden rounded-lg border bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            :disabled="!!picking"
            @click="pick(tile)"
          >
            <img
              :src="tile.url"
              loading="lazy"
              class="size-full object-cover transition-transform duration-300 group-hover:scale-105"
            />
            <div
              class="absolute inset-0 flex items-center justify-center bg-black/0 transition-colors group-hover:bg-black/30"
            >
              <Loader2 v-if="picking === tile.url" class="size-6 animate-spin text-white" />
            </div>
            <div
              v-if="tile.prompt"
              class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-1.5 pt-4 opacity-0 transition-opacity group-hover:opacity-100"
            >
              <p class="line-clamp-2 text-[10px] leading-snug text-white/95">{{ tile.prompt }}</p>
            </div>
          </button>
        </div>

        <!-- Load more (grid tabs only) -->
        <div v-if="!showingCollectionList && hasMore" class="mt-3 flex justify-center">
          <Button variant="outline" size="sm" :disabled="loading" @click="loadGrid(false)">
            <Loader2 v-if="loading" class="size-4 animate-spin" />
            {{ t('model3d.picker.loadMore') }}
          </Button>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>
