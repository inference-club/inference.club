<script setup lang="ts">
// Public node (host) detail: /<handle>/nodes/<host_id>. Shows the machine's
// specs, its GPUs (with live VRAM/utilization when the agent reports it), the
// services running on it, and the generations made on it with stats. Linked
// from every generation's host/GPU chips. Live perf is overlaid from the same
// cluster-state proxy the 3D scene uses; specs/services/stats come from the
// node endpoint.
import { ArrowLeft, Cpu, HardDrive, Server, Activity, Clock, Zap, Boxes } from 'lucide-vue-next'
import type { PublicProfile } from '@/composables/useManifest'
import { useClusterState, formatBytes, type LiveNode } from '@/composables/useClusterState'
import { useNode, type NodeDetail } from '@/composables/useNode'
import { machineForm, prettyGpuModel } from '@/composables/useMachineForm'
import { formatLatency } from '@/utils/inference'

const route = useRoute()
const { apiBase, nodeUrl } = useNode()

const username = computed(() => String(route.params.username || ''))
const hostId = computed(() => String(route.params.node || ''))

// Profile gives us the provider + manifest (for live cluster state + the
// machine's form-factor) and lets us resolve the provider when ?provider is
// absent.
const { data: profile } = await useFetch<PublicProfile>(
  () => `${apiBase}/api/users/${encodeURIComponent(username.value)}/`,
  { credentials: 'include' },
)

const provider = computed(() => {
  const providers = profile.value?.providers ?? []
  const wanted = Number(route.query.provider)
  if (wanted) return providers.find((p) => p.id === wanted) ?? null
  // Otherwise the first provider whose manifest declares this host.
  return (
    providers.find((p) =>
      (p.manifest?.parsed?.hosts ?? []).some((h) => h.id === hostId.value),
    ) ?? providers[0] ?? null
  )
})

if (!provider.value) {
  throw createError({ statusCode: 404, statusMessage: `@${username.value} has no node ${hostId.value}`, fatal: true })
}

const { data: node, error } = await useFetch<NodeDetail>(
  () => nodeUrl(provider.value!.id, hostId.value),
  { credentials: 'include', watch: [provider, hostId] },
)

if (error.value || !node.value) {
  throw createError({ statusCode: 404, statusMessage: `No node @${username.value}/${hostId.value}`, fatal: true })
}

// Live overlay (k8s providers only) — find this host in the cluster snapshot.
const { state, start } = useClusterState(() => provider.value?.id)
onMounted(() => { if (provider.value) start() })
const liveNode = computed<LiveNode | null>(
  () => (state.value?.nodes ?? []).find((n) => n.host_id === hostId.value) ?? null,
)
const liveDevice = (index: number) =>
  (liveNode.value?.gpu?.devices ?? []).find((d) => d.index === index) ?? null
const liveProcs = (index: number) =>
  (liveNode.value?.gpu?.processes ?? []).filter((p) => p.gpu_index === index)

// Form-factor icon from the manifest host (best-effort).
const manifestHost = computed(() =>
  (provider.value?.manifest?.parsed?.hosts ?? []).find((h) => h.id === hostId.value) ?? null,
)
const formInfo = computed(() => (manifestHost.value ? machineForm(manifestHost.value) : null))

const isOwner = computed(() => node.value?.is_owner ?? false)
const modalities = computed(() =>
  Object.entries(node.value?.stats?.by_modality ?? {}).sort((a, b) => b[1] - a[1]),
)

useHead({ title: () => `${node.value?.hostname || hostId.value} — @${username.value} · inference.club` })
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 sm:px-6 py-6">
    <NuxtLink
      :to="`/${username}`"
      class="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft class="size-4" /> @{{ username }}
    </NuxtLink>

    <template v-if="node">
      <!-- Header -->
      <div class="mb-6 flex flex-wrap items-start gap-3">
        <component :is="formInfo?.icon || HardDrive" class="mt-1 size-7 shrink-0 text-muted-foreground" />
        <div class="min-w-0">
          <h1 class="flex items-center gap-2 text-2xl font-bold">
            {{ node.hostname || node.host_id }}
            <ReadinessDot v-if="node.provider.is_online" :online="true" />
          </h1>
          <p class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
            <span class="font-mono">{{ node.host_id }}</span>
            <span>·</span>
            <NuxtLink
              v-if="node.provider.owner_handle"
              :to="`/${node.provider.owner_handle}`"
              class="inline-flex items-center gap-1 hover:text-foreground"
            >
              <Server class="size-3.5" /> {{ node.provider.name }}
            </NuxtLink>
            <template v-if="node.provider.owner_handle">
              <span>·</span>
              <NuxtLink
                :to="`/${node.provider.owner_handle}/cluster?provider=${node.provider.id}`"
                class="inline-flex items-center gap-1 hover:text-foreground"
              >
                <Boxes class="size-3.5" /> 3D cluster
              </NuxtLink>
            </template>
          </p>
          <p v-if="node.address && isOwner" class="mt-0.5 font-mono text-xs text-muted-foreground">{{ node.address }}</p>
          <p v-if="node.notes" class="mt-1 max-w-2xl text-sm text-muted-foreground">{{ node.notes }}</p>
        </div>
      </div>

      <!-- Stats -->
      <div class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div class="rounded-lg border bg-background p-3">
          <div class="flex items-center gap-1.5 text-xs text-muted-foreground"><Activity class="size-3.5" /> Generations</div>
          <div class="mt-1 text-2xl font-bold tabular-nums">{{ node.stats.total.toLocaleString() }}</div>
        </div>
        <div class="rounded-lg border bg-background p-3">
          <div class="flex items-center gap-1.5 text-xs text-muted-foreground"><Cpu class="size-3.5" /> GPUs</div>
          <div class="mt-1 text-2xl font-bold tabular-nums">{{ node.gpus.length }}</div>
        </div>
        <div class="rounded-lg border bg-background p-3">
          <div class="flex items-center gap-1.5 text-xs text-muted-foreground"><Clock class="size-3.5" /> Avg latency</div>
          <div class="mt-1 text-2xl font-bold tabular-nums">{{ node.stats.avg_latency_ms != null ? formatLatency(node.stats.avg_latency_ms) : '—' }}</div>
        </div>
        <div class="rounded-lg border bg-background p-3">
          <div class="flex items-center gap-1.5 text-xs text-muted-foreground"><Zap class="size-3.5" /> Tokens</div>
          <div class="mt-1 text-2xl font-bold tabular-nums">{{ (node.stats.total_completion_tokens || 0).toLocaleString() }}</div>
        </div>
      </div>

      <!-- by-modality chips -->
      <div v-if="modalities.length" class="mb-8 flex flex-wrap items-center gap-2">
        <span class="text-xs text-muted-foreground">By modality:</span>
        <span v-for="[type, n] in modalities" :key="type" class="inline-flex items-center gap-1.5">
          <ModalityBadge :type="type" />
          <span class="text-xs tabular-nums text-muted-foreground">{{ n }}</span>
        </span>
      </div>

      <!-- GPUs (each anchored as #gpu-<index>) -->
      <section class="mb-8">
        <h2 class="mb-3 flex items-center gap-2 text-lg font-semibold"><Cpu class="size-5" /> GPUs</h2>
        <div v-if="!node.gpus.length" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          No GPUs declared for this node.
        </div>
        <div v-else class="grid gap-3 sm:grid-cols-2">
          <Card v-for="g in node.gpus" :id="`gpu-${g.index}`" :key="g.index" class="scroll-mt-20 p-4">
            <div class="flex items-center justify-between gap-2">
              <div class="min-w-0">
                <p class="truncate font-medium">{{ prettyGpuModel(g.model || '') || g.model || 'GPU' }}</p>
                <p class="text-xs text-muted-foreground">
                  GPU {{ g.index }}<template v-if="g.vendor"> · {{ g.vendor }}</template>
                  <template v-if="g.vram_gb"> · {{ g.vram_gb }} GB</template>
                </p>
              </div>
            </div>
            <!-- Live VRAM/util when the agent reports it -->
            <div v-if="liveDevice(g.index)" class="mt-3">
              <MemoryBar
                :used-bytes="liveDevice(g.index)!.vram_used_bytes"
                :total-bytes="liveDevice(g.index)!.vram_total_bytes"
                :util-percent="liveDevice(g.index)!.util_percent"
              />
              <div v-if="liveProcs(g.index).length" class="mt-2 space-y-1">
                <div
                  v-for="p in liveProcs(g.index)"
                  :key="p.pid"
                  class="flex items-center justify-between gap-2 text-xs text-muted-foreground"
                >
                  <span class="truncate font-mono">{{ p.service || p.process_name || p.pod || `pid ${p.pid}` }}</span>
                  <span class="shrink-0 tabular-nums">{{ formatBytes(p.used_bytes) }}</span>
                </div>
              </div>
            </div>
            <p v-else class="mt-3 text-xs text-muted-foreground">No live telemetry.</p>
          </Card>
        </div>
      </section>

      <!-- Services -->
      <section v-if="node.services.length" class="mb-8">
        <h2 class="mb-3 flex items-center gap-2 text-lg font-semibold"><Server class="size-5" /> Services</h2>
        <div class="grid gap-2">
          <div
            v-for="s in node.services"
            :key="s.id"
            class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border bg-background p-3"
          >
            <EngineLogo v-if="s.engine" :engine="s.engine" class="size-4 shrink-0" />
            <span class="font-medium">{{ s.name }}</span>
            <span v-if="s.engine" class="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase">{{ s.engine }}</span>
            <span v-if="s.models?.length" class="min-w-0 truncate font-mono text-xs text-muted-foreground">
              {{ s.models.join(', ') }}
            </span>
          </div>
        </div>
      </section>

      <!-- Generations made on this node -->
      <section>
        <h2 class="mb-3 flex items-center gap-2 text-lg font-semibold"><Activity class="size-5" /> Recent generations</h2>
        <p v-if="!node.recent.length" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          No generations on this node yet.
        </p>
        <div v-else class="grid gap-3">
          <InferenceRequestCard v-for="r in node.recent" :key="r.id" :request="r" />
        </div>
      </section>
    </template>
  </div>
</template>
