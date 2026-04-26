<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { RefreshCw, Globe } from 'lucide-vue-next'
import { useAllProviders } from '@/composables/useProviders'

definePageMeta({
  layout: 'app',
})

const { providers, isLoading, error, fetchAllProviders } = useAllProviders()

onMounted(fetchAllProviders)

const onlineCount = computed(() => providers.value.filter(p => p.is_online).length)
const ownerCount = computed(
  () => new Set(providers.value.map(p => p.owner).filter(Boolean)).size,
)
const totalModels = computed(() =>
  providers.value.reduce(
    (sum, p) => sum + p.models.filter(m => m.is_active).length,
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
</script>

<template>
  <div class="container mx-auto p-6 space-y-6">
    <div class="flex items-end justify-between">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <Globe class="h-6 w-6" />
          All Nodes
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Every active provider on the inference.club network.
        </p>
      </div>
      <button
        class="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 disabled:opacity-50"
        :disabled="isLoading"
        @click="fetchAllProviders"
      >
        <RefreshCw class="h-3.5 w-3.5" :class="{ 'animate-spin': isLoading }" />
        {{ isLoading ? 'Refreshing…' : 'Refresh' }}
      </button>
    </div>

    <div class="grid gap-3 sm:grid-cols-4">
      <Card class="p-4">
        <p class="text-xs uppercase text-muted-foreground tracking-wide">Nodes</p>
        <p class="text-2xl font-semibold mt-1">{{ providers.length }}</p>
      </Card>
      <Card class="p-4">
        <p class="text-xs uppercase text-muted-foreground tracking-wide">Online</p>
        <p
          class="text-2xl font-semibold mt-1"
          :class="onlineCount > 0 ? 'text-green-600 dark:text-green-400' : ''"
        >
          {{ onlineCount }}
        </p>
      </Card>
      <Card class="p-4">
        <p class="text-xs uppercase text-muted-foreground tracking-wide">Operators</p>
        <p class="text-2xl font-semibold mt-1">{{ ownerCount }}</p>
      </Card>
      <Card class="p-4">
        <p class="text-xs uppercase text-muted-foreground tracking-wide">Models served</p>
        <p class="text-2xl font-semibold mt-1">{{ totalModels }}</p>
      </Card>
    </div>

    <div v-if="error" class="p-4 bg-destructive/10 text-destructive rounded text-sm">
      {{ error }}
    </div>

    <div v-if="isLoading && providers.length === 0" class="grid gap-3">
      <Card v-for="i in 3" :key="i" class="p-5 animate-pulse">
        <div class="h-5 bg-muted rounded w-40 mb-3" />
        <div class="h-4 bg-muted rounded w-64" />
      </Card>
    </div>

    <Card v-else-if="providers.length === 0" class="p-6">
      <h3 class="font-semibold mb-2">No active nodes on the network yet</h3>
      <p class="text-sm text-muted-foreground">
        Once operators register agents, they'll appear here.
      </p>
    </Card>

    <div v-else class="grid gap-3">
      <Card
        v-for="provider in providers"
        :key="provider.id"
        class="p-5"
      >
        <div class="flex flex-wrap items-start justify-between gap-3 mb-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <h3 class="font-semibold truncate">{{ provider.name }}</h3>
              <Badge :variant="provider.is_online ? 'default' : 'secondary'">
                <span
                  class="inline-block h-1.5 w-1.5 rounded-full mr-1.5"
                  :class="provider.is_online ? 'bg-green-500' : 'bg-muted-foreground'"
                />
                {{ provider.is_online ? 'online' : 'offline' }}
              </Badge>
              <Badge variant="outline" class="font-mono text-xs">
                @{{ provider.owner }}
              </Badge>
            </div>
            <p class="text-xs text-muted-foreground mt-1 font-mono truncate">
              {{ provider.tailnet_hostname || '(awaiting registration)' }}<template
                v-if="provider.agent_port && provider.agent_port !== 443"
              >:{{ provider.agent_port }}</template>
            </p>
          </div>
          <p class="text-xs text-muted-foreground shrink-0">
            last seen {{ formatRelative(provider.last_seen_at) }}
          </p>
        </div>

        <div class="border-t pt-3">
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
            No models reported yet.
          </p>
        </div>
      </Card>
    </div>
  </div>
</template>
