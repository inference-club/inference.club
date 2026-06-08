<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { Copy, Check } from 'lucide-vue-next'
import type { TranscriptWord, TranscriptSegment } from '@/types'

const props = withDefaults(
  defineProps<{
    text: string
    src?: string | null
    words?: TranscriptWord[] | null
    segments?: TranscriptSegment[] | null
    language?: string | null
  }>(),
  { src: null, words: null, segments: null, language: null },
)

const audio = ref<HTMLAudioElement | null>(null)
const currentTime = ref(0)
const copied = ref(false)

// Prefer word-level highlighting; fall back to segments; else plain text.
const hasWords = computed(() => Array.isArray(props.words) && props.words.length > 0)
const hasSegments = computed(
  () => !hasWords.value && Array.isArray(props.segments) && props.segments.length > 0,
)
const interactive = computed(() => hasWords.value || hasSegments.value)

// `timeupdate` fires only ~4×/s, which makes word-level highlighting trail the
// audio by up to ~250ms. While playing we poll currentTime via rAF (~60fps) so
// the active word lines up with what's being spoken; we still listen to
// timeupdate/seeked for the paused/scrubbing cases.
let raf = 0
const onTime = () => {
  currentTime.value = audio.value?.currentTime ?? 0
}
const tick = () => {
  onTime()
  raf = requestAnimationFrame(tick)
}
const onPlay = () => {
  cancelAnimationFrame(raf)
  raf = requestAnimationFrame(tick)
}
const onPause = () => {
  cancelAnimationFrame(raf)
  onTime()
}
onBeforeUnmount(() => cancelAnimationFrame(raf))

const isActive = (start?: number, end?: number) => {
  if (start == null) return false
  const t = currentTime.value
  return t >= start && (end == null || t < end)
}

const seek = (start?: number) => {
  if (start == null || !audio.value) return
  audio.value.currentTime = start
  audio.value.play().catch(() => {})
}

const copy = async () => {
  try {
    await navigator.clipboard.writeText(props.text)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    /* clipboard unavailable */
  }
}
</script>

<template>
  <div class="space-y-3">
    <!-- Audio player (bound to the stored/recorded input audio) -->
    <audio
      v-if="src"
      ref="audio"
      :src="src"
      controls
      class="w-full h-10"
      @timeupdate="onTime"
      @play="onPlay"
      @playing="onPlay"
      @pause="onPause"
      @ended="onPause"
      @seeked="onTime"
    />

    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2 text-[11px] text-muted-foreground">
        <Badge v-if="language" variant="outline" class="uppercase">{{ language }}</Badge>
        <span v-if="interactive && src">Click a {{ hasWords ? 'word' : 'line' }} to jump to it</span>
        <span v-else-if="!interactive">Transcript</span>
      </div>
      <Button variant="ghost" size="sm" class="h-7 gap-1.5 text-xs" @click="copy">
        <component :is="copied ? Check : Copy" class="size-3.5" />
        {{ copied ? 'Copied' : 'Copy' }}
      </Button>
    </div>

    <!-- Word-level karaoke transcript. flex-wrap + gap supplies the spacing so
         words always wrap (the source tokens may not carry their own spaces),
         avoiding a single unbreakable run that overflows horizontally. -->
    <p v-if="hasWords" class="flex flex-wrap items-baseline gap-x-1 gap-y-0.5 text-base leading-relaxed">
      <span
        v-for="(w, i) in words"
        :key="i"
        class="rounded px-0.5 transition-colors duration-75"
        :class="[
          src ? 'cursor-pointer hover:bg-accent' : '',
          isActive(w.start, w.end)
            ? 'bg-primary text-primary-foreground'
            : '',
        ]"
        @click="seek(w.start)"
        >{{ w.word.trim() }}</span>
    </p>

    <!-- Segment-level transcript -->
    <div v-else-if="hasSegments" class="space-y-1.5">
      <p
        v-for="(s, i) in segments"
        :key="i"
        class="text-sm leading-relaxed rounded px-2 py-1 transition-colors"
        :class="[
          src ? 'cursor-pointer hover:bg-accent' : '',
          isActive(s.start, s.end) ? 'bg-primary/15 ring-1 ring-primary/40' : '',
        ]"
        @click="seek(s.start)"
      >
        <span v-if="s.start != null" class="text-[10px] tabular-nums text-muted-foreground mr-2">
          {{ s.start.toFixed(1) }}s
        </span>
        {{ s.text }}
      </p>
    </div>

    <!-- Plain text (model doesn't emit timestamps, e.g. Qwen3-ASR) -->
    <p v-else class="text-base leading-relaxed whitespace-pre-wrap">{{ text || '—' }}</p>
  </div>
</template>
