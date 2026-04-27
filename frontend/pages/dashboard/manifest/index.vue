<script setup lang="ts">
import { CheckCircle2, AlertCircle } from 'lucide-vue-next'
import { useProviders } from '@/composables/useProviders'

definePageMeta({
  layout: 'app',
})

const { providers, isLoading, error, fetchProviders } = useProviders()
onMounted(fetchProviders)

const formatRelative = (iso: string | null) => {
  if (!iso) return 'never'
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return new Date(iso).toLocaleString()
}
</script>

<template>
  <div class="container mx-auto p-6 max-w-4xl">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold">Service manifests</h1>
        <p class="text-sm text-muted-foreground mt-1">
          The YAML each agent has uploaded. Edit
          <code class="text-foreground">agent.yaml</code> on the agent host and
          <code class="text-foreground">docker kill -s HUP club-host</code> to reload.
        </p>
      </div>
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

    <div
      v-if="!isLoading && providers.length === 0"
      class="p-6 bg-card rounded-lg border"
    >
      <p class="text-muted-foreground">
        No agents registered yet.
        <NuxtLink to="/dashboard/providers/my-nodes" class="underline">
          Register an agent
        </NuxtLink> to get started.
      </p>
    </div>

    <div class="space-y-4">
      <article
        v-for="provider in providers"
        :key="provider.id"
        class="rounded-lg border bg-card overflow-hidden"
      >
        <header class="flex items-center justify-between px-5 py-3 border-b">
          <div class="flex items-center gap-3">
            <h2 class="font-semibold">{{ provider.name }}</h2>
            <span
              v-if="provider.manifest"
              class="inline-flex items-center gap-1 text-xs"
              :class="provider.manifest.is_valid ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'"
            >
              <CheckCircle2 v-if="provider.manifest.is_valid" class="size-3.5" />
              <AlertCircle v-else class="size-3.5" />
              {{ provider.manifest.is_valid ? 'valid' : 'invalid' }}
            </span>
          </div>
          <p v-if="provider.manifest" class="text-xs text-muted-foreground">
            uploaded {{ formatRelative(provider.manifest.uploaded_at) }} · schema v{{ provider.manifest.schema_version }}
          </p>
        </header>

        <div v-if="!provider.manifest" class="px-5 py-4 text-sm text-muted-foreground">
          No manifest uploaded. The agent's older config-by-env-vars setup still works,
          but uploading a manifest enables the public profile view.
        </div>

        <template v-else>
          <ul
            v-if="provider.manifest.validation_errors.length"
            class="px-5 py-3 bg-destructive/5 border-b text-xs text-destructive list-disc pl-9 space-y-0.5"
          >
            <li
              v-for="(e, i) in provider.manifest.validation_errors"
              :key="i"
            >
              {{ e }}
            </li>
          </ul>

          <pre
            v-if="provider.manifest.raw_yaml"
            class="px-5 py-4 text-xs font-mono overflow-auto whitespace-pre"
          >{{ provider.manifest.raw_yaml }}</pre>
          <p
            v-else
            class="px-5 py-4 text-xs text-muted-foreground italic"
          >
            (raw YAML empty — manifest was synthesized from env vars)
          </p>
        </template>
      </article>
    </div>
  </div>
</template>
