<script setup lang="ts">
/**
 * One narration segment in the Studio editor: editable text, a bespoke waveform
 * player/trim editor over the StudioVoice-cleaned audio (showing exactly which
 * sections were clipped, draggable to re-cut), the quality grade, take A/B, and
 * the Process / Redo pipeline actions (clean → ASR → trim → grade).
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  AlertTriangle, CheckCircle2, Circle, Clock, Hourglass, Loader2,
  Mic, Plus, RotateCcw, Scissors, Wand2,
} from 'lucide-vue-next'
import WaveformEditor from '@/components/studio/WaveformEditor.vue'
import { useStudio, type Segment, type Variant, type Word } from '@/composables/useStudio'

interface Region { start: number; end: number }

const props = defineProps<{ segment: Segment }>()
const emit = defineEmits<{ (e: 'changed', id: number): void }>()

const studio = useStudio()
const busy = ref(false)
// Text saves on blur; kept separate from `busy` so an in-flight save (triggered
// by the blur when you click Apply) never disables the action buttons mid-click.
const savingText = ref(false)
const err = ref<string | null>(null)
const applied = ref(false)
const text = ref(props.segment.text)
const playTime = ref(0)
// 'result' shows the trimmed audio you'll use; 'original' shows the full take
// with the removed sections marked and editable.
const mode = ref<'result' | 'original'>('result')
const editorRef = ref<InstanceType<typeof WaveformEditor> | null>(null)
let appliedTimer: ReturnType<typeof setTimeout> | null = null
onBeforeUnmount(() => { if (appliedTimer) clearTimeout(appliedTimer) })

function addCut() {
  const dur = mode.value === 'result' ? resultDur.value : fullDuration.value
  const at = playTime.value > 0 ? playTime.value : Math.max(0, dur / 2 - 0.2)
  editorRef.value?.addRegionAt(at)
}

watch(() => props.segment.text, (t) => { text.value = t })

const variant = computed<Variant | null>(() => {
  const vs = props.segment.variants || []
  return vs.find((v) => v.id === props.segment.selected_variant_id) || vs[0] || null
})
// Process re-runs the pipeline on an existing take; until one is generated there
// is nothing to process, so the action is gated on a take being present.
const hasTake = computed(() => !!variant.value?.audio_url)

function describeError(e: unknown): string {
  const data = (e as { data?: { detail?: string } })?.data
  return data?.detail || (e instanceof Error ? e.message : 'Something went wrong')
}

// Three takes per variant: the trimmed result (default view — what you'll use),
// the full StudioVoice-cleaned source the cuts are marked/edited on, and the raw
// take as a final fallback before processing.
const resultSrc = computed(() => variant.value?.cleaned_audio_url || variant.value?.audio_url || null)
const originalSrc = computed(() => variant.value?.enhanced_audio_url || null)
const canTrim = computed(() => !!variant.value?.enhanced_audio_url)
const hasAudio = computed(() => !!resultSrc.value)
const fullDuration = computed(() =>
  variant.value?.enhanced_duration || variant.value?.duration_seconds || 0)  // untrimmed source
const resultDur = computed(() => variant.value?.duration_seconds || 0)        // trimmed output

// Transcript follows whatever audio is on screen (each has its own timeline).
const words = computed<Word[]>(() => {
  if (mode.value === 'original' && variant.value?.enhanced_words?.length) return variant.value.enhanced_words
  return variant.value?.words || []
})
const activeWord = computed(() =>
  words.value.findIndex((w) => playTime.value >= w.start && playTime.value < w.end))

// Saved removed regions = the gaps between the kept intervals (on the full take).
function removedFromKeep(keep: [number, number][], total: number): Region[] {
  const res: Region[] = []
  let cursor = 0
  for (const [a, b] of [...keep].sort((x, y) => x[0] - y[0])) {
    if (a - cursor > 0.03) res.push({ start: cursor, end: a })
    cursor = Math.max(cursor, b)
  }
  if (total - cursor > 0.03) res.push({ start: cursor, end: total })
  return res
}
const savedRegions = computed<Region[]>(() => {
  const keep = variant.value?.trim_intervals || []
  if (!keep.length || !fullDuration.value) return []
  return removedFromKeep(keep, fullDuration.value)
})
const regions = ref<Region[]>([])
function resetRegions() { regions.value = savedRegions.value.map((r) => ({ ...r })) }
watch(() => variant.value?.id, resetRegions, { immediate: true })
watch(savedRegions, (s) => { if (!dirty.value) regions.value = s.map((r) => ({ ...r })) })
// Nothing to edit (not processed) → stay on the result view.
watch(canTrim, (c) => { if (!c) mode.value = 'result' }, { immediate: true })

const round = (n: number) => Math.round(n * 100) / 100
const dirty = computed(() => {
  const a = regions.value, b = savedRegions.value
  if (a.length !== b.length) return true
  return a.some((r, i) => round(r.start) !== round(b[i].start) || round(r.end) !== round(b[i].end))
})
const removedSeconds = computed(() => regions.value.reduce((s, r) => s + Math.max(0, r.end - r.start), 0))
// What the trimmed clip will run to once applied (for the "1.4s → 0.9s" hint).
const resultDuration = computed(() => Math.max(0, fullDuration.value - removedSeconds.value))

// --- editing directly on the RESULT view -------------------------------------
// Cuts dragged on the (already-trimmed) result are in the trimmed timeline; we
// map them back onto the full take via the kept intervals and merge with the
// existing trim, so you can keep shaving the clip with zero mode-switching.
const pendingCuts = ref<Region[]>([])
const keepIntervals = computed<[number, number][]>(() => {
  const k = (variant.value?.trim_intervals || []) as [number, number][]
  if (k.length) return [...k].sort((a, b) => a[0] - b[0])
  return fullDuration.value ? [[0, fullDuration.value]] : []
})
function resultToFull(tr: number): number {
  let cum = 0
  for (const [a, b] of keepIntervals.value) {
    const span = b - a
    if (tr <= cum + span + 1e-6) return a + (tr - cum)
    cum += span
  }
  const last = keepIntervals.value[keepIntervals.value.length - 1]
  return last ? last[1] : tr
}
const pendingRemoved = computed(() => pendingCuts.value.reduce((s, r) => s + Math.max(0, r.end - r.start), 0))
const resultLiveDuration = computed(() => Math.max(0, resultDur.value - pendingRemoved.value))
const dirtyResult = computed(() => pendingCuts.value.length > 0)

async function applyResultCuts() {
  if (!pendingCuts.value.length) return
  busy.value = true; err.value = null
  try {
    const mapped = pendingCuts.value.map((r) =>
      [round(resultToFull(Math.min(r.start, r.end))), round(resultToFull(Math.max(r.start, r.end)))] as [number, number])
    const removes = savedRegions.value
      .map((r) => [round(r.start), round(r.end)] as [number, number])
      .concat(mapped)
    await studio.retrimSegment(props.segment.id, removes)
    pendingCuts.value = []
    applied.value = true
    if (appliedTimer) clearTimeout(appliedTimer)
    appliedTimer = setTimeout(() => { applied.value = false }, 2800)
    emit('changed', props.segment.id)
  } catch (e) { err.value = describeError(e) } finally { busy.value = false }
}

// Switching views discards unapplied edits (each view edits its own timeline).
watch(mode, () => { pendingCuts.value = []; resetRegions() })

const STATUS: Record<string, { label: string; cls: string; icon: unknown }> = {
  pending: { label: 'Pending', cls: 'bg-muted text-muted-foreground', icon: Circle },
  queued: { label: 'Queued', cls: 'bg-muted text-muted-foreground', icon: Hourglass },
  generating: { label: 'Working…', cls: 'bg-sky-500/15 text-sky-600 dark:text-sky-400', icon: Loader2 },
  ready: { label: 'Ready', cls: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400', icon: CheckCircle2 },
  flagged: { label: 'Flagged', cls: 'bg-amber-500/15 text-amber-600 dark:text-amber-400', icon: AlertTriangle },
  error: { label: 'Error', cls: 'bg-rose-500/15 text-rose-600 dark:text-rose-400', icon: Clock },
}
const st = computed(() => STATUS[props.segment.status] || STATUS.pending)
const grade = computed(() => variant.value?.grade || null)

async function saveText() {
  if (text.value.trim() === props.segment.text || !text.value.trim()) return
  savingText.value = true; err.value = null
  try {
    await studio.updateSegment(props.segment.id, { text: text.value.trim() })
    emit('changed', props.segment.id)
  } catch (e) { err.value = describeError(e) } finally { savingText.value = false }
}

async function run(action: 'process' | 'regenerate') {
  busy.value = true; err.value = null
  try {
    if (action === 'process') await studio.processSegment(props.segment.id)
    else await studio.regenerateSegment(props.segment.id)
    emit('changed', props.segment.id)
  } catch (e) { err.value = describeError(e) } finally { busy.value = false }
}

async function applyTrim() {
  busy.value = true; err.value = null
  try {
    await studio.retrimSegment(props.segment.id, regions.value.map((r) => [round(r.start), round(r.end)] as [number, number]))
    mode.value = 'result'  // jump to the freshly trimmed result
    applied.value = true
    if (appliedTimer) clearTimeout(appliedTimer)
    appliedTimer = setTimeout(() => { applied.value = false }, 2800)
    emit('changed', props.segment.id)
  } catch (e) { err.value = describeError(e) } finally { busy.value = false }
}

async function pick(v: Variant) {
  busy.value = true; err.value = null
  try {
    await studio.selectVariant(props.segment.id, v.id)
    emit('changed', props.segment.id)
  } catch (e) { err.value = describeError(e) } finally { busy.value = false }
}

const fmtDur = (s: number | null | undefined) => (s ? `${s.toFixed(1)}s` : '')
</script>

<template>
  <div class="rounded-xl border bg-background">
    <!-- header -->
    <div class="flex items-center justify-between gap-2 border-b px-3 py-2">
      <div class="flex items-center gap-2 text-sm">
        <span class="grid size-6 place-items-center rounded-md bg-muted text-xs font-semibold text-muted-foreground">
          {{ segment.position + 1 }}
        </span>
        <span class="flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium" :class="st.cls">
          <component :is="st.icon" class="size-3" :class="segment.status === 'generating' ? 'animate-spin' : segment.status === 'queued' ? 'animate-pulse' : ''" />
          {{ st.label }}
        </span>
        <span v-if="grade" class="text-xs text-muted-foreground" :title="grade.reason">
          grade {{ grade.score.toFixed(1) }}/10
        </span>
        <span v-if="variant?.duration_seconds" class="text-xs text-muted-foreground">· {{ fmtDur(variant.duration_seconds) }}</span>
      </div>
      <div class="flex items-center gap-1">
        <!-- primary: make the voice take (and auto-process it) -->
        <button
          type="button" :disabled="busy"
          :title="hasTake ? 'Generate a fresh take with Dia, then process it' : 'Generate the audio take with Dia'"
          class="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
          :class="hasTake ? 'bg-muted-foreground/80' : 'bg-fuchsia-500 hover:bg-fuchsia-600'"
          @click="run('regenerate')"
        >
          <component :is="hasTake ? RotateCcw : Mic" class="size-3" /> {{ hasTake ? 'Redo' : 'Generate' }}
        </button>
        <!-- secondary: re-run clean → trim → grade on the existing take -->
        <button
          type="button" :disabled="busy || !hasTake"
          :title="hasTake ? 'Re-run clean → transcribe → trim → grade on this take' : 'Generate a take first'"
          class="flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium hover:bg-muted disabled:opacity-50"
          @click="run('process')"
        >
          <Wand2 class="size-3" /> Process
        </button>
      </div>
    </div>

    <div class="space-y-2.5 px-3 py-2.5">
      <!-- editable text -->
      <textarea
        v-model="text" rows="2" :disabled="busy"
        class="w-full resize-y rounded-md border bg-transparent px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-sky-400"
        @blur="saveText"
      />

      <!-- flagged reason -->
      <p v-if="segment.status === 'flagged' && grade" class="text-xs text-amber-600 dark:text-amber-400">
        {{ grade.reason }}
      </p>

      <!-- action error -->
      <p v-if="err" class="text-xs text-rose-500">{{ err }}</p>

      <!-- waveform: trimmed result by default, editable source ("Original") on demand -->
      <template v-if="hasAudio">
        <!-- mode toggle + applied confirmation -->
        <div class="flex items-center gap-2">
          <div v-if="canTrim" class="inline-flex items-center rounded-lg border p-0.5 text-xs">
            <button
              type="button" class="rounded-md px-2.5 py-1 font-medium transition-colors"
              :class="mode === 'result' ? 'bg-fuchsia-500 text-white' : 'text-muted-foreground hover:text-foreground'"
              @click="mode = 'result'"
            >
              Result
            </button>
            <button
              type="button" class="rounded-md px-2.5 py-1 font-medium transition-colors"
              :class="mode === 'original' ? 'bg-fuchsia-500 text-white' : 'text-muted-foreground hover:text-foreground'"
              @click="mode = 'original'"
            >
              Original
            </button>
          </div>
          <span class="text-xs text-muted-foreground">
            {{ mode === 'original' ? 'Full take — drag to adjust or restore cuts' : 'Result — drag to trim more' }}
          </span>
          <span
            v-if="applied"
            class="ml-auto flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400"
          >
            <CheckCircle2 class="size-3.5" /> Trim applied
          </span>
        </div>

        <!-- RESULT: the trimmed audio — drag directly on it to trim more -->
        <WaveformEditor
          v-if="mode === 'result'"
          ref="editorRef"
          :key="`res-${variant?.cleaned_audio_url || variant?.audio_url || ''}`"
          :src="resultSrc" v-model="pendingCuts" :duration="resultDur" :readonly="busy || !canTrim"
          @time="playTime = $event"
        />
        <!-- ORIGINAL: full take with every cut (adjust or restore removed bits) -->
        <WaveformEditor
          v-else
          ref="editorRef"
          :src="originalSrc" v-model="regions" :duration="fullDuration" :readonly="busy"
          @time="playTime = $event"
        />

        <!-- RESULT controls: drag right on the result to trim more -->
        <div v-if="mode === 'result' && canTrim" class="flex flex-wrap items-center gap-2 text-xs">
          <span v-if="dirtyResult" class="text-muted-foreground">
            {{ pendingCuts.length }} new cut{{ pendingCuts.length === 1 ? '' : 's' }} ·
            {{ fmtDur(resultDur) }} → {{ resultLiveDuration.toFixed(1) }}s
            <span class="text-rose-500">(−{{ pendingRemoved.toFixed(1) }}s)</span>
          </span>
          <span v-else class="text-muted-foreground">
            {{ fmtDur(resultDur) }}
            <template v-if="savedRegions.length"> · {{ savedRegions.length }} cut{{ savedRegions.length === 1 ? '' : 's' }} removed</template>
            — drag on the result to trim more
          </span>
          <button
            type="button" :disabled="busy"
            class="flex items-center gap-1 rounded-md border px-2 py-1 font-medium hover:bg-muted disabled:opacity-40"
            title="Add a cut at the playhead, then drag its edges to fit" @click="addCut"
          >
            <Plus class="size-3" /> Add cut
          </button>
          <button
            type="button" :disabled="busy || !dirtyResult"
            class="ml-auto flex items-center gap-1 rounded-md bg-fuchsia-500 px-2.5 py-1 font-medium text-white hover:bg-fuchsia-600 disabled:opacity-40"
            @click="applyResultCuts"
          >
            <Scissors class="size-3" /> Apply trim
          </button>
          <button
            type="button" :disabled="busy || !dirtyResult"
            class="flex items-center gap-1 rounded-md border px-2 py-1 font-medium hover:bg-muted disabled:opacity-40"
            title="Discard unapplied cuts" @click="pendingCuts = []"
          >
            <RotateCcw class="size-3" /> Cancel
          </button>
        </div>

        <!-- not processed yet -->
        <p v-else-if="mode === 'result' && !canTrim" class="text-xs text-muted-foreground">
          Press <b>Process</b> to clean and analyse this take — then you can trim it here.
        </p>

        <!-- ORIGINAL trim actions (full take) -->
        <div v-else class="flex flex-wrap items-center gap-2 text-xs">
          <span v-if="dirty" class="text-muted-foreground">
            {{ regions.length }} cut{{ regions.length === 1 ? '' : 's' }} ·
            {{ fullDuration.toFixed(1) }}s → {{ resultDuration.toFixed(1) }}s
            <span class="text-rose-500">(−{{ removedSeconds.toFixed(1) }}s)</span>
          </span>
          <span v-else class="text-muted-foreground">
            <template v-if="regions.length">{{ regions.length }} cut{{ regions.length === 1 ? '' : 's' }} · drag, add, or double-click to delete</template>
            <template v-else>Drag on the waveform (either direction) to remove a section</template>
          </span>
          <button
            type="button" :disabled="busy"
            class="flex items-center gap-1 rounded-md border px-2 py-1 font-medium hover:bg-muted disabled:opacity-40"
            title="Add a cut at the playhead, then drag its edges to fit" @click="addCut"
          >
            <Plus class="size-3" /> Add cut
          </button>
          <button
            type="button" :disabled="busy || !dirty"
            class="ml-auto flex items-center gap-1 rounded-md bg-fuchsia-500 px-2.5 py-1 font-medium text-white hover:bg-fuchsia-600 disabled:opacity-40"
            @click="applyTrim"
          >
            <Scissors class="size-3" /> Apply trim
          </button>
          <button
            type="button" :disabled="busy || !dirty"
            class="flex items-center gap-1 rounded-md border px-2 py-1 font-medium hover:bg-muted disabled:opacity-40"
            title="Discard unapplied edits" @click="resetRegions"
          >
            <RotateCcw class="size-3" /> Cancel
          </button>
        </div>

        <!-- word-synced transcript (follows the audio on screen) -->
        <p v-if="words.length" class="flex flex-wrap gap-x-1 text-xs leading-relaxed">
          <span
            v-for="(w, i) in words" :key="i"
            class="rounded px-0.5"
            :class="i === activeWord ? 'bg-sky-400/30 text-foreground' : 'text-muted-foreground'"
          >
            {{ w.word }}
          </span>
        </p>
      </template>
      <p v-else class="text-xs text-muted-foreground">No take yet — press <b>{{ hasTake ? 'Redo' : 'Generate' }}</b> to create one.</p>

      <!-- take A/B -->
      <div v-if="(segment.variants?.length || 0) > 1" class="flex flex-wrap items-center gap-1 pt-1">
        <span class="text-[11px] text-muted-foreground">Takes:</span>
        <button
          v-for="(v, i) in segment.variants" :key="v.id" type="button" :disabled="busy"
          class="rounded-md border px-1.5 py-0.5 text-[11px] hover:bg-muted disabled:opacity-50"
          :class="v.id === segment.selected_variant_id ? 'border-sky-400 text-sky-600 dark:text-sky-400' : ''"
          @click="pick(v)"
        >
          {{ segment.variants.length - i }}<span v-if="v.grade"> · {{ v.grade.score.toFixed(0) }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
