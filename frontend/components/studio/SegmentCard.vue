<script setup lang="ts">
/**
 * One narration segment in the Studio editor: editable text, the selected
 * take's audio (original ↔ cleaned toggle) with word-synced highlighting, the
 * quality grade, take A/B selection, and Process / Redo actions that drive the
 * per-segment pipeline (clean → ASR → trim → grade).
 */
import { computed, ref, watch } from 'vue'
import { Loader2, RotateCcw, Wand2, CheckCircle2, AlertTriangle, Clock, Circle } from 'lucide-vue-next'
import { useStudio, type Segment, type Variant } from '@/composables/useStudio'

const props = defineProps<{ segment: Segment }>()
const emit = defineEmits<{ (e: 'changed', id: number): void }>()

const studio = useStudio()
const busy = ref(false)
const showCleaned = ref(true)
const text = ref(props.segment.text)
const currentTime = ref(0)

watch(() => props.segment.text, (t) => { text.value = t })

const variant = computed<Variant | null>(() => {
  const segs = props.segment.variants || []
  return segs.find((v) => v.id === props.segment.selected_variant_id) || segs[0] || null
})
const cleanedAvailable = computed(() => !!variant.value?.cleaned_audio_url)
const audioUrl = computed(() =>
  (showCleaned.value && cleanedAvailable.value
    ? variant.value?.cleaned_audio_url
    : variant.value?.audio_url) || null)
const words = computed(() => variant.value?.words || [])
const activeWord = computed(() =>
  words.value.findIndex((w) => currentTime.value >= w.start && currentTime.value < w.end))

const STATUS: Record<string, { label: string; cls: string; icon: unknown }> = {
  pending: { label: 'Pending', cls: 'bg-muted text-muted-foreground', icon: Circle },
  generating: { label: 'Working…', cls: 'bg-sky-500/15 text-sky-600 dark:text-sky-400', icon: Loader2 },
  ready: { label: 'Ready', cls: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400', icon: CheckCircle2 },
  flagged: { label: 'Flagged', cls: 'bg-amber-500/15 text-amber-600 dark:text-amber-400', icon: AlertTriangle },
  error: { label: 'Error', cls: 'bg-rose-500/15 text-rose-600 dark:text-rose-400', icon: Clock },
}
const st = computed(() => STATUS[props.segment.status] || STATUS.pending)
const grade = computed(() => variant.value?.grade || null)

async function saveText() {
  if (text.value.trim() === props.segment.text || !text.value.trim()) return
  busy.value = true
  try {
    await studio.updateSegment(props.segment.id, { text: text.value.trim() })
    emit('changed', props.segment.id)
  } finally { busy.value = false }
}

async function run(action: 'process' | 'regenerate') {
  busy.value = true
  try {
    if (action === 'process') await studio.processSegment(props.segment.id)
    else await studio.regenerateSegment(props.segment.id)
    emit('changed', props.segment.id)
  } finally { busy.value = false }
}

async function pick(v: Variant) {
  busy.value = true
  try {
    await studio.selectVariant(props.segment.id, v.id)
    emit('changed', props.segment.id)
  } finally { busy.value = false }
}

const onTime = (e: Event) => { currentTime.value = (e.target as HTMLAudioElement).currentTime }
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
          <component :is="st.icon" class="size-3" :class="segment.status === 'generating' ? 'animate-spin' : ''" />
          {{ st.label }}
        </span>
        <span v-if="grade" class="text-xs text-muted-foreground" :title="grade.reason">
          grade {{ grade.score.toFixed(1) }}/10
        </span>
        <span v-if="variant?.duration_seconds" class="text-xs text-muted-foreground">· {{ fmtDur(variant.duration_seconds) }}</span>
      </div>
      <div class="flex items-center gap-1">
        <button
type="button" :disabled="busy" title="Run the pipeline on this take"
                class="flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium hover:bg-muted disabled:opacity-50"
                @click="run('process')">
          <Wand2 class="size-3" /> Process
        </button>
        <button
type="button" :disabled="busy" title="Generate a fresh take, then process it"
                class="flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium hover:bg-muted disabled:opacity-50"
                @click="run('regenerate')">
          <RotateCcw class="size-3" /> Redo
        </button>
      </div>
    </div>

    <div class="space-y-2 px-3 py-2">
      <!-- editable text -->
      <textarea
v-model="text" rows="2" :disabled="busy"
                class="w-full resize-y rounded-md border bg-transparent px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-sky-400"
                @blur="saveText" />

      <!-- flagged reason -->
      <p v-if="segment.status === 'flagged' && grade" class="text-xs text-amber-600 dark:text-amber-400">
        {{ grade.reason }}
      </p>

      <!-- player + cleaned toggle -->
      <div v-if="audioUrl" class="space-y-1.5">
        <div class="flex items-center gap-2">
          <audio :src="audioUrl" controls preload="metadata" class="h-8 w-full" @timeupdate="onTime" />
          <button
v-if="cleanedAvailable" type="button"
                  class="shrink-0 rounded-md border px-2 py-1 text-[11px] font-medium hover:bg-muted"
                  :class="showCleaned ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'"
                  @click="showCleaned = !showCleaned">
            {{ showCleaned ? 'Cleaned' : 'Original' }}
          </button>
        </div>
        <!-- word-synced transcript -->
        <p v-if="words.length" class="flex flex-wrap gap-x-1 text-xs leading-relaxed">
          <span
v-for="(w, i) in words" :key="i"
                class="rounded px-0.5"
                :class="i === activeWord ? 'bg-sky-400/30 text-foreground' : 'text-muted-foreground'">
            {{ w.word }}
          </span>
        </p>
      </div>
      <p v-else class="text-xs text-muted-foreground">No take yet — press <b>Redo</b> to generate one.</p>

      <!-- take A/B -->
      <div v-if="(segment.variants?.length || 0) > 1" class="flex flex-wrap items-center gap-1 pt-1">
        <span class="text-[11px] text-muted-foreground">Takes:</span>
        <button
v-for="(v, i) in segment.variants" :key="v.id" type="button" :disabled="busy"
                class="rounded-md border px-1.5 py-0.5 text-[11px] hover:bg-muted disabled:opacity-50"
                :class="v.id === segment.selected_variant_id ? 'border-sky-400 text-sky-600 dark:text-sky-400' : ''"
                @click="pick(v)">
          {{ segment.variants.length - i }}<span v-if="v.grade"> · {{ v.grade.score.toFixed(0) }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
