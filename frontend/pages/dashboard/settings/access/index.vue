<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { toast } from 'vue-sonner'
import { ShieldCheck, Server, Cpu, Pause, Play } from 'lucide-vue-next'
import {
  useServices,
  type ProviderServiceItem,
  type HostAccessItem,
} from '@/composables/useServices'
import { useProviders, type Provider } from '@/composables/useProviders'

definePageMeta({
  layout: 'app',
  requireAuth: true,
  gateTitleKey: 'dashboard.items.access',
})

const { services, hosts, loading, error, fetchServices, updateService, fetchHosts, updateHost } = useServices()
const { providers, fetchProviders, setAcceptingRequests, updateProviderAccess } = useProviders()

const savingId = ref<number | null>(null)
const pausingId = ref<number | null>(null)
const savingProviderId = ref<number | null>(null)
const savingHostId = ref<number | null>(null)

const providerById = computed(() => {
  const m = new Map<number, Provider>()
  for (const p of providers.value) m.set(p.id, p)
  return m
})

// Group only currently-active services by their node (provider). Services that
// have dropped out of the agent's config (is_active === false) are stale and
// excluded entirely, which in turn hides any node left with nothing live.
const grouped = computed(() => {
  const map = new Map<number, { id: number; name: string; services: ProviderServiceItem[] }>()
  for (const s of services.value) {
    if (!s.is_active) continue
    const g = map.get(s.provider.id) ?? { id: s.provider.id, name: s.provider.name, services: [] }
    g.services.push(s)
    map.set(s.provider.id, g)
  }
  return Array.from(map.values())
})

// Look up a Host record by its (cluster, manifest host_id) key.
const hostByKey = computed(() => {
  const m = new Map<string, HostAccessItem>()
  for (const h of hosts.value) m.set(`${h.provider_id}:${h.host_id}`, h)
  return m
})

// Three-level shape: cluster (provider) → physical node (host) → services.
// Each cluster joins its full provider record (access policy, pause state);
// within it, services are sub-grouped by the host they run on, joined to the
// editable Host record. `provider`/`host` are null only before data loads.
const nodes = computed(() =>
  grouped.value.map(g => {
    const hostMap = new Map<
      string,
      { host_id: string; host: HostAccessItem | null; services: ProviderServiceItem[] }
    >()
    for (const s of g.services) {
      const key = s.host_id || ''
      const grp =
        hostMap.get(key) ??
        { host_id: key, host: hostByKey.value.get(`${g.id}:${key}`) ?? null, services: [] }
      grp.services.push(s)
      hostMap.set(key, grp)
    }
    return {
      id: g.id,
      name: g.name,
      provider: providerById.value.get(g.id) ?? null,
      hostGroups: Array.from(hostMap.values()),
    }
  }),
)

const save = async (svc: ProviderServiceItem) => {
  savingId.value = svc.id
  try {
    const updated = await updateService(svc.id, {
      access_policy: svc.access_policy,
      allowed_github_users: svc.allowed_github_users,
    })
    // Reflect server-side normalization (e.g. allowlist cleared for non-RESTRICTED).
    svc.allowed_github_users = updated.allowed_github_users
    toast.success(`Access updated for "${svc.name}"`)
  } catch {
    toast.error('Failed to update access')
  } finally {
    savingId.value = null
  }
}

const saveMachine = async (providerId: number) => {
  const p = providerById.value.get(providerId)
  if (!p) return
  savingProviderId.value = providerId
  try {
    const updated = await updateProviderAccess(providerId, {
      access_policy: p.access_policy,
      allowed_github_users: p.allowed_github_users,
    })
    // Reflect server-side normalization (allowlist cleared for non-RESTRICTED).
    p.allowed_github_users = updated.allowed_github_users
    toast.success(`Cluster access updated for "${p.name}"`)
  } catch {
    toast.error('Failed to update cluster access')
  } finally {
    savingProviderId.value = null
  }
}

const saveHost = async (host: HostAccessItem) => {
  savingHostId.value = host.id
  try {
    const updated = await updateHost(host.id, {
      access_policy: host.access_policy,
      allowed_github_users: host.allowed_github_users,
    })
    // Reflect server-side normalization (allowlist cleared for non-RESTRICTED).
    host.allowed_github_users = updated.allowed_github_users
    toast.success(`Node access updated for "${host.host_id}"`)
  } catch {
    toast.error('Failed to update node access')
  } finally {
    savingHostId.value = null
  }
}

const togglePause = async (providerId: number) => {
  const p = providerById.value.get(providerId)
  if (!p) return
  const next = !p.accepting_requests
  pausingId.value = providerId
  try {
    await setAcceptingRequests(providerId, next)
    toast.success(next ? `"${p.name}" is accepting requests` : `"${p.name}" paused — no longer serving`)
  } catch {
    toast.error('Failed to update node')
  } finally {
    pausingId.value = null
  }
}

onMounted(() => {
  fetchServices()
  fetchProviders()
  fetchHosts()
})
</script>

<template>
  <div class="mx-auto w-full max-w-3xl px-3 sm:px-6 py-6">
    <div class="mb-6">
      <h1 class="text-2xl font-bold flex items-center gap-2">
        <ShieldCheck class="h-6 w-6" />
        Inference Access
      </h1>
      <p class="text-sm text-muted-foreground mt-1">
        Gate who in inference.club can route requests to your inference at three
        levels: the whole <strong>cluster</strong>, a single physical
        <strong>node</strong> (e.g. a DGX Spark), and each <strong>service</strong>.
        A request must clear every level — cluster <em>and</em> node <em>and</em>
        service. Models discovered live (outside a manifest) stay private to you
        until declared in a service.
      </p>
    </div>

    <div v-if="loading && services.length === 0" class="space-y-3">
      <Card v-for="i in 2" :key="i" class="p-4 animate-pulse h-24" />
    </div>

    <div v-else-if="error" class="p-4 bg-destructive/10 text-destructive rounded text-sm">
      {{ error }}
    </div>

    <Card v-else-if="grouped.length === 0" class="p-6">
      <h3 class="font-semibold mb-2">No services yet</h3>
      <p class="text-sm text-muted-foreground">
        Register an agent and upload an <code>agent.yaml</code> manifest, and your
        services will appear here for you to share.
      </p>
    </Card>

    <div v-else class="space-y-5">
      <Card v-for="node in nodes" :key="node.id" class="overflow-hidden py-0 gap-0">
        <!-- Machine header: identity, status, pause/resume -->
        <div class="flex items-center justify-between gap-2 px-4 py-3 bg-muted/40 border-b">
          <h2 class="text-sm font-semibold flex items-center gap-2 min-w-0">
            <Server class="size-4 shrink-0 text-muted-foreground" />
            <span class="truncate">{{ node.name }}</span>
            <Badge
              v-if="node.provider && !node.provider.accepting_requests"
              variant="outline"
              class="text-amber-600 border-amber-600/40"
            >paused</Badge>
          </h2>
          <Button
            v-if="node.provider"
            variant="ghost"
            size="sm"
            class="h-7 shrink-0"
            :disabled="pausingId === node.id"
            @click="togglePause(node.id)"
          >
            <Pause v-if="node.provider.accepting_requests" class="size-3.5" />
            <Play v-else class="size-3.5" />
            {{ node.provider.accepting_requests ? 'Pause' : 'Resume' }}
          </Button>
        </div>

        <!-- Cluster-level access policy (applies to every node + service) -->
        <div v-if="node.provider" class="px-4 py-3 border-b">
          <AccessPolicyControl
            v-model:policy="node.provider.access_policy"
            v-model:allowlist="node.provider.allowed_github_users"
            label="Cluster access"
            :saving="savingProviderId === node.id"
            hint="The whole cluster is limited — node and service policies below apply on top."
            @save="saveMachine(node.id)"
          />
        </div>

        <!-- One section per physical node (host): its node-level gate + services -->
        <div
          v-for="hg in node.hostGroups"
          :key="hg.host_id || 'unassigned'"
          class="border-b last:border-b-0"
        >
          <!-- Node-level access policy -->
          <div v-if="hg.host" class="px-4 py-3 bg-muted/20 border-b space-y-2">
            <div class="flex items-center gap-2 text-sm font-medium">
              <Cpu class="size-4 shrink-0 text-muted-foreground" />
              <span class="truncate">{{ hg.host.host_id }}</span>
              <span v-if="hg.host.hostname && hg.host.hostname !== hg.host.host_id" class="text-xs text-muted-foreground truncate">
                {{ hg.host.hostname }}
              </span>
            </div>
            <AccessPolicyControl
              v-model:policy="hg.host.access_policy"
              v-model:allowlist="hg.host.allowed_github_users"
              label="Node access"
              :saving="savingHostId === hg.host.id"
              hint="This node is limited — service policies below apply on top."
              @save="saveHost(hg.host)"
            />
          </div>
          <div v-else-if="hg.host_id" class="px-4 py-2 bg-muted/20 border-b text-sm font-medium flex items-center gap-2">
            <Cpu class="size-4 shrink-0 text-muted-foreground" />
            <span class="truncate">{{ hg.host_id }}</span>
          </div>

          <!-- Services on this node (tightened rows) -->
          <div class="divide-y">
            <div v-for="svc in hg.services" :key="svc.id" class="px-4 py-3">
              <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <h3 class="font-medium text-sm">{{ svc.name }}</h3>
                <Badge v-if="svc.engine" variant="secondary" class="font-mono text-[10px] px-1.5 py-0">{{ svc.engine }}</Badge>
                <span
                  v-for="m in svc.models"
                  :key="m"
                  class="px-1.5 py-0.5 text-[10px] rounded bg-muted font-mono text-muted-foreground"
                >{{ m }}</span>
                <span v-if="!svc.models.length" class="text-xs text-muted-foreground italic">No active models.</span>
              </div>
              <div class="mt-2">
                <AccessPolicyControl
                  v-model:policy="svc.access_policy"
                  v-model:allowlist="svc.allowed_github_users"
                  save-variant="outline"
                  :saving="savingId === svc.id"
                  @save="save(svc)"
                />
              </div>
            </div>
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>
