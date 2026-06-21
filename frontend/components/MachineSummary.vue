<script setup lang="ts">
// Compact, one-line fleet summary for list/header contexts: the set of engine
// logos in use, total memory, GPU count, and service count. Same visual
// language as <MachineCard> but condensed. Derived from a manifest's hosts.
import { Cpu, HardDrive, Layers } from 'lucide-vue-next'
import type { ManifestHost } from '@/composables/useManifest'

const props = defineProps<{ hosts?: ManifestHost[] }>()

const hosts = computed(() => props.hosts ?? [])

// Unique engines across all services, in first-seen order.
const engines = computed(() => {
  const seen = new Set<string>()
  const out: string[] = []
  for (const h of hosts.value) {
    for (const s of h.services ?? []) {
      const e = s.engine || 'other'
      if (!seen.has(e)) { seen.add(e); out.push(e) }
    }
  }
  return out
})

const totalMemGb = computed(() =>
  Math.round(hosts.value.reduce((sum, h) => sum + (h.gpu?.vram_gb ?? 0), 0)),
)
const gpuCount = computed(() =>
  hosts.value.reduce((sum, h) => sum + (h.gpu?.count ?? (h.gpu ? 1 : 0)), 0),
)
const serviceCount = computed(() =>
  hosts.value.reduce((sum, h) => sum + (h.services?.length ?? 0), 0),
)
</script>

<template>
  <div v-if="hosts.length" class="flex flex-wrap items-center gap-x-4 gap-y-2">
    <div v-if="engines.length" class="flex items-center gap-1">
      <EngineLogo v-for="e in engines" :key="e" :engine="e" :size="22" />
    </div>
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      <span v-if="totalMemGb" class="inline-flex items-center gap-1">
        <HardDrive class="size-3.5" />
        <span class="font-mono tabular-nums text-foreground">{{ totalMemGb }}</span>&thinsp;GB
      </span>
      <span v-if="gpuCount" class="inline-flex items-center gap-1">
        <Cpu class="size-3.5" />
        <span class="font-mono tabular-nums text-foreground">{{ gpuCount }}</span> GPU{{ gpuCount === 1 ? '' : 's' }}
      </span>
      <span v-if="serviceCount" class="inline-flex items-center gap-1">
        <Layers class="size-3.5" />
        <span class="font-mono tabular-nums text-foreground">{{ serviceCount }}</span> service{{ serviceCount === 1 ? '' : 's' }}
      </span>
    </div>
  </div>
</template>
