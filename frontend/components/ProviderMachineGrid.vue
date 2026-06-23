<script setup lang="ts">
// One provider's machines: the fleet summary line + a grid of <MachineCard>.
// When the provider is a kubernetes agent, this polls its live /cluster/state
// (same source as the 3D scene) and hands each card the live node matched by
// host_id, so the memory gauges show ACTUAL VRAM instead of the declared
// capacity. Non-k8s providers (or unreachable agents) render from the manifest
// alone — live data is pure progressive enhancement.
import type { CatalogModelInfo, ManifestHost } from '@/composables/useManifest'
import { useClusterState, type LiveNode } from '@/composables/useClusterState'

const props = withDefaults(
  defineProps<{
    providerId: number
    hosts: ManifestHost[]
    // 'kubernetes' unlocks the live cluster-state poll.
    discovery?: string
    maxMemoryGb?: number
    online?: boolean
    catalog?: CatalogModelInfo[]
    showCommand?: boolean
  }>(),
  { discovery: '', maxMemoryGb: 0, online: undefined, catalog: undefined, showCommand: false },
)

const isK8s = computed(() => props.discovery === 'kubernetes')

const { state, history, start, stop } = useClusterState(() => props.providerId)

onMounted(() => {
  if (isK8s.value) start()
})
onBeforeUnmount(stop)

// Live node per host, keyed by host_id (the manifest↔agent join key).
const liveByHostId = computed(() => {
  const map = new Map<string, LiveNode>()
  for (const n of state.value?.nodes ?? []) map.set(n.host_id, n)
  return map
})
</script>

<template>
  <div>
    <MachineSummary :hosts="hosts" class="mb-4" />
    <div class="grid gap-4 lg:grid-cols-2">
      <MachineCard
        v-for="host in hosts"
        :key="host.id"
        :host="host"
        :max-memory-gb="maxMemoryGb"
        :online="online"
        :catalog="catalog"
        :show-command="showCommand"
        :live="liveByHostId.get(host.id) ?? null"
        :history="history[host.id] ?? []"
      />
    </div>
  </div>
</template>
