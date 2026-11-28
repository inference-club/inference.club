<script setup lang="ts">
// The player for a finished narration: one file, a scrubber across the whole
// thing, back/forward 15 seconds, and the speed control (0.5× to 3×, kept at
// pitch). It knows where each piece starts, reports which one is playing so
// the page can highlight it, and can jump to a piece when asked.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Play, Pause, RotateCcw, RotateCw, Download } from 'lucide-vue-next'
import { clock } from '@/composables/useNarration'

const props = defineProps<{
  src: string
  seconds?: number | null
  offsets?: Array<{ segment_id: number; start: number; end: number }>
  downloadName?: string
}>()
const emit = defineEmits<{ (e: 'segment', id: number | null): void; (e: 'time', seconds: number): void }>()

const { t } = useI18n()
const { rate, apply } = usePlaybackRate()
const el = ref<HTMLAudioElement | null>(null)
const playing = ref(false)
const now = ref(0)
const total = ref(props.seconds ?? 0)
watch([rate, el], () => apply(el.value))
watch(() => props.seconds, (s) => { if (s) total.value = s })

const current = computed(() => {
  const list = props.offsets ?? []
  // The gap after a piece still belongs to it, so use the next piece's start.
  for (let i = list.length - 1; i >= 0; i--) if (now.value >= list[i].start - 0.05) return list[i].segment_id
  return list[0]?.segment_id ?? null
})
watch([current, playing], () => emit('segment', playing.value || now.value > 0 ? current.value : null))

const toggle = () => {
  const a = el.value
  if (!a) return
  if (a.paused) a.play().catch(() => {})
  else a.pause()
}
const seek = (s: number) => {
  const a = el.value
  if (!a) return
  a.currentTime = Math.min(Math.max(0, s), total.value || s)
  onTime()
}
// timeupdate fires only a few times a second; while playing, read the clock
// every frame so word-by-word highlighting keeps up at 3× speed.
let raf = 0
const onTime = () => {
  now.value = el.value?.currentTime ?? 0
  emit('time', now.value)
}
const follow = () => {
  onTime()
  raf = playing.value ? requestAnimationFrame(follow) : 0
}
watch(playing, (p) => { if (p && !raf) raf = requestAnimationFrame(follow) })
const onMeta = () => {
  apply(el.value)
  const d = el.value?.duration
  if (d && Number.isFinite(d)) total.value = d
}
const pct = computed(() => (total.value > 0 ? (now.value / total.value) * 100 : 0))
// Listening time left at the chosen speed, which is what a fast listener wants.
const left = computed(() => Math.max(0, total.value - now.value) / rate.value)

/** Jump to a piece and start playing it. */
const playSegment = (id: number) => {
  const hit = (props.offsets ?? []).find((o) => o.segment_id === id)
  if (!hit) return
  seek(hit.start)
  el.value?.play().catch(() => {})
}
defineExpose({ playSegment, toggle })
onBeforeUnmount(() => { cancelAnimationFrame(raf); el.value?.pause() })
</script>

<template>
  <div class="rounded-2xl border bg-card p-3 sm:p-4" data-testid="narration-player">
    <audio
      ref="el"
      :src="src"
      preload="metadata"
      @loadedmetadata="onMeta"
      @timeupdate="onTime"
      @play="playing = true"
      @pause="playing = false"
      @ended="playing = false"
    />
    <input
      type="range"
      class="scrub block w-full"
      min="0"
      :max="total || 0"
      step="0.1"
      :value="now"
      :style="{ '--pct': `${pct}%` }"
      :aria-label="t('request.seek')"
      data-testid="narration-scrub"
      @input="seek(Number(($event.target as HTMLInputElement).value))"
    />
    <div class="mt-1 flex justify-between font-mono text-xs tabular-nums text-muted-foreground">
      <span>{{ clock(now) }}</span>
      <span>{{ t('narrate.player.left', { time: clock(left) }) }}</span>
    </div>
    <div class="mt-2 flex items-center justify-between gap-2">
      <PlaybackSpeed />
      <div class="flex items-center gap-1 sm:gap-2">
        <button type="button" class="ctl" :aria-label="t('narrate.player.back')" :title="t('narrate.player.back')" @click="seek(now - 15)">
          <RotateCcw class="size-5" />
        </button>
        <button
          type="button"
          class="flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow transition hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          :aria-label="playing ? t('request.pause') : t('request.play')"
          data-testid="narration-play"
          @click="toggle"
        >
          <Pause v-if="playing" class="size-6" />
          <Play v-else class="size-6 translate-x-0.5" />
        </button>
        <button type="button" class="ctl" :aria-label="t('narrate.player.forward')" :title="t('narrate.player.forward')" @click="seek(now + 15)">
          <RotateCw class="size-5" />
        </button>
      </div>
      <a
        :href="src"
        :download="downloadName || 'narration.mp3'"
        class="ctl"
        :aria-label="t('request.download')"
        :title="t('request.download')"
      >
        <Download class="size-5" />
      </a>
    </div>
  </div>
</template>

<style scoped>
.ctl {
  display: flex;
  width: 2.75rem;
  height: 2.75rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  color: var(--muted-foreground);
}
.ctl:hover {
  background: var(--accent);
  color: var(--foreground);
}
.scrub {
  appearance: none;
  height: 6px;
  border-radius: 9999px;
  cursor: pointer;
  background: linear-gradient(
    to right,
    var(--primary) var(--pct, 0%),
    color-mix(in oklab, var(--foreground) 15%, transparent) var(--pct, 0%)
  );
}
.scrub::-webkit-slider-thumb {
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 9999px;
  background: var(--primary);
}
.scrub::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border: 0;
  border-radius: 9999px;
  background: var(--primary);
}
</style>
