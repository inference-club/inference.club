<script setup lang="ts">
// A dialog for choosing the source audio of a transcription from existing
// inference.club speech generations (TTS) — the user's own recent clips, ones
// they've starred or bookmarked, or a search across every public clip on the
// network. The audio counterpart of ImageSourcePicker: picking a row fetches
// the stored clip into a blob and emits it, so the caller can treat it
// exactly like an uploaded file.

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  AudioLines, Check, Loader2, Pause, Play, Search, X,
} from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { useInferenceRequest } from '@/composables/useInferenceRequest'
import { useContentSharing } from '@/composables/useContentSharing'
import type { InferenceRequest } from '@/types'
import { formatTrackTime } from '@/utils/player'
import { formatRelative } from '@/utils/inference'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'select', payload: { blob: Blob; name: string }): void
}>()

const { listInferenceRequests, listAllInferenceRequests } = useInferenceRequest()
const { listStarred, listBookmarked } = useContentSharing()

type TabKey = 'recent' | 'starred' | 'bookmarked' | 'search'
const TABS: { key: TabKey; label: string }[] = [
  { key: 'recent', label: 'Recent' },
  { key: 'starred', label: 'Starred' },
  { key: 'bookmarked', label: 'Bookmarked' },
  { key: 'search', label: 'Search' },
]
const tab = ref<TabKey>('recent')

interface Clip {
  id: string
  url: string
  prompt: string
  seconds: number | null
  created: string
}
const PAGE = 12

const toClips = (reqs: InferenceRequest[]): Clip[] =>
  reqs
    .filter((r) => r.output_audio_url)
    .map((r) => ({
      id: String(r.id),
      url: r.output_audio_url!,
      prompt: r.prompt_preview || '',
      seconds: r.audio_seconds ?? null,
      created: r.created_on,
    }))

const clips = ref<Clip[]>([])
const loading = ref(false)
const error = ref('')
const reqOffset = ref(0)
const reqCount = ref(0)
const hasMore = computed(() => reqOffset.value < reqCount.value)

// Search is committed on submit, not per keystroke.
const search = ref('')
const activeSearch = ref('')

const fetchPage = (offset: number) => {
  const f = { type: 'TTS' }
  if (tab.value === 'starred') return listStarred(PAGE, offset, f)
  if (tab.value === 'bookmarked') return listBookmarked(PAGE, offset, f)
  if (tab.value === 'search')
    return listAllInferenceRequests(PAGE, offset, { type: 'TTS', search: activeSearch.value || undefined })
  return listInferenceRequests(PAGE, offset, f)
}

const loadList = async (reset: boolean) => {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const offset = reset ? 0 : reqOffset.value
    const res = await fetchPage(offset)
    const next = toClips(res.results)
    clips.value = reset ? next : [...clips.value, ...next]
    reqOffset.value = offset + res.results.length
    reqCount.value = res.count
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load clips'
  } finally {
    loading.value = false
  }
}

const refreshTab = () => {
  clips.value = []
  error.value = ''
  reqOffset.value = 0
  reqCount.value = 0
  loadList(true)
}

watch(tab, refreshTab)

// Open with a clean slate on the default tab.
watch(
  () => props.open,
  (o) => {
    if (!o) {
      stopPreview()
      return
    }
    search.value = ''
    activeSearch.value = ''
    if (tab.value === 'recent') refreshTab()
    else tab.value = 'recent' // triggers refreshTab via the tab watcher
  },
)

const submitSearch = () => {
  activeSearch.value = search.value.trim()
  loadList(true)
}
const clearSearch = () => {
  search.value = ''
  if (activeSearch.value) submitSearch()
}

// --- inline preview (one shared element; not the global music player) ------
let previewEl: HTMLAudioElement | null = null
const playingUrl = ref<string | null>(null)

const stopPreview = () => {
  previewEl?.pause()
  playingUrl.value = null
}

const togglePreview = (clip: Clip) => {
  if (playingUrl.value === clip.url) {
    stopPreview()
    return
  }
  if (!previewEl) {
    previewEl = new Audio()
    previewEl.onended = () => (playingUrl.value = null)
  }
  previewEl.src = clip.url
  previewEl.play().catch(() => (playingUrl.value = null))
  playingUrl.value = clip.url
}

onBeforeUnmount(() => {
  stopPreview()
  previewEl = null
})

// --- picking ---------------------------------------------------------------
const fileName = (clip: Clip): string => {
  const ext = clip.url.split('?')[0].match(/\.(wav|mp3|m4a|flac|ogg|webm|opus)$/i)?.[1] || 'wav'
  const base = clip.prompt
    ? clip.prompt.slice(0, 40).replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '')
    : ''
  return `${base || `speech-${clip.id}`}.${ext}`
}

const picking = ref<string | null>(null)
const pick = async (clip: Clip) => {
  if (picking.value) return
  picking.value = clip.id
  try {
    // Media assets allow credentialed GETs from our origins (same path the
    // download helper uses), so the bytes come back as a blob we can reuse.
    const res = await fetch(clip.url, { credentials: 'include' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    stopPreview()
    emit('select', { blob, name: fileName(clip) })
    emit('update:open', false)
  } catch {
    toast.error('Could not fetch that clip — try another one')
  } finally {
    picking.value = null
  }
}

const emptyMessage = computed(
  () =>
    ({
      recent: "You haven't generated any speech clips yet.",
      starred: "You haven't starred any speech clips.",
      bookmarked: "You haven't bookmarked any speech clips.",
      search: 'No public speech clips match your search.',
    })[tab.value],
)
</script>

<template>
  <Dialog :open="open" @update:open="(v: boolean) => emit('update:open', v)">
    <DialogContent class="sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>Pick a generated clip</DialogTitle>
        <DialogDescription>
          Transcribe speech you already generated — yours, or any public clip on the network.
        </DialogDescription>
      </DialogHeader>

      <Tabs v-model="tab">
        <TabsList class="w-full justify-start overflow-x-auto">
          <TabsTrigger v-for="t_ in TABS" :key="t_.key" :value="t_.key">
            {{ t_.label }}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <!-- Search bar (search tab only) -->
      <form v-if="tab === 'search'" class="flex items-center gap-2" @submit.prevent="submitSearch">
        <div class="relative flex-1">
          <Search class="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input v-model="search" placeholder="Search public speech clips…" class="h-9 w-full pl-8 pr-8 text-sm" />
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

      <div class="max-h-[60vh] min-h-[14rem] overflow-y-auto">
        <p v-if="error" class="py-12 text-center text-sm text-destructive">{{ error }}</p>

        <!-- Loading skeleton -->
        <div v-else-if="loading && clips.length === 0" class="space-y-2">
          <div v-for="i in 5" :key="i" class="h-12 animate-pulse rounded-lg bg-muted" />
        </div>

        <!-- Empty -->
        <p
          v-else-if="clips.length === 0"
          class="flex flex-col items-center gap-2 py-12 text-center text-sm text-muted-foreground"
        >
          <AudioLines class="size-8 opacity-40" />
          {{ emptyMessage }}
        </p>

        <!-- Clip rows -->
        <div v-else class="space-y-1.5">
          <div
            v-for="clip in clips"
            :key="clip.id"
            class="flex items-center gap-3 rounded-lg border px-3 py-2 transition-colors hover:bg-muted/50"
            :data-testid="`audio-pick-${clip.id}`"
          >
            <Button
              variant="ghost"
              size="icon"
              class="size-8 shrink-0"
              :class="playingUrl === clip.url ? 'text-primary' : 'text-muted-foreground'"
              :title="playingUrl === clip.url ? 'Pause preview' : 'Preview'"
              @click="togglePreview(clip)"
            >
              <component :is="playingUrl === clip.url ? Pause : Play" class="size-4" />
            </Button>
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm" :title="clip.prompt">
                {{ clip.prompt || 'Untitled clip' }}
              </p>
              <p class="text-xs text-muted-foreground">
                <template v-if="clip.seconds != null">{{ formatTrackTime(clip.seconds) }} · </template>
                {{ formatRelative(clip.created) }}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              class="shrink-0 gap-1.5"
              :disabled="!!picking"
              @click="pick(clip)"
            >
              <component :is="picking === clip.id ? Loader2 : Check" class="size-3.5" :class="picking === clip.id ? 'animate-spin' : ''" />
              Use
            </Button>
          </div>
        </div>

        <!-- Load more -->
        <div v-if="hasMore" class="mt-3 flex justify-center">
          <Button variant="outline" size="sm" :disabled="loading" @click="loadList(false)">
            <Loader2 v-if="loading" class="size-4 animate-spin" />
            Load more
          </Button>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>
