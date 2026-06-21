<script setup lang="ts">
// Relative memory gauge for a machine. The fill is sized against `maxGb` — the
// largest machine in the group being shown — so a fleet's relative capacities
// read at a glance (a 128 GB Spark dwarfs a 24 GB RTX). Unified-memory boxes
// (DGX Spark, Apple silicon) are labeled "unified"; discrete GPUs say "VRAM".
const props = withDefaults(
  defineProps<{
    gb?: number | null
    maxGb?: number | null
    unified?: boolean
    // accent color for the fill (defaults to NVIDIA-ish green)
    color?: string
  }>(),
  { gb: null, maxGb: null, unified: false, color: '#22c55e' },
)

const pct = computed(() => {
  if (!props.gb) return 0
  const max = Math.max(props.maxGb || props.gb, props.gb, 1)
  // floor at a visible sliver so small boxes don't vanish next to a Spark
  return Math.max(6, Math.round((props.gb / max) * 100))
})

// GFD reports VRAM in MiB; the agent divides by 1024, so values arrive as
// floats (24564 MiB → 23.988). Show a clean number: integer ≥ 10 GB, else 1 dp.
const label = computed(() => {
  const g = props.gb ?? 0
  return g >= 10 ? Math.round(g).toString() : g.toFixed(1)
})
</script>

<template>
  <div v-if="gb" class="space-y-1">
    <div class="flex items-baseline justify-between text-xs">
      <span class="font-medium text-muted-foreground">Memory</span>
      <span class="font-mono tabular-nums">
        <span class="font-semibold text-foreground">{{ label }}</span>&thinsp;GB
        <span class="text-muted-foreground">{{ unified ? 'unified' : 'VRAM' }}</span>
      </span>
    </div>
    <div class="h-2 w-full overflow-hidden rounded-full bg-muted">
      <div
        class="h-full rounded-full transition-[width] duration-500"
        :style="{
          width: `${pct}%`,
          background: `linear-gradient(90deg, ${color}99, ${color})`,
        }"
      />
    </div>
  </div>
</template>
