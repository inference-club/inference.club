<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { toast } from 'vue-sonner'
import { ShieldCheck, Server, Lock, Globe, Users, Pause, Play } from 'lucide-vue-next'
import { useServices, type ProviderServiceItem, type AccessPolicy } from '@/composables/useServices'
import { useProviders, type Provider } from '@/composables/useProviders'

definePageMeta({
  layout: 'app',
  requireAuth: true,
  gateTitleKey: 'dashboard.items.access',
})

const { services, loading, error, fetchServices, updateService } = useServices()
const { providers, fetchProviders, setAcceptingRequests } = useProviders()

const savingId = ref<number | null>(null)
const pausingId = ref<number | null>(null)

const POLICY_LABELS: Record<AccessPolicy, string> = {
  PRIVATE: 'Only me',
  AUTHENTICATED: 'Any inference.club member',
  RESTRICTED: 'Specific GitHub users',
}

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
        Choose who in inference.club can route requests to each of your services.
        Models discovered live (outside a manifest) stay private to you until they're
        declared in a service.
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

    <div v-else class="space-y-6">
      <div v-for="node in grouped" :key="node.id">
        <div class="flex items-center justify-between gap-2 mb-2">
          <h2 class="text-sm font-semibold text-muted-foreground flex items-center gap-1.5 min-w-0">
            <Server class="size-4 shrink-0" />
            <span class="truncate">{{ node.name }}</span>
            <Badge
              v-if="providerById.get(node.id) && !providerById.get(node.id)!.accepting_requests"
              variant="outline"
              class="text-amber-600 border-amber-600/40"
            >paused</Badge>
          </h2>
          <Button
            v-if="providerById.get(node.id)"
            variant="ghost"
            size="sm"
            class="h-7 shrink-0"
            :disabled="pausingId === node.id"
            @click="togglePause(node.id)"
          >
            <Pause v-if="providerById.get(node.id)!.accepting_requests" class="size-3.5" />
            <Play v-else class="size-3.5" />
            {{ providerById.get(node.id)!.accepting_requests ? 'Pause' : 'Resume' }}
          </Button>
        </div>

        <div class="space-y-2">
          <Card v-for="svc in node.services" :key="svc.id" class="p-4">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="font-semibold">{{ svc.name }}</h3>
              <Badge v-if="svc.engine" variant="secondary" class="font-mono">{{ svc.engine }}</Badge>
              <span
                v-for="m in svc.models"
                :key="m"
                class="px-1.5 py-0.5 text-xs rounded bg-muted font-mono"
              >{{ m }}</span>
              <span v-if="!svc.models.length" class="text-xs text-muted-foreground italic">No active models.</span>
            </div>

            <div class="border-t mt-3 pt-3 space-y-3">
              <div class="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
                <label class="text-sm font-medium w-40 shrink-0">Who can use this</label>
                <Select v-model="svc.access_policy">
                  <SelectTrigger class="w-full sm:max-w-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="PRIVATE">
                      <span class="inline-flex items-center gap-2"><Lock class="size-3.5" /> {{ POLICY_LABELS.PRIVATE }}</span>
                    </SelectItem>
                    <SelectItem value="AUTHENTICATED">
                      <span class="inline-flex items-center gap-2"><Globe class="size-3.5" /> {{ POLICY_LABELS.AUTHENTICATED }}</span>
                    </SelectItem>
                    <SelectItem value="RESTRICTED">
                      <span class="inline-flex items-center gap-2"><Users class="size-3.5" /> {{ POLICY_LABELS.RESTRICTED }}</span>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div v-if="svc.access_policy === 'RESTRICTED'" class="flex flex-col sm:flex-row gap-2 sm:gap-3">
                <label class="text-sm font-medium w-40 shrink-0 pt-2">Allowed GitHub users</label>
                <div class="flex-1">
                  <TagsInput v-model="svc.allowed_github_users" class="w-full">
                    <TagsInputItem v-for="u in svc.allowed_github_users" :key="u" :value="u">
                      <TagsInputItemText />
                      <TagsInputItemDelete />
                    </TagsInputItem>
                    <TagsInputInput placeholder="github-username, then Enter" />
                  </TagsInput>
                  <p class="text-xs text-muted-foreground mt-1">
                    Type a GitHub username and press Enter. Case-insensitive.
                  </p>
                </div>
              </div>

              <div class="flex justify-end">
                <Button size="sm" :disabled="savingId === svc.id" @click="save(svc)">
                  {{ savingId === svc.id ? 'Saving…' : 'Save' }}
                </Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  </div>
</template>
