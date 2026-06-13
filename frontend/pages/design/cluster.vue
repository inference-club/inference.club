<script setup lang="ts">
// Living Cluster scene workbench — renders ClusterScene from a frozen mock of
// the real home fleet (utils/clusterMock.ts) so the viz can be art-directed
// without a live agent. Scenario + theme are settable via query params
// (?scenario=degraded&theme=dark) for deterministic screenshots.
import { Sun, Moon } from 'lucide-vue-next'
import { useTheme } from '@/composables/useTheme'
import { buildMockClusterSnapshot, type MockScenario } from '@/utils/clusterMock'

definePageMeta({ layout: 'app', middleware: 'staff' })

const route = useRoute()
const { isDark } = useTheme()

const SCENARIOS: { key: MockScenario; label: string; desc: string }[] = [
  { key: 'live', label: 'Live', desc: 'all nodes ready, traffic flowing' },
  { key: 'degraded', label: 'Degraded', desc: 'a3 down, trellis2 crash-looping' },
  { key: 'manifest', label: 'Manifest only', desc: 'shape without live state' },
]

const scenario = ref<MockScenario>(
  SCENARIOS.some(s => s.key === route.query.scenario) ? (route.query.scenario as MockScenario) : 'live',
)

onMounted(() => {
  if (route.query.theme === 'dark') isDark.value = true
  else if (route.query.theme === 'light') isDark.value = false
})

const snapshot = computed(() => buildMockClusterSnapshot(scenario.value))
</script>

<template>
  <div class="mx-auto flex h-[calc(100vh-4rem)] w-full max-w-7xl flex-col px-3 py-4 sm:px-6">
    <div class="flex flex-wrap items-center gap-3 pb-3">
      <div>
        <h1 class="text-lg font-semibold tracking-tight">Living cluster — scene workbench</h1>
        <p class="text-xs text-muted-foreground">
          Frozen copy of the real fleet (a1 · a2 · a3 · spark + LM Studio satellite); fabricated traffic.
        </p>
      </div>
      <div class="ml-auto flex items-center gap-2">
        <div class="flex rounded-lg border border-border p-0.5">
          <button
            v-for="s in SCENARIOS"
            :key="s.key"
            class="rounded-md px-2.5 py-1 text-xs font-medium transition-colors"
            :class="scenario === s.key ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'"
            :title="s.desc"
            @click="scenario = s.key"
          >
            {{ s.label }}
          </button>
        </div>
        <button
          class="inline-flex size-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:text-foreground"
          :title="isDark ? 'Switch to light' : 'Switch to dark'"
          @click="isDark = !isDark"
        >
          <Sun v-if="isDark" class="size-4" />
          <Moon v-else class="size-4" />
        </button>
      </div>
    </div>

    <div
      id="cluster-stage"
      class="min-h-0 flex-1 overflow-hidden rounded-xl border border-border bg-background"
    >
      <ClusterScene :snapshot="snapshot" :show-commands="true" class="h-full" />
    </div>
  </div>
</template>
