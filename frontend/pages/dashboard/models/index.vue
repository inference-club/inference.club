<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Boxes,
  Brain,
  ExternalLink,
  Eye,
  Mic,
  Type,
  Video,
  Wrench,
} from 'lucide-vue-next'
import { useModelCatalog, type CatalogModelItem } from '@/composables/useModelCatalog'

definePageMeta({ layout: 'app' })

const { models, loading, error, fetchModels } = useModelCatalog()

const search = ref('')
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return models.value
  return models.value.filter(
    (m) =>
      m.slug.includes(q) ||
      m.display_name.toLowerCase().includes(q) ||
      m.hf_repo_id.toLowerCase().includes(q)
  )
})

const MODALITY_ICONS: Record<string, { icon: unknown; label: string }> = {
  text: { icon: Type, label: 'Text' },
  image: { icon: Eye, label: 'Image' },
  audio: { icon: Mic, label: 'Audio' },
  video: { icon: Video, label: 'Video' },
}
const FEATURE_ICONS: Record<string, { icon: unknown; label: string }> = {
  reasoning: { icon: Brain, label: 'Reasoning' },
  tools: { icon: Wrench, label: 'Tools' },
}

const fmtCtx = (n: number | null) => {
  if (!n) return null
  if (n >= 1000) return `${Math.round(n / 1024)}K ctx`
  return `${n} ctx`
}

// Offline/retired deployments are hidden by default (data quality); the toggle
// brings them back, marked with a gray dot.
const showOffline = ref(false)
const toggleOffline = () => {
  showOffline.value = !showOffline.value
  fetchModels(showOffline.value)
}
onMounted(() => fetchModels(false))
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-3 sm:px-6 py-6">
    <div class="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2">
          <Boxes class="h-6 w-6" /> Models
        </h1>
        <p class="text-sm text-muted-foreground mt-1">
          Every model available across the network, with the capabilities and nodes
          serving it. Call any of these by its id from the API or the
          <NuxtLink to="/dashboard/playground" class="underline">playground</NuxtLink>.
        </p>
      </div>
      <div class="flex w-full items-center gap-3 sm:w-auto">
        <button
          type="button"
          class="inline-flex shrink-0 items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent"
          :class="showOffline ? 'bg-accent text-foreground' : ''"
          :title="showOffline ? 'Hide offline / retired nodes' : 'Show offline / retired nodes'"
          @click="toggleOffline"
        >
          <span class="size-2 rounded-full" :class="showOffline ? 'bg-muted-foreground/50' : 'bg-green-500'" />
          {{ showOffline ? 'Showing offline' : 'Online only' }}
        </button>
        <Input v-model="search" placeholder="Filter models…" class="w-full sm:w-64" />
      </div>
    </div>

    <div v-if="loading && !models.length" class="grid gap-3 sm:grid-cols-2">
      <Card v-for="i in 4" :key="i" class="h-40 animate-pulse" />
    </div>

    <div v-else-if="error" class="p-4 bg-destructive/10 text-destructive rounded text-sm">
      {{ error }}
    </div>

    <Card v-else-if="!models.length" class="p-6">
      <h3 class="font-semibold mb-1">No models yet</h3>
      <p class="text-sm text-muted-foreground">
        Once a node comes online and reports the models it serves, they'll appear here.
      </p>
    </Card>

    <div v-else class="grid gap-3 sm:grid-cols-2">
      <Card v-for="m in filtered" :key="m.slug" class="p-4 flex flex-col gap-3 min-w-0">
        <!-- Header -->
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <h3 class="font-semibold truncate" :title="m.display_name">{{ m.display_name }}</h3>
            <code class="text-xs text-muted-foreground break-all">{{ m.slug }}</code>
          </div>
          <a
            v-if="m.hf_url"
            :href="m.hf_url"
            target="_blank"
            rel="noopener"
            class="shrink-0 text-muted-foreground hover:text-foreground"
            title="View on HuggingFace"
          >
            <ExternalLink class="size-4" />
          </a>
        </div>

        <!-- Capability badges -->
        <div class="flex flex-wrap items-center gap-1.5">
          <Badge v-if="m.is_custom" variant="outline">custom</Badge>
          <Badge v-if="fmtCtx(m.context_length)" variant="secondary" class="font-mono">
            {{ fmtCtx(m.context_length) }}
          </Badge>
          <span
            v-for="mod in m.input_modalities"
            :key="mod"
            class="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-xs"
            :title="`Input: ${MODALITY_ICONS[mod]?.label || mod}`"
          >
            <component :is="MODALITY_ICONS[mod]?.icon || Type" class="size-3" />
            {{ MODALITY_ICONS[mod]?.label || mod }}
          </span>
          <span
            v-for="f in m.supported_features"
            :key="f"
            class="inline-flex items-center gap-1 rounded bg-primary/10 text-primary px-1.5 py-0.5 text-xs"
          >
            <component :is="FEATURE_ICONS[f]?.icon || Wrench" class="size-3" />
            {{ FEATURE_ICONS[f]?.label || f }}
          </span>
        </div>

        <!-- Meta -->
        <div class="text-xs text-muted-foreground space-y-1 mt-auto">
          <div class="flex items-center gap-3">
            <span class="inline-flex items-center gap-1.5">
              <span class="relative flex size-2" aria-hidden="true">
                <span
                  v-if="m.online_provider_count > 0"
                  class="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-500 opacity-75"
                />
                <span
                  class="relative inline-flex size-2 rounded-full"
                  :class="m.online_provider_count > 0 ? 'bg-green-500' : 'bg-muted-foreground/40'"
                />
              </span>
              {{ m.online_provider_count }}/{{ m.provider_count }}
              node{{ m.provider_count === 1 ? '' : 's' }} online
            </span>
          </div>
          <div v-if="m.providers.length" class="truncate" :title="m.providers.map((p) => p.name).join(', ')">
            {{ m.providers.map((p) => p.name).join(', ') }}
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>
