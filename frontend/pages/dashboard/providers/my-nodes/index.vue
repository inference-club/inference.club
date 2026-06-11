<script setup lang="ts">
import { toast } from 'vue-sonner'
import { useProviders, type Provider } from '@/composables/useProviders'

definePageMeta({
  layout: 'app',
})

const { providers, isLoading, error, fetchProviders, refreshModels, setAcceptingRequests } = useProviders()

onMounted(fetchProviders)

const togglePause = async (p: Provider) => {
  const next = !p.accepting_requests
  try {
    await setAcceptingRequests(p.id, next)
    toast.success(next ? `"${p.name}" is accepting requests` : `"${p.name}" paused — no longer serving`)
  } catch {
    toast.error('Failed to update node')
  }
}

const formatRelative = (iso: string | null) => {
  if (!iso) return 'never'
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  return new Date(iso).toLocaleString()
}
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-4 sm:px-6 py-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">My Inference Nodes</h1>
      <button
        class="text-sm text-muted-foreground hover:text-foreground"
        :disabled="isLoading"
        @click="fetchProviders"
      >
        {{ isLoading ? 'Refreshing…' : 'Refresh' }}
      </button>
    </div>

    <div v-if="error" class="p-4 mb-4 bg-destructive/10 text-destructive rounded">
      {{ error }}
    </div>

    <div v-if="!isLoading && providers.length === 0" class="p-6 bg-card rounded-lg border">
      <h2 class="text-xl font-semibold mb-2">No nodes yet</h2>
      <p class="text-muted-foreground mb-2">
        Run <code class="text-foreground">inference-club-agent</code> on a machine with an LLM server, configured with
        your inference.club API key. The agent will join the inference.club Tailscale network and register here automatically.
      </p>
      <p class="text-muted-foreground">
        Get an API key at
        <NuxtLink to="/dashboard/settings/token" class="underline">
          Dashboard → Settings → Token
        </NuxtLink>. See
        <NuxtLink to="/docs/providers/run-an-agent" class="underline">
          the agent guide
        </NuxtLink> for setup.
      </p>
    </div>

    <div class="grid gap-4">
      <div
        v-for="provider in providers"
        :key="provider.id"
        class="p-6 bg-card rounded-lg border"
      >
        <div class="flex items-start justify-between mb-3">
          <div>
            <div class="flex items-center gap-3">
              <h2 class="text-xl font-semibold">{{ provider.name }}</h2>
              <span
                :class="provider.is_online
                  ? 'bg-green-500/20 text-green-700 dark:text-green-400'
                  : 'bg-muted text-muted-foreground'"
                class="px-2 py-0.5 text-xs rounded-full"
              >
                {{ provider.is_online ? 'online' : 'offline' }}
              </span>
              <span
                v-if="!provider.accepting_requests"
                class="px-2 py-0.5 text-xs rounded-full bg-amber-500/20 text-amber-700 dark:text-amber-400"
              >
                paused
              </span>
            </div>
            <p class="text-sm text-muted-foreground mt-1 font-mono">
              {{ provider.tailnet_hostname || '(awaiting registration)' }}<template v-if="provider.agent_port && provider.agent_port !== 443">:{{ provider.agent_port }}</template>
            </p>
          </div>
          <div class="text-right">
            <p class="text-xs text-muted-foreground">
              last seen: {{ formatRelative(provider.last_seen_at) }}
            </p>
            <button
              class="text-xs text-muted-foreground hover:text-foreground mt-1 block ml-auto"
              :disabled="isLoading"
              @click="refreshModels(provider.id)"
            >
              {{ isLoading ? '…' : 'Refresh models' }}
            </button>
            <button
              class="text-xs mt-1 block ml-auto"
              :class="provider.accepting_requests
                ? 'text-muted-foreground hover:text-amber-600'
                : 'text-amber-600 hover:text-amber-700 font-medium'"
              @click="togglePause(provider)"
            >
              {{ provider.accepting_requests ? 'Pause node' : 'Resume node' }}
            </button>
          </div>
        </div>

        <div v-if="provider.models.length > 0">
          <p class="text-xs uppercase text-muted-foreground mb-2">Models</p>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="m in provider.models"
              :key="m.id"
              class="px-2 py-1 text-xs rounded bg-muted font-mono"
            >
              {{ m.name }}<template v-if="m.context_window">
                <span class="text-muted-foreground"> · {{ m.context_window }} ctx</span>
              </template>
            </span>
          </div>
        </div>
        <p v-else class="text-sm text-muted-foreground italic">
          No models reported. Click "Refresh models" once the agent is online to discover them.
        </p>
      </div>
    </div>
  </div>
</template>
