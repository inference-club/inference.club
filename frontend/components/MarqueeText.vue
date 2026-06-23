<script setup lang="ts">
// Overflow-aware single-line text. When the text fits, it renders statically
// (optionally truncated). When it overflows its container, it scrolls as a
// seamless marquee — unless the user prefers reduced motion, in which case it
// falls back to truncation. Used for song titles in TrackList and the player
// bar, where long names used to just get cut off.

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ text: string }>()

const GAP_PX = 32 // visual gap between the two scrolling copies
const SPEED = 40 // px/sec — constant feel regardless of length

const root = ref<HTMLElement | null>(null)
const measureEl = ref<HTMLElement | null>(null)
const overflowing = ref(false)
const reduced = ref(false)
const shift = ref('0px')
const duration = ref('0s')

// Scroll only when it both overflows and motion is allowed.
const run = computed(() => overflowing.value && !reduced.value)

let ro: ResizeObserver | null = null

const measure = () => {
  const r = root.value
  const m = measureEl.value
  if (!r || !m) return
  const copyW = m.offsetWidth
  overflowing.value = copyW > r.clientWidth + 1
  if (overflowing.value) {
    const distance = copyW + GAP_PX
    shift.value = `${distance}px`
    duration.value = `${Math.max(6, distance / SPEED)}s`
  }
}

watch(() => props.text, () => requestAnimationFrame(measure))

onMounted(() => {
  if (typeof window !== 'undefined' && window.matchMedia) {
    reduced.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }
  measure()
  if (typeof ResizeObserver !== 'undefined' && root.value) {
    ro = new ResizeObserver(() => measure())
    ro.observe(root.value)
  }
})

onBeforeUnmount(() => ro?.disconnect())
</script>

<template>
  <div ref="root" class="relative overflow-hidden">
    <div
      class="mq-track flex w-max whitespace-nowrap"
      :class="run ? 'mq-run' : ''"
      :style="run ? { '--mq-shift': shift, '--mq-dur': duration } : undefined"
    >
      <span ref="measureEl" :class="run ? '' : 'block max-w-full truncate'">{{ text }}</span>
      <span v-if="run" aria-hidden="true" :style="{ marginLeft: `${GAP_PX}px` }">{{ text }}</span>
    </div>
  </div>
</template>

<style scoped>
@keyframes mq-scroll {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(calc(-1 * var(--mq-shift)));
  }
}

.mq-run {
  animation: mq-scroll var(--mq-dur) linear infinite;
  will-change: transform;
}

/* Let people read it: pause while hovering/focusing the row. */
.mq-track.mq-run:hover {
  animation-play-state: paused;
}
</style>
