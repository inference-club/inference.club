<script setup lang="ts">
/**
 * Whole-episode preview: stitches every segment's finished (trimmed) take into
 * one continuous timeline and plays them back-to-back through a single audio
 * element. Blocks are sized by duration; click one to start there; a playhead
 * sweeps across as it plays. (Ported in spirit from inference-club-studio.)
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Pause, Play, Square } from 'lucide-vue-next'
import type { Segment, Word } from '@/composables/useStudio'

const props = defineProps<{ segments: Segment[] }>()

interface Clip { url: string; dur: number; label: number; ready: boolean; words: Word[] }

const clips = computed<Clip[]>(() => {
  const out: Clip[] = []
  for (const s of props.segments) {
    const v = s.variants?.find((x) => x.id === s.selected_variant_id) || s.variants?.[0]
    const url = v?.cleaned_audio_url || v?.audio_url
    if (url) out.push({ url, dur: v?.duration_seconds || 0, label: s.position + 1, ready: s.status === 'ready', words: v?.words || [] })
  }
  return out
})
const hasWords = computed(() => clips.value.some((c) => c.words.length))
const total = computed(() => clips.value.reduce((s, c) => s + (c.dur || 0), 0))
function widthPct(c: Clip) {
  return total.value ? (c.dur / total.value) * 100 : 100 / Math.max(1, clips.value.length)
}

let audio: HTMLAudioElement | null = null
let raf = 0
const playingIdx = ref(-1)
const isPlaying = ref(false)
const clipTime = ref(0)

const cursorPct = computed(() => {
  if (playingIdx.value < 0 || !total.value) return 0
  let off = 0
  for (let i = 0; i < playingIdx.value; i++) off += clips.value[i].dur || 0
  return Math.max(0, Math.min(100, ((off + clipTime.value) / total.value) * 100))
})

function ensure() {
  if (audio || !import.meta.client) return
  audio = new Audio()
  audio.addEventListener('ended', () => playClip(playingIdx.value + 1))
}
function tick() {
  if (!audio) return
  clipTime.value = audio.currentTime
  if (isPlaying.value) raf = requestAnimationFrame(tick)
}
function playClip(i: number) {
  ensure()
  if (!audio) return
  if (i < 0 || i >= clips.value.length) { stop(); return }
  playingIdx.value = i
  clipTime.value = 0
  audio.src = clips.value[i].url
  audio.play()
    .then(() => { isPlaying.value = true; cancelAnimationFrame(raf); raf = requestAnimationFrame(tick) })
    .catch(() => { isPlaying.value = false })
}
function toggle() {
  ensure()
  if (!audio) return
  if (isPlaying.value) { audio.pause(); isPlaying.value = false; cancelAnimationFrame(raf); return }
  if (playingIdx.value >= 0 && audio.src) {
    audio.play().then(() => { isPlaying.value = true; raf = requestAnimationFrame(tick) }).catch(() => {})
  } else {
    playClip(0)
  }
}
function stop() {
  if (audio) { audio.pause(); audio.removeAttribute('src') }
  isPlaying.value = false
  playingIdx.value = -1
  clipTime.value = 0
  cancelAnimationFrame(raf)
}

// Karaoke: the active word in the currently-playing clip (its words are aligned
// to the trimmed audio, which is exactly what the timeline plays).
const activeWord = computed(() => {
  if (playingIdx.value < 0) return -1
  const ws = clips.value[playingIdx.value]?.words || []
  return ws.findIndex((w) => clipTime.value >= w.start && clipTime.value < w.end)
})

function seekToWord(ci: number, start: number) {
  ensure()
  if (!audio) return
  if (ci !== playingIdx.value) {
    playingIdx.value = ci
    clipTime.value = start
    audio.src = clips.value[ci].url
    audio.addEventListener('loadedmetadata', () => { if (audio) audio.currentTime = start }, { once: true })
    audio.play().then(() => { isPlaying.value = true; cancelAnimationFrame(raf); raf = requestAnimationFrame(tick) }).catch(() => {})
  } else {
    audio.currentTime = start
    clipTime.value = start
  }
}

// Keep the active word scrolled into view as playback advances.
const wordStrip = ref<HTMLElement>()
watch([playingIdx, activeWord], async () => {
  await nextTick()
  wordStrip.value?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
})

const elapsed = computed(() => {
  if (playingIdx.value < 0) return 0
  let off = 0
  for (let i = 0; i < playingIdx.value; i++) off += clips.value[i].dur || 0
  return off + clipTime.value
})
const fmt = (s: number) => {
  if (!isFinite(s) || s < 0) s = 0
  return `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}`
}

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  if (audio) { audio.pause(); audio.src = '' }
})
</script>

<template>
  <div v-if="clips.length" class="space-y-2 rounded-xl border bg-background p-3">
    <div class="flex items-center gap-2">
      <button
        type="button"
        class="flex size-8 items-center justify-center rounded-md bg-fuchsia-500 text-white hover:bg-fuchsia-600"
        :title="isPlaying ? 'Pause' : 'Play the whole episode'"
        @click="toggle"
      >
        <component :is="isPlaying ? Pause : Play" class="size-4" />
      </button>
      <button
        v-if="playingIdx >= 0" type="button"
        class="flex size-8 items-center justify-center rounded-md border text-muted-foreground hover:bg-muted"
        title="Stop" @click="stop"
      >
        <Square class="size-3.5" />
      </button>
      <span class="text-sm font-medium">Episode preview</span>
      <span class="ml-auto text-xs tabular-nums text-muted-foreground">{{ fmt(elapsed) }} / {{ fmt(total) }}</span>
    </div>

    <!-- segment blocks -->
    <div class="relative flex h-9 w-full overflow-hidden rounded-md border bg-muted/40">
      <button
        v-for="(c, i) in clips" :key="i"
        type="button"
        class="group relative h-full border-r border-background/60 text-[10px] font-medium transition-colors last:border-r-0"
        :class="i === playingIdx ? 'bg-fuchsia-500/30 text-foreground' : c.ready ? 'bg-emerald-500/15 text-emerald-700 hover:bg-emerald-500/25 dark:text-emerald-300' : 'bg-muted text-muted-foreground hover:bg-muted-foreground/20'"
        :style="{ width: `${widthPct(c)}%` }"
        :title="`Segment ${c.label} · ${fmt(c.dur)}`"
        @click="playClip(i)"
      >
        <span class="absolute inset-0 grid place-items-center">{{ c.label }}</span>
      </button>
      <!-- playhead -->
      <div
        v-if="playingIdx >= 0"
        class="pointer-events-none absolute inset-y-0 w-px bg-sky-500"
        :style="{ left: `${cursorPct}%` }"
      />
    </div>

    <!-- karaoke word strip: every word, highlighted as it's spoken -->
    <div
      v-if="hasWords"
      ref="wordStrip"
      class="max-h-28 overflow-y-auto rounded-md border bg-muted/30 px-3 py-2 text-xs leading-relaxed"
    >
      <span class="flex flex-wrap items-center gap-x-1 gap-y-0.5">
        <template v-for="(c, ci) in clips" :key="ci">
          <button
            v-for="(w, wi) in c.words"
            :key="`${ci}-${wi}`"
            type="button"
            :data-active="ci === playingIdx && wi === activeWord"
            class="rounded px-0.5 transition-colors"
            :class="ci === playingIdx && wi === activeWord
              ? 'bg-fuchsia-500/30 font-medium text-foreground'
              : 'text-muted-foreground hover:bg-foreground/10'"
            @click="seekToWord(ci, w.start)"
          >
            {{ w.word }}
          </button>
          <span v-if="c.words.length && ci < clips.length - 1" class="text-muted-foreground/30">·</span>
        </template>
      </span>
    </div>
  </div>
</template>
