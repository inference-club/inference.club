<script setup lang="ts">
// nvtop-style live sparkline: a stacked area of per-service VRAM over time (the
// composition of the GPU's memory, not just the total), with a faint
// device-utilization line overlaid. Samples accumulate from the cluster-state
// poll while the page is open. Colors match the stacked bar (serviceColor).
import type { VramSample } from '@/composables/useClusterState'

const props = defineProps<{
  samples: VramSample[]
  colors: Record<string, string>
}>()

const W = 100
const H = 30

const enough = computed(() => props.samples.length >= 2)

// Service stacking order: union across the window, latest-largest first (stable
// so bands don't jump as values wobble).
const names = computed(() => {
  const latest = props.samples[props.samples.length - 1]?.services ?? {}
  const set = new Set<string>()
  for (const s of props.samples) for (const k in s.services) set.add(k)
  return [...set].sort((a, b) => (latest[b] ?? 0) - (latest[a] ?? 0))
})

// Consistent y-scale across the window (handles the unified pool / changing total).
const scaleTotal = computed(() => Math.max(1, ...props.samples.map(s => s.total)))

const areas = computed(() => {
  const n = props.samples.length
  const xs = (i: number) => (n <= 1 ? 0 : (i / (n - 1)) * W)
  const y = (bytes: number) => H - (bytes / scaleTotal.value) * H
  const cum = props.samples.map(() => 0) // running stack offset per sample
  const out: { name: string; color: string; d: string }[] = []
  for (const name of names.value) {
    const top: string[] = []
    const bot: string[] = []
    props.samples.forEach((s, i) => {
      const b = s.services[name] ?? 0
      const y0 = cum[i]
      const y1 = cum[i] + b
      cum[i] = y1
      top.push(`${xs(i).toFixed(2)},${y(y1).toFixed(2)}`)
      bot.push(`${xs(i).toFixed(2)},${y(y0).toFixed(2)}`)
    })
    out.push({ name, color: props.colors[name] ?? '#9ca3af', d: `M${top.join(' L')} L${bot.reverse().join(' L')} Z` })
  }
  return out
})

const utilLine = computed(() => {
  const n = props.samples.length
  if (n < 2) return ''
  return props.samples
    .map((s, i) => `${((i / (n - 1)) * W).toFixed(2)},${(H - (Math.min(100, s.util) / 100) * H).toFixed(2)}`)
    .join(' ')
})
</script>

<template>
  <div v-if="enough" class="space-y-0.5">
    <svg :viewBox="`0 0 ${W} ${H}`" class="h-8 w-full overflow-visible" preserveAspectRatio="none">
      <path v-for="a in areas" :key="a.name" :d="a.d" :fill="a.color" fill-opacity="0.9" />
      <!-- device utilization (0–100%) overlaid as a faint line -->
      <polyline
        :points="utilLine"
        fill="none"
        stroke="currentColor"
        stroke-width="1"
        vector-effect="non-scaling-stroke"
        class="text-foreground/35"
      />
    </svg>
    <p class="text-[10px] text-muted-foreground">
      VRAM by service over time · {{ samples.length }} samples · faint line = GPU util
    </p>
  </div>
</template>
