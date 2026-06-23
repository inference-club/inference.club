<script setup lang="ts">
// Memory gauge for a machine. Modes:
//   live + segments — the stacked breakdown: each service's VRAM is a colored
//           segment of the bar (free space is the muted remainder), with a
//           hover panel detailing every service's footprint and share.
//   live    — actual VRAM used / total with util, single fill (no per-service
//           data, e.g. a node with dcgm but no reporter).
//   declared — operator-declared capacity from the manifest, sized relative to
//           `maxGb`. Labeled "declared" so it's never mistaken for a reading.
// Unified-memory boxes (DGX Spark) are labeled "unified".
import { formatBytes } from '@/composables/useClusterState'

export interface VramSegment {
  label: string
  bytes: number
  color: string
  type?: string
}

const props = withDefaults(
  defineProps<{
    gb?: number | null
    maxGb?: number | null
    unified?: boolean
    color?: string
    usedBytes?: number | null
    totalBytes?: number | null
    utilPercent?: number | null
    // Per-service VRAM segments (already filtered to this node). When present
    // with a known total, the bar renders stacked + hoverable.
    segments?: VramSegment[]
  }>(),
  {
    gb: null, maxGb: null, unified: false, color: '#22c55e',
    usedBytes: null, totalBytes: null, utilPercent: null, segments: () => [],
  },
)

const hasLive = computed(() => (props.totalBytes ?? 0) > 0)
const total = computed(() => props.totalBytes || 1)
const segs = computed(() => (props.segments ?? []).filter(s => s.bytes > 0))
const hasSegments = computed(() => hasLive.value && segs.value.length > 0)

const widthPct = (bytes: number) => Math.max(0.5, (bytes / total.value) * 100)
const sharePct = (bytes: number) => Math.round((bytes / total.value) * 100)

// "used" for the simple (non-segmented) live fill.
const pct = computed(() => {
  if (hasLive.value) {
    const used = props.usedBytes ?? 0
    const ratio = Math.round((used / total.value) * 100)
    return used > 0 ? Math.min(100, Math.max(2, ratio)) : 0
  }
  if (!props.gb) return 0
  const max = Math.max(props.maxGb || props.gb, props.gb, 1)
  return Math.max(6, Math.round((props.gb / max) * 100))
})

// VRAM the per-service segments don't account for (other processes / overhead).
const segmentedBytes = computed(() => segs.value.reduce((s, x) => s + x.bytes, 0))
const otherBytes = computed(() => Math.max(0, (props.usedBytes ?? 0) - segmentedBytes.value))

const label = computed(() => {
  const g = props.gb ?? 0
  return g >= 10 ? Math.round(g).toString() : g.toFixed(1)
})
const util = computed(() => (props.utilPercent == null ? null : Math.round(props.utilPercent)))
</script>

<template>
  <div v-if="hasLive || gb" class="group/mem relative space-y-1">
    <div class="flex items-baseline justify-between text-xs">
      <span class="font-medium text-muted-foreground">{{ unified ? 'Memory' : 'VRAM' }}</span>
      <span v-if="hasLive" class="font-mono tabular-nums">
        <span class="font-semibold text-foreground">{{ formatBytes(usedBytes ?? 0) }}</span>
        <span class="text-muted-foreground"> / {{ formatBytes(totalBytes ?? 0) }}</span>
        <span v-if="util != null" class="text-muted-foreground"> · {{ util }}% util</span>
      </span>
      <span v-else class="font-mono tabular-nums">
        <span class="font-semibold text-foreground">{{ label }}</span>&thinsp;GB
        <span class="text-muted-foreground">{{ unified ? 'unified' : 'VRAM' }} · declared</span>
      </span>
    </div>

    <!-- stacked per-service segments -->
    <div v-if="hasSegments" class="flex h-2.5 w-full gap-px overflow-hidden rounded-full bg-muted">
      <div
        v-for="s in segs"
        :key="s.label"
        class="h-full first:rounded-l-full transition-[width] duration-500"
        :style="{ width: `${widthPct(s.bytes)}%`, background: s.color }"
        :title="`${s.label} · ${formatBytes(s.bytes)} (${sharePct(s.bytes)}%)`"
      />
      <div
        v-if="otherBytes > 0"
        class="h-full bg-muted-foreground/40"
        :style="{ width: `${widthPct(otherBytes)}%` }"
        :title="`other · ${formatBytes(otherBytes)}`"
      />
    </div>
    <!-- simple fill (live without per-service data, or declared) -->
    <div v-else class="h-2.5 w-full overflow-hidden rounded-full bg-muted">
      <div
        class="h-full rounded-full transition-[width] duration-500"
        :style="{ width: `${pct}%`, background: `linear-gradient(90deg, ${color}99, ${color})` }"
      />
    </div>

    <!-- hover breakdown -->
    <div
      v-if="hasSegments"
      class="pointer-events-none absolute left-0 top-full z-20 mt-1 w-full min-w-[14rem] rounded-lg border bg-popover p-2.5 text-xs opacity-0 shadow-lg transition-opacity group-hover/mem:opacity-100"
    >
      <p class="mb-1.5 font-medium text-muted-foreground">
        VRAM by service · {{ formatBytes(usedBytes ?? 0) }} of {{ formatBytes(totalBytes ?? 0) }}
        <span v-if="util != null"> · {{ util }}% util</span>
      </p>
      <ul class="space-y-1">
        <li v-for="s in segs" :key="s.label" class="flex items-center gap-2">
          <span class="size-2.5 shrink-0 rounded-[3px]" :style="{ background: s.color }" />
          <span class="truncate font-medium text-foreground">{{ s.label }}</span>
          <span class="ml-auto shrink-0 font-mono tabular-nums text-muted-foreground">
            {{ formatBytes(s.bytes) }} · {{ sharePct(s.bytes) }}%
          </span>
        </li>
        <li v-if="otherBytes > 0" class="flex items-center gap-2">
          <span class="size-2.5 shrink-0 rounded-[3px] bg-muted-foreground/40" />
          <span class="truncate text-muted-foreground">other</span>
          <span class="ml-auto shrink-0 font-mono tabular-nums text-muted-foreground">{{ formatBytes(otherBytes) }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>
