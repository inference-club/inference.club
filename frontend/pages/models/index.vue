<script setup lang="ts">
import { useProviders } from '@/composables/useProviders'

definePageMeta({
  layout: 'default',
})

const { aggregatedModels, isLoading, error, fetchProviders } = useProviders()

onMounted(fetchProviders)
</script>

<template>
  <div class="container mx-auto p-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">Available Models</h1>
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

    <div v-if="!isLoading && aggregatedModels.length === 0" class="p-6 bg-card rounded-lg border">
      <h2 class="text-xl font-semibold mb-2">No models available</h2>
      <p class="text-muted-foreground">
        No online providers are advertising any models. Bring up an
        <code>inference-club-agent</code> on a machine running an LLM server, then refresh.
      </p>
    </div>

    <div class="grid gap-3">
      <div
        v-for="m in aggregatedModels"
        :key="m.name"
        class="p-4 bg-card rounded-lg border flex items-center justify-between"
      >
        <span class="font-mono">{{ m.name }}</span>
        <span class="text-sm text-muted-foreground">
          served by {{ m.providers.join(', ') }}
        </span>
      </div>
    </div>
  </div>
</template>
