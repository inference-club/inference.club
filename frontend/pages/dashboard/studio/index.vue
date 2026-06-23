<script setup lang="ts">
/**
 * Narration Studio home: your episodes + a "paste text → split into segments"
 * creator (the from-text endpoint splits whole sentences into narration-sized
 * chunks). Open an episode to clean/transcribe/trim/grade and redo takes.
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Loader2, Mic, Scissors, Trash2 } from 'lucide-vue-next'
import { useStudio, type EpisodeSummary } from '@/composables/useStudio'

definePageMeta({ layout: 'app', requireAuth: true, gateTitleKey: 'dashboard.items.studio' })

const studio = useStudio()
const router = useRouter()

const episodes = ref<EpisodeSummary[]>([])
const loading = ref(true)
const creating = ref(false)
const error = ref<string | null>(null)

const text = ref('')
const title = ref('')
const targetWords = ref(32)

const canCreate = computed(() => !!text.value.trim() && !creating.value)

async function load() {
  try {
    episodes.value = await studio.listEpisodes()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load episodes'
  } finally {
    loading.value = false
  }
}

async function createFromText() {
  if (!canCreate.value) return
  creating.value = true
  error.value = null
  try {
    const ep = await studio.createFromText(text.value.trim(), targetWords.value, title.value.trim() || undefined)
    router.push(`/dashboard/studio/${ep.id}`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to create episode'
    creating.value = false
  }
}

async function remove(ep: EpisodeSummary) {
  if (!confirm(`Delete "${ep.title}"? This removes its segments and takes.`)) return
  await studio.deleteEpisode(ep.id)
  await load()
}

onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-6 px-4 py-6">
    <div class="flex items-center gap-2">
      <Mic class="size-6 text-fuchsia-500" />
      <h1 class="text-xl font-semibold">Narration Studio</h1>
    </div>

    <!-- paste → split -->
    <div class="space-y-3 rounded-xl border bg-background p-4">
      <div class="flex items-center gap-2 text-sm font-medium">
        <Scissors class="size-4" /> New from text
      </div>
      <textarea
v-model="text" rows="5"
                placeholder="Paste a script or article — it's split into narration-sized segments."
                class="w-full resize-y rounded-md border bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-sky-400" />
      <div class="flex flex-wrap items-end gap-3">
        <label class="flex flex-col gap-1 text-xs text-muted-foreground">
          Title (optional)
          <input v-model="title" type="text" placeholder="Episode title"
                 class="w-48 rounded-md border bg-transparent px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-sky-400" >
        </label>
        <label class="flex flex-col gap-1 text-xs text-muted-foreground">
          Words / segment
          <input v-model.number="targetWords" type="number" min="8" max="120"
                 class="w-24 rounded-md border bg-transparent px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-sky-400" >
        </label>
        <button
type="button" :disabled="!canCreate"
                class="ml-auto flex items-center gap-1 rounded-md bg-fuchsia-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-fuchsia-600 disabled:opacity-50"
                @click="createFromText">
          <Loader2 v-if="creating" class="size-4 animate-spin" />
          <Scissors v-else class="size-4" /> Split into segments
        </button>
      </div>
      <p v-if="error" class="text-sm text-rose-500">{{ error }}</p>
    </div>

    <!-- episodes -->
    <div class="space-y-2">
      <h2 class="text-sm font-medium text-muted-foreground">Episodes</h2>
      <div v-if="loading" class="flex items-center gap-2 text-muted-foreground">
        <Loader2 class="size-4 animate-spin" /> Loading…
      </div>
      <p v-else-if="!episodes.length" class="text-sm text-muted-foreground">No episodes yet — paste some text above to start.</p>
      <div v-else class="divide-y rounded-xl border bg-background">
        <div v-for="ep in episodes" :key="ep.id" class="flex items-center justify-between gap-2 px-4 py-3">
          <NuxtLink :to="`/dashboard/studio/${ep.id}`" class="min-w-0 flex-1">
            <div class="truncate text-sm font-medium hover:text-sky-500">{{ ep.title }}</div>
            <div class="text-xs text-muted-foreground">{{ ep.segment_count }} segment{{ ep.segment_count === 1 ? '' : 's' }}</div>
          </NuxtLink>
          <button
type="button" title="Delete episode"
                  class="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-rose-500" @click="remove(ep)">
            <Trash2 class="size-4" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
