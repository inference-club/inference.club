<script setup lang="ts">
/**
 * Narration Studio editor: an episode's ordered segments, each with its take's
 * audio, word-synced transcript, quality grade, and Process / Redo actions.
 * Polls while any segment is still generating so results fill in live.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Loader2, Plus, Wand2, CheckCircle2 } from 'lucide-vue-next'
import SegmentCard from '@/components/studio/SegmentCard.vue'
import { useStudio, type Episode } from '@/composables/useStudio'

definePageMeta({ layout: 'app' })

const route = useRoute()
const studio = useStudio()
const id = Number(route.params.id)

const episode = ref<Episode | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const busy = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const segments = computed(() => episode.value?.segments || [])
const readyCount = computed(() => segments.value.filter((s) => s.status === 'ready').length)
const allReady = computed(() => segments.value.length > 0 && readyCount.value === segments.value.length)
const anyWorking = computed(() => segments.value.some((s) => s.status === 'generating'))

async function load() {
  try {
    episode.value = await studio.getEpisode(id)
    error.value = null
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load episode'
  } finally {
    loading.value = false
  }
}

async function addSegment() {
  busy.value = true
  try {
    await studio.addSegment(id, 'New line…')
    await load()
  } finally { busy.value = false }
}

async function processAll() {
  busy.value = true
  try {
    await Promise.all(
      segments.value.filter((s) => s.selected_variant_id || s.variants?.length).map((s) => studio.processSegment(s.id)),
    )
    await load()
  } finally { busy.value = false }
}

onMounted(() => {
  load()
  // Poll while anything is generating so takes/grades appear without a refresh.
  timer = setInterval(() => { if (anyWorking.value) load() }, 2500)
})
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-4 px-4 py-6">
    <NuxtLink to="/dashboard/studio" class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft class="size-4" /> Episodes
    </NuxtLink>

    <div v-if="loading" class="flex items-center gap-2 text-muted-foreground">
      <Loader2 class="size-4 animate-spin" /> Loading…
    </div>
    <p v-else-if="error" class="text-sm text-rose-500">{{ error }}</p>

    <template v-else-if="episode">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 class="text-xl font-semibold">{{ episode.title }}</h1>
          <p class="text-sm text-muted-foreground">
            <span :class="allReady ? 'text-emerald-600 dark:text-emerald-400' : ''">
              {{ readyCount }}/{{ segments.length }} ready
            </span>
            <span v-if="anyWorking"> · <Loader2 class="inline size-3 animate-spin" /> working…</span>
          </p>
        </div>
        <div class="flex items-center gap-2">
          <span v-if="allReady" class="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 class="size-3.5" /> All segments ready
          </span>
          <button
type="button" :disabled="busy || !segments.length"
                  class="flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-sm font-medium hover:bg-muted disabled:opacity-50"
                  title="Run the pipeline on every segment that has a take" @click="processAll">
            <Wand2 class="size-4" /> Process all
          </button>
        </div>
      </div>

      <div class="space-y-3">
        <SegmentCard v-for="s in segments" :key="s.id" :segment="s" @changed="load" />
      </div>

      <button
type="button" :disabled="busy"
              class="flex w-full items-center justify-center gap-1 rounded-lg border border-dashed py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
              @click="addSegment">
        <Plus class="size-4" /> Add a segment
      </button>
    </template>
  </div>
</template>
