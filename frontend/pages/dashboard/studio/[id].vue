<script setup lang="ts">
/**
 * Narration Studio editor: an episode's ordered segments, each with its take's
 * audio, word-synced transcript, quality grade, and Process / Redo actions.
 * Polls while any segment is still generating so results fill in live.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Loader2, Mic, Plus, Wand2, CheckCircle2 } from 'lucide-vue-next'
import SegmentCard from '@/components/studio/SegmentCard.vue'
import EpisodeTimeline from '@/components/studio/EpisodeTimeline.vue'
import { useStudio, type Episode, type StudioVoices } from '@/composables/useStudio'

definePageMeta({ layout: 'app' })

const route = useRoute()
const studio = useStudio()
const id = Number(route.params.id)

const episode = ref<Episode | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const busy = ref(false)
const voices = ref<StudioVoices | null>(null)
const savingVoice = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const voiceOptions = computed(() => voices.value?.voices || [])
const sampleOptions = computed(() => (voices.value?.samples || []).filter((s) => s.has_transcript))
const selectedVoiceModel = computed(() => episode.value?.voice_model || '')
// No explicit model → the backend auto-picks a voice-cloning model (Dia).
const cloningSelected = computed(() => {
  const m = selectedVoiceModel.value
  if (!m) return true
  const opt = voiceOptions.value.find((v) => v.model === m)
  return opt ? opt.voice_cloning : true
})
const noVoiceService = computed(() => !!voices.value && voiceOptions.value.length === 0)

async function loadVoices() {
  try { voices.value = await studio.listVoices() } catch { voices.value = { voices: [], samples: [] } }
}

async function setVoiceModel(e: Event) {
  const model = (e.target as HTMLSelectElement).value
  savingVoice.value = true
  try {
    const ep = await studio.updateEpisode(id, { voice_model: model })
    if (episode.value) Object.assign(episode.value, {
      voice_model: ep.voice_model, voice_sample_id: ep.voice_sample_id, voice_sample_name: ep.voice_sample_name,
    })
  } finally { savingVoice.value = false }
}

async function setVoiceSample(e: Event) {
  const v = (e.target as HTMLSelectElement).value
  savingVoice.value = true
  try {
    const ep = await studio.updateEpisode(id, { voice_sample_id: v ? Number(v) : null })
    if (episode.value) Object.assign(episode.value, {
      voice_sample_id: ep.voice_sample_id, voice_sample_name: ep.voice_sample_name,
    })
  } finally { savingVoice.value = false }
}

const segments = computed(() => episode.value?.segments || [])
const readyCount = computed(() => segments.value.filter((s) => s.status === 'ready').length)
const allReady = computed(() => segments.value.length > 0 && readyCount.value === segments.value.length)
const queuedCount = computed(() => segments.value.filter((s) => s.status === 'queued').length)
const generatingCount = computed(() => segments.value.filter((s) => s.status === 'generating').length)
// Keep polling while anything is queued or generating so statuses advance live.
const anyWorking = computed(() => queuedCount.value > 0 || generatingCount.value > 0)
// Segments that still need a voice take generated (fresh from a text split).
const needTake = computed(() => segments.value.filter((s) => !(s.variants && s.variants.length)))
const hasAnyTake = computed(() => segments.value.some((s) => s.variants?.length))

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

async function generateAll() {
  busy.value = true
  try {
    await Promise.all(needTake.value.map((s) => studio.regenerateSegment(s.id)))
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
  loadVoices()
  // Poll while anything is generating so takes/grades appear without a refresh.
  timer = setInterval(() => { if (anyWorking.value) load() }, 2500)
})
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-4 px-4 py-6">
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
            <span v-if="generatingCount"> · <Loader2 class="inline size-3 animate-spin" /> generating…</span>
            <span v-if="queuedCount"> · {{ queuedCount }} queued</span>
          </p>
        </div>
        <div class="flex items-center gap-2">
          <span v-if="allReady" class="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 class="size-3.5" /> All segments ready
          </span>
          <button
            type="button" :disabled="busy || !needTake.length"
            class="flex items-center gap-1 rounded-md bg-fuchsia-500 px-2.5 py-1.5 text-sm font-medium text-white hover:bg-fuchsia-600 disabled:opacity-50"
            :title="needTake.length ? `Generate the voice take for ${needTake.length} segment(s) that don't have one yet` : 'Every segment already has a take'"
            @click="generateAll">
            <Mic class="size-4" /> Generate all<span v-if="needTake.length"> ({{ needTake.length }})</span>
          </button>
          <button
            type="button" :disabled="busy || !hasAnyTake"
            class="flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-sm font-medium hover:bg-muted disabled:opacity-50"
            title="Re-run clean → trim → grade on every segment that has a take" @click="processAll">
            <Wand2 class="size-4" /> Process all
          </button>
        </div>
      </div>

      <!-- voice picker (applies to every take you generate in this episode) -->
      <div class="flex flex-wrap items-center gap-3 rounded-xl border bg-background px-3 py-2.5 text-sm">
        <span class="flex items-center gap-1.5 font-medium"><Mic class="size-4 text-fuchsia-500" /> Voice</span>
        <p v-if="noVoiceService" class="text-xs text-amber-600 dark:text-amber-400">
          No voice service is online — start a TTS/Dia deployment to generate takes.
        </p>
        <template v-else>
          <label class="flex items-center gap-1.5 text-xs text-muted-foreground">
            Model
            <select :value="selectedVoiceModel" :disabled="savingVoice"
                    class="rounded-md border bg-transparent px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-sky-400"
                    @change="setVoiceModel">
              <option value="">Auto (voice cloning)</option>
              <option v-for="v in voiceOptions" :key="v.model" :value="v.model">
                {{ v.label }}{{ v.voice_cloning ? ' · clone' : '' }}
              </option>
            </select>
          </label>
          <label v-if="cloningSelected" class="flex items-center gap-1.5 text-xs text-muted-foreground">
            Sample
            <select :value="episode.voice_sample_id ?? ''" :disabled="savingVoice"
                    class="rounded-md border bg-transparent px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-sky-400"
                    @change="setVoiceSample">
              <option value="">Default (no clone)</option>
              <option v-for="s in sampleOptions" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </label>
          <span v-if="cloningSelected && !sampleOptions.length" class="text-xs text-muted-foreground">
            No voice samples yet — clone one in Voice Cloning to speak in your own voice.
          </span>
          <Loader2 v-if="savingVoice" class="size-3.5 animate-spin text-muted-foreground" />
        </template>
      </div>

      <!-- whole-episode preview timeline -->
      <EpisodeTimeline :segments="segments" />

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
