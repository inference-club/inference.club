<script setup lang="ts">
// An equalizer-style visualizer that sits right above an audio player: a wide,
// short row of bars driven by the real audio via the Web Audio API
// (AnalyserNode + getByteFrequencyData), the way music players usually do it.
// The song's OUTPUT_AUDIO asset is a public kind served with CORS headers, so
// `crossorigin="anonymous"` lets us analyse it without tainting and without
// affecting playback. If Web Audio is unavailable or setup fails, we fall back
// to a deterministic CSS bounce so the bars still move.

import { onBeforeUnmount, ref } from 'vue'
import { getSharedAudioContext } from '@/utils/audio'

withDefaults(
  defineProps<{ src: string; audioClass?: string }>(),
  { audioClass: 'w-full h-10' },
)

const BAR_COUNT = 32
const IDLE = 0.12

const audioEl = ref<HTMLAudioElement | null>(null)
const levels = ref<number[]>(Array(BAR_COUNT).fill(IDLE)) // per-bar scaleY, 0..1
const playing = ref(false)
const useCss = ref(false) // fallback when the analyser can't run

// Deterministic CSS-fallback timing (no Math.random → SSR & client match).
const frac = (i: number, seed: number) => {
  const x = Math.sin((i + 1) * seed) * 10000
  return x - Math.floor(x)
}
const cssBars = Array.from({ length: BAR_COUNT }, (_, i) => ({
  '--peak': (0.45 + frac(i, 12.9898) * 0.55).toFixed(2),
  '--dur': (0.5 + frac(i, 78.233) * 0.6).toFixed(2) + 's',
  '--delay': '-' + (frac(i, 43.123) * 0.7).toFixed(2) + 's',
}))

// --- Web Audio analyser ----------------------------------------------------
let ctx: AudioContext | null = null
let analyser: AnalyserNode | null = null
let source: MediaElementAudioSourceNode | null = null
let freq: Uint8Array | null = null
let raf = 0

const setup = (): boolean => {
  if (analyser) return true
  const el = audioEl.value
  if (!el) return false
  ctx = getSharedAudioContext()
  if (!ctx) return false
  try {
    // createMediaElementSource can only be called once per element; `analyser`
    // guards against a second call.
    source = ctx.createMediaElementSource(el)
    analyser = ctx.createAnalyser()
    analyser.fftSize = 256
    analyser.smoothingTimeConstant = 0.75
    source.connect(analyser)
    analyser.connect(ctx.destination)
    freq = new Uint8Array(analyser.frequencyBinCount)
    return true
  } catch {
    return false
  }
}

const tick = () => {
  if (!analyser || !freq) return
  analyser.getByteFrequencyData(freq)
  // The top bins are mostly empty for music, so spread the bars over the lower
  // portion of the spectrum where the energy actually is.
  const usable = Math.floor(freq.length * 0.75)
  const next = new Array<number>(BAR_COUNT)
  for (let i = 0; i < BAR_COUNT; i++) {
    const start = Math.floor((i / BAR_COUNT) * usable)
    const end = Math.max(start + 1, Math.floor(((i + 1) / BAR_COUNT) * usable))
    let sum = 0
    for (let j = start; j < end; j++) sum += freq[j]
    next[i] = Math.min(1, Math.max(IDLE, sum / (end - start) / 255))
  }
  levels.value = next
  raf = requestAnimationFrame(tick)
}

const onPlay = () => {
  playing.value = true
  if (useCss.value) return
  if (!setup()) {
    useCss.value = true // give up on analysis, let CSS take over
    return
  }
  void ctx?.resume?.() // contexts start suspended until a user gesture
  if (!raf) raf = requestAnimationFrame(tick)
}

const stopLoop = () => {
  if (raf) cancelAnimationFrame(raf)
  raf = 0
}

const onStop = () => {
  playing.value = false
  stopLoop()
  levels.value = Array(BAR_COUNT).fill(IDLE) // ease the bars back to flat
}

const barStyle = (i: number) =>
  useCss.value ? cssBars[i] : { transform: `scaleY(${levels.value[i]})` }

onBeforeUnmount(() => {
  stopLoop()
  try {
    source?.disconnect()
    analyser?.disconnect()
  } catch {
    /* already torn down */
  }
})
</script>

<template>
  <div class="space-y-1.5" @click.stop>
    <div class="eq flex h-8 w-full items-end gap-[2px]" aria-hidden="true">
      <span
        v-for="(lvl, i) in levels"
        :key="i"
        class="eq-bar flex-1 rounded-sm bg-primary/70"
        :class="{ 'eq-anim': useCss && playing }"
        :style="barStyle(i)"
      />
    </div>
    <audio
      ref="audioEl"
      :src="src"
      crossorigin="anonymous"
      controls
      :class="audioClass"
      @play="onPlay"
      @playing="onPlay"
      @pause="onStop"
      @ended="onStop"
    />
  </div>
</template>

<style scoped>
.eq-bar {
  height: 100%;
  transform: scaleY(0.12);
  transform-origin: bottom;
  /* Smooths frame-to-frame analyser updates and the settle-to-flat on pause. */
  transition: transform 0.06s ease-out;
}
/* CSS fallback only (used when the Web Audio analyser can't run). */
.eq-anim {
  animation: eq-bounce var(--dur) ease-in-out infinite alternate;
  animation-delay: var(--delay);
}
@keyframes eq-bounce {
  from {
    transform: scaleY(0.15);
  }
  to {
    transform: scaleY(var(--peak, 1));
  }
}
@media (prefers-reduced-motion: reduce) {
  .eq-anim {
    animation: none;
  }
}
</style>
