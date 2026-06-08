<script setup lang="ts">
// A live m:ss stopwatch for in-flight inference. While `running` is true it
// ticks up from zero; when it flips false it freezes (and hides). Used on the
// playground pages so a slow generation (music, image, speech, 3D) shows how
// long it's been working in real time.

import { onBeforeUnmount, ref, watch } from 'vue'
import { Timer } from 'lucide-vue-next'

const props = defineProps<{ running: boolean }>()

const elapsedMs = ref(0)
let startedAt = 0
let timer: ReturnType<typeof setInterval> | null = null

const stopInterval = () => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

watch(
  () => props.running,
  (r) => {
    if (r) {
      startedAt = Date.now()
      elapsedMs.value = 0
      stopInterval()
      timer = setInterval(() => (elapsedMs.value = Date.now() - startedAt), 250)
    } else {
      stopInterval()
    }
  },
  { immediate: true },
)

onBeforeUnmount(stopInterval)

const fmt = (ms: number) => {
  const total = Math.floor(ms / 1000)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}
</script>

<template>
  <span v-if="running" class="inline-flex items-center gap-1 tabular-nums">
    <Timer class="size-3.5" /> {{ fmt(elapsedMs) }}
  </span>
</template>
