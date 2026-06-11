<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { RefreshCw, Cpu, Server, Sparkles, Wrench, Activity, Layers } from 'lucide-vue-next'
import { useProviders, type Provider } from '@/composables/useProviders'
import {
  ENGINE_LABELS,
  VENDOR_LABELS,
  type ManifestModel,
  type ManifestService,
} from '@/composables/useManifest'
import { fmtCtx } from '@/utils/modelCapabilities'

definePageMeta({
  layout: 'app',
})

const { providers, isLoading, error, fetchProviders, refreshModels } = useProviders()

onMounted(fetchProviders)

const onlineCount = computed(() => providers.value.filter(p => p.is_online).length)
const totalModels = computed(() =>
  providers.value.reduce(
    (sum, p) => sum + p.models.filter(m => m.is_active).length,
    0,
  ),
)
const totalServices = computed(() =>
  providers.value.reduce(
    (sum, p) =>
      sum + (p.manifest?.parsed.hosts ?? []).reduce((n, h) => n + (h.services?.length ?? 0), 0),
    0,
  ),
)

const formatRelative = (iso: string | null) => {
  if (!iso) return 'never'
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

const formatDate = (iso: string | null) => {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

const engineLabel = (e: string) => ENGINE_LABELS[e] ?? e
const vendorLabel = (v?: string) => (v ? VENDOR_LABELS[v] ?? v : '')
const modelLabel = (m: ManifestModel) => m.id || m.hf || 'model'
const modelSlug = (m: ManifestModel) => (m.hf || m.id || '').trim().toLowerCase()
const playgroundLink = (slug: string) => `/dashboard/playground?model=${encodeURIComponent(slug)}`

// A manifest-declared model is matched to the live ProviderModel rows (the
// serializer already filters `provider.models` to is_active=True) by served
// id / hf repo / slug, so we can show its real context window + active dot.
const modelKeys = (m: ManifestModel) =>
  new Set([modelSlug(m), (m.id || '').toLowerCase(), (m.hf || '').toLowerCase()].filter(Boolean))

const isModelActive = (provider: Provider, m: ManifestModel) => {
  const keys = modelKeys(m)
  return provider.models.some(pm => pm.is_active && keys.has(pm.name.toLowerCase()))
}
const ctxFor = (provider: Provider, m: ManifestModel) => {
  const keys = modelKeys(m)
  const pm = provider.models.find(p => keys.has(p.name.toLowerCase()))
  return fmtCtx(pm?.context_window ?? null)
}

// There's no real per-service health probe server-side, so derive a status
// from the node's online-state plus how many of the service's declared models
// are currently active (per the agent's latest /v1/models sync).
type SvcState = 'online' | 'degraded' | 'offline'
const serviceStatus = (provider: Provider, svc: ManifestService) => {
  const models = svc.models ?? []
  const total = models.length
  const active = models.filter(m => isModelActive(provider, m)).length
  let state: SvcState
  let detail: string
  if (!provider.is_online) {
    state = 'offline'
    detail = 'node offline'
  } else if (total === 0) {
    state = 'online'
    detail = 'node online'
  } else if (active === total) {
    state = 'online'
    detail = `${active}/${total} models active`
  } else if (active > 0) {
    state = 'degraded'
    detail = `${active}/${total} models active`
  } else {
    state = 'offline'
    detail = 'no models active'
  }
  return { state, detail }
}

const STATUS_BADGE: Record<SvcState, string> = {
  online: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  degraded: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  offline: 'bg-muted text-muted-foreground',
}
const STATUS_DOT: Record<SvcState, string> = {
  online: 'bg-emerald-500',
  degraded: 'bg-amber-500',
  offline: 'bg-muted-foreground/50',
}
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-4 sm:px-6 py-6 space-y-8">
    <DashboardPageHeader
      title="Dashboard"
      description="Overview of your compute and inference activity."
    />

    <OnboardingChecklist />

    <section class="space-y-4">
      <div class="flex items-end justify-between">
        <div>
          <h2 class="text-xl font-semibold flex items-center gap-2">
            <Cpu class="h-5 w-5" />
            Registered Compute
          </h2>
          <p class="text-sm text-muted-foreground">
            Agents you've registered to serve inference on the inference.club tailnet.
          </p>
        </div>
        <button
          class="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 disabled:opacity-50"
          :disabled="isLoading"
          @click="fetchProviders"
        >
          <RefreshCw class="h-3.5 w-3.5" :class="{ 'animate-spin': isLoading }" />
          {{ isLoading ? 'Refreshing…' : 'Refresh' }}
        </button>
      </div>

      <div class="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <Card class="p-4">
          <div class="flex items-center justify-between gap-2">
            <p class="text-2xs uppercase tracking-wider text-muted-foreground">Nodes</p>
            <Server class="size-4 text-muted-foreground/50" />
          </div>
          <p class="text-2xl font-semibold mt-1 tabular-nums">
            {{ providers.length }}
          </p>
        </Card>
        <Card class="p-4">
          <div class="flex items-center justify-between gap-2">
            <p class="text-2xs uppercase tracking-wider text-muted-foreground">Online</p>
            <Activity class="size-4 text-muted-foreground/50" />
          </div>
          <p class="text-2xl font-semibold mt-1 tabular-nums"
            :class="onlineCount > 0 ? 'text-green-600 dark:text-green-400' : ''">
            {{ onlineCount }}
          </p>
        </Card>
        <Card class="p-4">
          <div class="flex items-center justify-between gap-2">
            <p class="text-2xs uppercase tracking-wider text-muted-foreground">Services</p>
            <Layers class="size-4 text-muted-foreground/50" />
          </div>
          <p class="text-2xl font-semibold mt-1 tabular-nums">
            {{ totalServices }}
          </p>
        </Card>
        <Card class="p-4">
          <div class="flex items-center justify-between gap-2">
            <p class="text-2xs uppercase tracking-wider text-muted-foreground">Models served</p>
            <Cpu class="size-4 text-muted-foreground/50" />
          </div>
          <p class="text-2xl font-semibold mt-1 tabular-nums">
            {{ totalModels }}
          </p>
        </Card>
      </div>

      <div v-if="error" class="p-4 bg-destructive/10 text-destructive rounded text-sm">
        {{ error }}
      </div>

      <div v-if="isLoading && providers.length === 0" class="grid gap-3">
        <Card v-for="i in 2" :key="i" class="p-5 animate-pulse">
          <div class="h-5 bg-muted rounded w-40 mb-3" />
          <div class="h-4 bg-muted rounded w-64" />
        </Card>
      </div>

      <Card
        v-else-if="providers.length === 0"
        class="p-6"
      >
        <h3 class="font-semibold mb-2">No nodes registered yet</h3>
        <p class="text-sm text-muted-foreground mb-3">
          Run <code class="text-foreground">inference-club-agent</code> on a machine
          with an LLM server, configured with your inference.club API key. The agent
          joins the tailnet and registers automatically.
        </p>
        <p class="text-sm text-muted-foreground">
          Get an API key at
          <NuxtLink to="/dashboard/settings/token" class="underline">
            Settings → Token
          </NuxtLink>. See the
          <NuxtLink to="/docs/providers/run-an-agent" class="underline">
            agent guide
          </NuxtLink>
          for setup.
        </p>
      </Card>

      <div v-else class="grid gap-3">
        <Card
          v-for="provider in providers"
          :key="provider.id"
          class="p-5 space-y-4 min-w-0"
        >
          <!-- node header -->
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex min-w-0 items-center gap-2">
                <h3 class="min-w-0 font-semibold truncate">{{ provider.name }}</h3>
                <Badge :variant="provider.is_online ? 'default' : 'secondary'">
                  <span
                    class="inline-block h-1.5 w-1.5 rounded-full mr-1.5"
                    :class="provider.is_online ? 'bg-green-500' : 'bg-muted-foreground'"
                  />
                  {{ provider.is_online ? 'online' : 'offline' }}
                </Badge>
              </div>
              <p class="text-xs text-muted-foreground mt-1 font-mono truncate">
                {{ provider.tailnet_hostname || '(awaiting registration)' }}<template
                  v-if="provider.agent_port && provider.agent_port !== 443"
                >:{{ provider.agent_port }}</template>
              </p>
            </div>
            <div class="flex flex-col items-end gap-1.5 shrink-0">
              <div class="text-right text-xs text-muted-foreground space-y-0.5">
                <p>last seen {{ formatRelative(provider.last_seen_at) }}</p>
                <p>registered {{ formatDate(provider.registered_at) }}</p>
              </div>
              <button
                class="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 disabled:opacity-50"
                :disabled="isLoading"
                @click="refreshModels(provider.id)"
              >
                <RefreshCw class="h-3 w-3" :class="{ 'animate-spin': isLoading }" />
                Refresh models
              </button>
            </div>
          </div>

          <!-- hosts → services → models (from the uploaded manifest) -->
          <template v-if="provider.manifest && provider.manifest.parsed.hosts.length">
            <div
              v-for="host in provider.manifest.parsed.hosts"
              :key="host.id"
              class="border-t pt-3 space-y-3"
            >
              <!-- host line: id, network, GPU -->
              <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <Server class="size-4 text-muted-foreground shrink-0" />
                <span class="font-medium text-sm">{{ host.id }}</span>
                <span
                  v-if="host.hostname || host.address"
                  class="min-w-0 break-all text-xs text-muted-foreground font-mono"
                >
                  <template v-if="host.hostname">{{ host.hostname }}</template><template
                    v-if="host.hostname && host.address"
                  > · </template><template v-if="host.address">{{ host.address }}</template>
                </span>
                <span v-if="host.gpu" class="inline-flex items-center gap-1.5 text-xs">
                  <Cpu class="size-3.5 text-muted-foreground" />
                  <span class="font-medium">{{ host.gpu.model || 'GPU' }}</span>
                  <span
                    v-if="host.gpu.vendor"
                    class="rounded bg-muted px-1 py-0.5"
                  >{{ vendorLabel(host.gpu.vendor) }}</span>
                  <span
                    v-if="host.gpu.vram_gb"
                    class="text-muted-foreground"
                  >{{ host.gpu.vram_gb }}&thinsp;GB</span>
                  <span
                    v-if="host.gpu.count && host.gpu.count > 1"
                    class="text-muted-foreground"
                  >× {{ host.gpu.count }}</span>
                </span>
              </div>
              <p v-if="host.notes" class="text-xs text-muted-foreground italic">{{ host.notes }}</p>

              <!-- services on this host -->
              <div v-if="host.services && host.services.length" class="space-y-3">
                <div
                  v-for="svc in host.services"
                  :key="svc.name"
                  class="rounded-md border bg-background/40 p-3 space-y-2"
                >
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <div class="flex items-center gap-2 flex-wrap min-w-0">
                      <span
                        class="rounded bg-primary/10 text-primary px-1.5 py-0.5 text-xs font-medium"
                      >{{ engineLabel(svc.engine) }}</span>
                      <span class="min-w-0 text-sm font-medium truncate">{{ svc.name }}</span>
                    </div>
                    <span
                      class="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium"
                      :class="STATUS_BADGE[serviceStatus(provider, svc).state]"
                      :title="serviceStatus(provider, svc).detail"
                    >
                      <span
                        class="size-1.5 rounded-full"
                        :class="STATUS_DOT[serviceStatus(provider, svc).state]"
                      />
                      {{ serviceStatus(provider, svc).state }}
                    </span>
                  </div>
                  <p class="text-xs text-muted-foreground font-mono break-all">{{ svc.url }}</p>

                  <!-- models served by this service -->
                  <div v-if="svc.models && svc.models.length" class="space-y-1.5">
                    <div
                      v-for="m in svc.models"
                      :key="modelSlug(m)"
                      class="flex items-center justify-between gap-2 rounded border bg-background px-2 py-1.5"
                    >
                      <div class="flex items-center gap-2 min-w-0">
                        <span
                          class="size-1.5 rounded-full shrink-0"
                          :class="isModelActive(provider, m) ? 'bg-emerald-500' : 'bg-muted-foreground/40'"
                          :title="isModelActive(provider, m) ? 'active' : 'inactive'"
                        />
                        <span class="min-w-0 font-mono text-xs truncate">{{ modelLabel(m) }}</span>
                        <span
                          v-if="ctxFor(provider, m)"
                          class="shrink-0 rounded bg-muted px-1 py-0.5 text-[11px] font-mono text-muted-foreground"
                        >{{ ctxFor(provider, m) }}</span>
                      </div>
                      <NuxtLink
                        v-if="modelSlug(m)"
                        :to="playgroundLink(modelSlug(m))"
                        class="shrink-0 inline-flex items-center gap-1 text-xs text-primary hover:underline underline-offset-4"
                      >
                        <Sparkles class="size-3" /> playground
                      </NuxtLink>
                    </div>
                  </div>

                  <details v-if="svc.command" class="group">
                    <summary
                      class="text-xs text-muted-foreground cursor-pointer inline-flex items-center gap-1"
                    >
                      <Wrench class="size-3" /> command
                    </summary>
                    <pre
                      class="mt-1 rounded bg-muted/60 p-2 text-xs overflow-auto whitespace-pre-wrap font-mono"
                    >{{ svc.command }}</pre>
                  </details>
                </div>
              </div>
              <p v-else class="text-xs text-muted-foreground italic">
                no services configured on this host
              </p>
            </div>
          </template>

          <!-- fallback: no manifest yet — flat list of live-discovered models -->
          <div v-else class="border-t pt-3">
            <p class="text-xs uppercase text-muted-foreground tracking-wide mb-1.5">
              Models ({{ provider.models.filter(m => m.is_active).length }})
            </p>
            <div v-if="provider.models.length > 0" class="flex flex-wrap gap-1.5">
              <span
                v-for="m in provider.models.filter(x => x.is_active)"
                :key="m.id"
                class="px-1.5 py-0.5 text-xs rounded bg-muted font-mono"
              >
                {{ m.name }}
              </span>
            </div>
            <p v-else class="text-xs text-muted-foreground italic">
              No models reported yet. Upload a service manifest from your agent for a richer view.
            </p>
          </div>
        </Card>
      </div>
    </section>
  </div>
</template>
