<script setup lang="ts">
// One piece of a narration: the line, how it turned out, and the fixes a
// listener can ask for without opening the Studio: voice it again, reword
// it, leave a note (typed or spoken), or switch to another take.
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  Check, ChevronDown, CircleAlert, Clock, Loader2, Mic, Play, RefreshCw, Send, Square, TriangleAlert, X,
} from 'lucide-vue-next'
import type { Segment } from '@/composables/useStudio'
import { useNarration, clock } from '@/composables/useNarration'
import { useAudioRecorder } from '@/composables/useAudioRecorder'

const props = defineProps<{
  segment: Segment
  index: number
  kind?: string
  /** This piece is the one playing in the main player. */
  playing?: boolean
  /** The main player can jump to this piece. */
  seekable?: boolean
  /** Seconds into this piece, while it is the one playing. */
  time?: number | null
}>()
const emit = defineEmits<{ (e: 'play' | 'changed'): void }>()

const { t } = useI18n()
const api = useNarration()
const recorder = useAudioRecorder()

const open = ref(false)
const busy = ref(false)
const text = ref(props.segment.text)
const note = ref('')
const transcribing = ref(false)
watch(() => props.segment.text, (v) => { if (!open.value) text.value = v })

const take = computed(() => props.segment.variants.find((v) => v.id === props.segment.selected_variant_id) ?? null)
const working = computed(() => ['queued', 'generating'].includes(props.segment.status))
const score = computed(() => take.value?.grade?.take_score ?? take.value?.grade?.score ?? null)
const clip = computed(() => take.value?.cleaned_audio_url || take.value?.audio_url || '')
// While this piece plays, show the words as they were heard, lit up in time.
// The timings come from speech recognition of this take, carried through
// every cut, so this is also a check that the cuts kept them aligned.
const spoken = computed(() => (props.playing && props.time != null && take.value?.words?.length ? take.value.words : null))
const wordAt = computed(() => {
  const w = spoken.value
  if (!w || props.time == null) return -1
  let at = -1
  for (let i = 0; i < w.length; i++) if (w[i].start <= props.time + 0.03) at = i
  return at
})
const takes = computed(() => [...props.segment.variants].sort((a, b) => (b.grade?.take_score ?? 0) - (a.grade?.take_score ?? 0)))

const run = async (fn: () => Promise<unknown>, done?: string) => {
  if (busy.value) return
  busy.value = true
  try {
    await fn()
    if (done) toast.success(done)
    emit('changed')
  } catch {
    toast.error(t('narrate.piece.failed'))
  } finally {
    busy.value = false
  }
}
const revoice = () => run(() => api.revoice(props.segment.id), t('narrate.piece.revoicing'))
const saveText = () =>
  run(async () => {
    await api.reword(props.segment.id, text.value.trim())
    await api.revoice(props.segment.id)
  }, t('narrate.piece.revoicing'))
const sendNote = () =>
  run(async () => {
    const res = await api.feedback(props.segment.id, note.value.trim())
    note.value = ''
    toast.success(res.understood.summary)
  })
const choose = (id: number) => run(() => api.chooseTake(props.segment.id, id))

// Voice note: record, transcribe, drop the words into the note box to send.
const toggleRecord = async () => {
  if (recorder.recording.value) {
    recorder.stop()
    return
  }
  try {
    const audio = await recorder.start()
    transcribing.value = true
    const heard = await api.transcribe(audio.blob, audio.ext)
    if (heard) note.value = note.value ? `${note.value} ${heard}` : heard
    else toast.error(t('narrate.piece.notHeard'))
  } catch {
    toast.error(t('narrate.piece.micDenied'))
  } finally {
    transcribing.value = false
  }
}

const play = () => {
  if (props.seekable) emit('play')
  else if (clip.value) new Audio(clip.value).play().catch(() => {})
}
</script>

<template>
  <li
    class="rounded-xl border transition-colors"
    :class="[playing ? 'border-primary/60 bg-primary/5' : 'bg-card', kind === 'heading' ? 'font-semibold' : '']"
    :data-testid="`piece-${index}`"
    :data-status="segment.status"
  >
    <div class="flex min-w-0 items-start gap-2 p-2.5 sm:gap-3 sm:p-3">
      <button
        type="button"
        class="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full border text-muted-foreground transition-colors enabled:hover:border-primary enabled:hover:text-primary disabled:opacity-60"
        :disabled="!clip"
        :aria-label="t('narrate.piece.play', { n: index + 1 })"
        @click="play"
      >
        <Loader2 v-if="segment.status === 'generating'" class="size-4 animate-spin text-primary" />
        <Clock v-else-if="segment.status === 'queued' || (segment.status === 'pending' && !clip)" class="size-4" />
        <X v-else-if="segment.status === 'error' && !clip" class="size-4 text-destructive" />
        <Play v-else class="size-3.5 translate-x-px" />
      </button>

      <button type="button" class="min-w-0 flex-1 text-left" :aria-expanded="open" @click="open = !open">
        <p v-if="spoken" class="break-words text-sm leading-relaxed" data-testid="piece-words">
          <span
            v-for="(w, i) in spoken"
            :key="i"
            class="rounded-sm transition-colors duration-75"
            :class="i === wordAt ? 'bg-primary text-primary-foreground' : i < wordAt ? '' : 'text-muted-foreground'"
          >{{ w.word }}{{ ' ' }}</span>
        </p>
        <p v-else class="break-words text-sm leading-relaxed" :class="!clip && !working ? 'text-muted-foreground' : ''">
          {{ segment.text }}
        </p>
        <p class="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px] font-normal text-muted-foreground">
          <span class="font-mono">{{ index + 1 }}</span>
          <span v-if="segment.status === 'generating'" class="text-primary">{{ t('narrate.piece.status.generating') }}</span>
          <span v-else-if="segment.status === 'queued'">{{ t('narrate.piece.status.queued') }}</span>
          <span v-else-if="segment.status === 'ready'" class="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
            <Check class="size-3" /> {{ t('narrate.piece.status.ready') }}
          </span>
          <span v-else-if="segment.status === 'flagged'" class="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
            <TriangleAlert class="size-3" /> {{ t('narrate.piece.status.flagged') }}
          </span>
          <span v-else-if="segment.status === 'error'" class="inline-flex items-center gap-1 text-destructive">
            <CircleAlert class="size-3" /> {{ t('narrate.piece.status.error') }}
          </span>
          <span v-if="take?.duration_seconds">{{ clock(take.duration_seconds) }}</span>
          <span v-if="score != null" :title="take?.grade?.reason">{{ t('narrate.piece.score', { n: score.toFixed(1) }) }}</span>
          <span v-if="take?.grade?.tail_cut" :title="t('narrate.piece.tailCutHint')">{{ t('narrate.piece.tailCut', { n: take.grade.tail_cut.toFixed(1) }) }}</span>
          <span v-if="segment.variants.length > 1">{{ t('narrate.piece.takes', { n: segment.variants.length }, segment.variants.length) }}</span>
        </p>
      </button>
      <ChevronDown class="mt-1.5 size-4 shrink-0 text-muted-foreground transition-transform" :class="open ? 'rotate-180' : ''" />
    </div>

    <!-- Fixes -->
    <div v-if="open" class="space-y-3 border-t p-3 font-normal">
      <p v-if="take?.grade?.reason && segment.status === 'flagged'" class="text-xs text-amber-600 dark:text-amber-400">
        {{ take.grade.reason }}
      </p>
      <div>
        <label :for="`piece-text-${segment.id}`" class="mb-1 block text-xs font-medium text-muted-foreground">{{ t('narrate.piece.words') }}</label>
        <textarea
          :id="`piece-text-${segment.id}`"
          v-model="text"
          rows="3"
          class="block w-full rounded-lg border bg-background p-2 text-sm"
        />
        <div class="mt-2 flex flex-wrap gap-2">
          <Button v-if="text.trim() !== segment.text" size="sm" class="gap-1.5" :disabled="busy || working || !text.trim()" @click="saveText">
            <Check class="size-3.5" /> {{ t('narrate.piece.saveAndVoice') }}
          </Button>
          <Button size="sm" variant="outline" class="gap-1.5" :disabled="busy || working" data-testid="piece-revoice" @click="revoice">
            <RefreshCw class="size-3.5" :class="working ? 'animate-spin' : ''" /> {{ t('narrate.piece.revoice') }}
          </Button>
        </div>
      </div>

      <div>
        <label :for="`piece-note-${segment.id}`" class="mb-1 block text-xs font-medium text-muted-foreground">{{ t('narrate.piece.noteLabel') }}</label>
        <div class="flex min-w-0 items-center gap-2">
          <input
            :id="`piece-note-${segment.id}`"
            v-model="note"
            class="h-9 min-w-0 flex-1 rounded-lg border bg-background px-2.5 text-sm"
            :placeholder="t('narrate.piece.notePlaceholder')"
            @keydown.enter.prevent="note.trim() && sendNote()"
          />
          <Button
            v-if="recorder.supported.value"
            size="icon"
            variant="outline"
            class="size-9 shrink-0"
            :class="recorder.recording.value ? 'border-destructive text-destructive' : ''"
            :disabled="transcribing"
            :aria-label="recorder.recording.value ? t('narrate.piece.stopRecording') : t('narrate.piece.record')"
            :title="recorder.recording.value ? t('narrate.piece.stopRecording') : t('narrate.piece.record')"
            @click="toggleRecord"
          >
            <Loader2 v-if="transcribing" class="size-4 animate-spin" />
            <Square v-else-if="recorder.recording.value" class="size-3.5" />
            <Mic v-else class="size-4" />
          </Button>
          <Button size="icon" class="size-9 shrink-0" :disabled="busy || working || !note.trim()" :aria-label="t('narrate.piece.sendNote')" @click="sendNote">
            <Send class="size-4" />
          </Button>
        </div>
      </div>

      <div v-if="takes.length > 1">
        <p class="mb-1 text-xs font-medium text-muted-foreground">{{ t('narrate.piece.otherTakes') }}</p>
        <ul class="space-y-1.5">
          <li v-for="v in takes" :key="v.id" class="flex min-w-0 items-center gap-2">
            <AudioClip
              v-if="v.cleaned_audio_url || v.audio_url"
              :src="(v.cleaned_audio_url || v.audio_url)!"
              :seconds="v.duration_seconds"
              class="min-w-0 flex-1"
            />
            <span class="w-9 shrink-0 text-right font-mono text-xs tabular-nums text-muted-foreground">{{ (v.grade?.take_score ?? v.grade?.score ?? 0).toFixed(1) }}</span>
            <Button
              size="sm"
              :variant="v.id === segment.selected_variant_id ? 'default' : 'outline'"
              class="shrink-0"
              :disabled="busy || v.id === segment.selected_variant_id"
              @click="choose(v.id)"
            >
              {{ v.id === segment.selected_variant_id ? t('narrate.piece.inUse') : t('narrate.piece.use') }}
            </Button>
          </li>
        </ul>
      </div>
    </div>
  </li>
</template>
