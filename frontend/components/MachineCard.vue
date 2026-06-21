<script setup lang="ts">
// A single machine, richly visualized: form-factor header + online state,
// a relative memory gauge, the GPU chip, and a stack of service modules — each
// with its engine's brand logo, modality, and the models it serves. One Spark
// or RTX box can run several services; they stack as distinct modules here.
//
// Used on the public profile and across the Compute tab. Pass `catalog` to
// enrich models with capabilities + playground deep-links (profile/owner views);
// omit it for lighter list contexts.
import { Cpu, Sparkles, Wrench } from 'lucide-vue-next'
import {
  VENDOR_LABELS,
  type CatalogModelInfo,
  type ManifestHost,
  type ManifestModel,
} from '@/composables/useManifest'
import { engineBrand, modalityType } from '@/composables/useEngines'
import { machineForm, prettyGpuModel } from '@/composables/useMachineForm'

const props = withDefaults(
  defineProps<{
    host: ManifestHost
    // Largest memory among the machines shown, for the relative gauge.
    maxMemoryGb?: number
    online?: boolean
    // When set, models are enriched (capabilities + playground links).
    catalog?: CatalogModelInfo[]
    // Owner view — reveals the launch command per service.
    showCommand?: boolean
  }>(),
  { maxMemoryGb: 0, online: undefined, catalog: undefined, showCommand: false },
)

const form = computed(() => machineForm(props.host))
const services = computed(() => props.host.services ?? [])

const vendorLabel = (v?: string) => (v ? VENDOR_LABELS[v] ?? v : '')

// model enrichment (same slug rule as the backend: (hf || id).toLowerCase())
const modelByKey = computed(() => {
  const map = new Map<string, CatalogModelInfo>()
  for (const m of props.catalog ?? []) {
    map.set(m.slug, m)
    if (m.hf_repo_id) map.set(m.hf_repo_id.toLowerCase(), m)
  }
  return map
})
const modelSlug = (m: ManifestModel) => (m.hf || m.id || '').trim().toLowerCase()
const catalogFor = (m: ManifestModel) =>
  props.catalog ? modelByKey.value.get(modelSlug(m)) ?? null : null
const modelLabel = (m: ManifestModel) =>
  catalogFor(m)?.display_name || m.id || m.hf || 'model'
const playgroundLink = (slug: string) =>
  `/dashboard/playground?model=${encodeURIComponent(slug)}`
</script>

<template>
  <article class="rounded-xl border bg-card overflow-hidden">
    <!-- header: form-factor + identity + online -->
    <header class="flex items-start gap-3 px-4 pt-4">
      <div
        class="flex size-9 shrink-0 items-center justify-center rounded-lg"
        :style="{ backgroundColor: `${form.accent}1f`, color: form.accent }"
      >
        <component :is="form.icon" class="size-5" />
      </div>
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2">
          <h3 class="truncate font-semibold leading-tight">{{ host.id }}</h3>
          <span
            v-if="online !== undefined"
            class="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
            :class="online
              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
              : 'bg-muted text-muted-foreground'"
          >
            <span class="size-1.5 rounded-full" :class="online ? 'bg-emerald-500' : 'bg-muted-foreground/50'" />
            {{ online ? 'online' : 'offline' }}
          </span>
        </div>
        <p
          v-if="host.hostname || host.address"
          class="truncate font-mono text-xs text-muted-foreground"
        >
          <span v-if="host.hostname">{{ host.hostname }}</span>
          <span v-if="host.hostname && host.address"> · </span>
          <span v-if="host.address">{{ host.address }}</span>
        </p>
      </div>
      <!-- service-count chip: makes multi-service boxes (Spark/RTX) obvious -->
      <span
        v-if="services.length"
        class="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
      >
        {{ services.length }} service{{ services.length === 1 ? '' : 's' }}
      </span>
    </header>

    <!-- memory + GPU -->
    <div class="space-y-3 px-4 py-3">
      <MemoryBar
        v-if="host.gpu?.vram_gb"
        :gb="host.gpu.vram_gb"
        :max-gb="maxMemoryGb"
        :unified="form.unified"
        :color="form.accent"
      />
      <div v-if="host.gpu" class="flex flex-wrap items-center gap-1.5 text-xs">
        <span
          class="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5"
          :style="{ borderColor: `${form.accent}55` }"
        >
          <Cpu class="size-3" :style="{ color: form.accent }" />
          <span class="font-medium">{{ prettyGpuModel(host.gpu.model) }}</span>
        </span>
        <span v-if="host.gpu.vendor" class="rounded-md bg-muted px-1.5 py-0.5 text-muted-foreground">
          {{ vendorLabel(host.gpu.vendor) }}
        </span>
        <span v-if="host.gpu.count && host.gpu.count > 1" class="rounded-md bg-muted px-1.5 py-0.5 text-muted-foreground">
          × {{ host.gpu.count }}
        </span>
      </div>
      <p v-if="host.notes" class="text-xs italic text-muted-foreground">{{ host.notes }}</p>
    </div>

    <!-- service modules -->
    <div v-if="services.length" class="divide-y border-t">
      <div v-for="svc in services" :key="svc.name" class="px-4 py-3">
        <div class="flex items-center gap-2.5">
          <EngineLogo :engine="svc.engine" :size="30" />
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="truncate text-sm font-medium">{{ svc.name }}</span>
              <ModalityBadge :type="(modalityType(svc.type) as any)" />
            </div>
            <p class="truncate font-mono text-[11px] text-muted-foreground">
              {{ engineBrand(svc.engine).label }}<span v-if="svc.url"> · {{ svc.url }}</span>
            </p>
          </div>
        </div>

        <!-- models served by this service -->
        <div v-if="svc.models && svc.models.length" class="mt-2.5 space-y-2 pl-[42px]">
          <div
            v-for="m in svc.models"
            :key="modelSlug(m)"
            class="rounded-lg border bg-background p-2.5"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="min-w-0 break-all font-mono text-xs">{{ modelLabel(m) }}</span>
              <NuxtLink
                v-if="catalog && modelSlug(m)"
                :to="playgroundLink(modelSlug(m))"
                class="inline-flex shrink-0 items-center gap-1 text-xs text-primary underline-offset-4 hover:underline"
              >
                <Sparkles class="size-3" /> playground
              </NuxtLink>
            </div>
            <ModelCapabilities
              v-if="catalogFor(m)"
              class="mt-2"
              :context-length="catalogFor(m)?.context_length"
              :input-modalities="catalogFor(m)?.input_modalities"
              :supported-features="catalogFor(m)?.supported_features"
            />
          </div>
        </div>

        <details v-if="showCommand && svc.command" class="group mt-2 pl-[42px]">
          <summary class="inline-flex cursor-pointer items-center gap-1 text-xs text-muted-foreground">
            <Wrench class="size-3" /> command
          </summary>
          <pre class="mt-1 overflow-auto whitespace-pre-wrap rounded bg-muted/60 p-2 font-mono text-xs">{{ svc.command }}</pre>
        </details>
      </div>
    </div>
    <p v-else class="border-t px-4 py-3 text-xs italic text-muted-foreground">
      no services configured on this host
    </p>
  </article>
</template>
