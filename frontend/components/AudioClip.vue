<script setup lang="ts">
// A small, quiet audio player for one clip (speech, a recording, an enhanced
// take): play/pause, a scrubber and the time. Songs use the global player
// instead, so they keep playing across pages.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Play, Pause, Download } from 'lucide-vue-next'
import { formatTrackTime } from '@/utils/player'

const props = defineProps<{
  src: string
  /** Known length in seconds, shown before the file's metadata loads. */
  seconds?: number | null
  label?: string
  downloadName?: string
}>()

const { t } = useI18n()
const el = ref<HTMLAudioElement | null>(null)
// Speed is shared across the site; follow it, including while playing.
const { rate, apply } = usePlaybackRate()
watch([rate, el], () => apply(el.value))
const playing = ref(false)
const now = ref(0)
const total = ref(props.seconds ?? 0)

const toggle = () => {
  const a = el.value
  if (!a) return
  if (a.paused) {
    // One clip at a time on a page.
    document.querySelectorAll('audio').forEach((o) => o !== a && o.pause())
    a.play().catch(() => {})
  } else {
    a.pause()
  }
}
const onMeta = () => {
  apply(el.value)
  const d = el.value?.duration
  if (d && Number.isFinite(d)) total.value = d
}
const onTime = () => {
  now.value = el.value?.currentTime ?? 0
}
const seek = (e: Event) => {
  const v = Number((e.target as HTMLInputElement).value)
  if (el.value) el.value.currentTime = v
  now.value = v
}
const pct = computed(() => (total.value > 0 ? (now.value / total.value) * 100 : 0))

onBeforeUnmount(() => el.value?.pause())
</script>

<template>
  <div class="flex min-w-0 items-center gap-3 rounded-xl border bg-muted/30 px-3 py-2.5">
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
    <button
      type="button"
      class="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      :aria-label="playing ? t('request.pause') : t('request.play')"
      @click="toggle"
    >
      <Pause v-if="playing" class="size-4" />
      <Play v-else class="size-4 translate-x-px" />
    </button>
    <div class="min-w-0 flex-1">
      <p v-if="label" class="mb-1 truncate text-xs text-muted-foreground">{{ label }}</p>
      <input
        type="range"
        class="clip-range block w-full"
        min="0"
        :max="total || 0"
        step="0.05"
        :value="now"
        :style="{ '--pct': `${pct}%` }"
        :aria-label="t('request.seek')"
        @input="seek"
      />
    </div>
    <span class="hidden shrink-0 text-xs tabular-nums text-muted-foreground min-[380px]:inline">
      {{ formatTrackTime(now) }} / {{ formatTrackTime(total) }}
    </span>
    <PlaybackSpeed compact />
    <a
      v-if="downloadName"
      :href="src"
      :download="downloadName"
      class="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
      :aria-label="t('request.download')"
      :title="t('request.download')"
    >
      <Download class="size-4" />
    </a>
  </div>
</template>

<style scoped>
.clip-range {
  appearance: none;
  height: 4px;
  border-radius: 9999px;
  cursor: pointer;
  background: linear-gradient(
    to right,
    var(--primary) var(--pct, 0%),
    color-mix(in oklab, var(--foreground) 15%, transparent) var(--pct, 0%)
  );
}
.clip-range::-webkit-slider-thumb {
  appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 9999px;
  background: var(--primary);
}
.clip-range::-moz-range-thumb {
  width: 12px;
  height: 12px;
  border: 0;
  border-radius: 9999px;
  background: var(--primary);
}
</style>
