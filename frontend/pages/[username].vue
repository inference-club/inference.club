<script setup lang="ts">
import { Cpu, ExternalLink, Github, Server, Wrench } from 'lucide-vue-next'
import {
  ENGINE_LABELS,
  VENDOR_LABELS,
  type OwnerServiceManifest,
  type PublicProfile,
} from '@/composables/useManifest'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const config = useRuntimeConfig()
const auth = useAuthStore()

const username = computed(() => String(route.params.username || ''))

// Don't use onResponseError — that fires inside ofetch and the thrown
// error gets swallowed by useFetch's own error handling. Instead let
// useFetch swallow non-2xx into ``error`` and convert it to a Nuxt
// fatal-error after the await, so SSR returns the right status code.
const { data, error } = await useFetch<PublicProfile>(
  () => `${config.public.apiBase}/api/users/${encodeURIComponent(username.value)}/`,
  { credentials: 'include' },
)

if (error.value) {
  const status = (error.value as { statusCode?: number }).statusCode ?? 500
  throw createError({
    statusCode: status === 404 ? 404 : 500,
    statusMessage:
      status === 404
        ? `No inference.club profile for @${username.value}`
        : 'Failed to load profile',
    fatal: true,
  })
}

useHead({
  title: () => (data.value ? `@${data.value.github_login} — inference.club` : 'inference.club'),
})

const isOwner = computed(
  () => auth.isAuthenticated && auth.user?.github_login === data.value?.github_login,
)

const formatJoined = (iso: string) => {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}

const totalGPUs = computed(() => {
  if (!data.value) return 0
  let n = 0
  for (const p of data.value.providers) {
    for (const h of p.manifest?.parsed.hosts ?? []) {
      n += h.gpu?.count ?? (h.gpu ? 1 : 0)
    }
  }
  return n
})

const totalServices = computed(() => {
  if (!data.value) return 0
  let n = 0
  for (const p of data.value.providers) {
    for (const h of p.manifest?.parsed.hosts ?? []) {
      n += (h.services ?? []).length
    }
  }
  return n
})

// Owner-only raw YAML modal
const showRawModal = ref(false)
const rawManifest = ref<OwnerServiceManifest | null>(null)
const rawError = ref<string | null>(null)
const rawLoading = ref(false)

const openRawModal = async (providerId: number) => {
  showRawModal.value = true
  rawError.value = null
  rawManifest.value = null
  rawLoading.value = true
  try {
    rawManifest.value = await $fetch<OwnerServiceManifest>(
      `${config.public.apiBase}/api/inference/providers/${providerId}/manifest/`,
      { credentials: 'include' },
    )
  } catch (e: unknown) {
    rawError.value = e instanceof Error ? e.message : String(e)
  } finally {
    rawLoading.value = false
  }
}

const engineLabel = (e: string) => ENGINE_LABELS[e] ?? e
const vendorLabel = (v?: string) => (v ? VENDOR_LABELS[v] ?? v : '')
</script>

<template>
  <main v-if="data" class="container mx-auto max-w-5xl px-4 py-10">
    <!-- profile header -->
    <header class="flex items-start gap-5 mb-10">
      <img
        v-if="data.avatar_url"
        :src="data.avatar_url"
        :alt="data.github_login"
        class="size-20 rounded-full ring-1 ring-border"
      >
      <div class="flex-1 min-w-0">
        <h1 class="text-2xl font-semibold leading-tight truncate">
          {{ data.name || data.github_login }}
        </h1>
        <a
          v-if="data.github_url"
          :href="data.github_url"
          target="_blank"
          rel="noopener noreferrer"
          class="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <Github class="size-3.5" />
          @{{ data.github_login }}
          <ExternalLink class="size-3" />
        </a>
        <p class="text-xs text-muted-foreground mt-1">
          joined {{ formatJoined(data.joined) }}
        </p>
      </div>
      <div class="hidden sm:flex flex-col items-end text-sm text-muted-foreground">
        <span><strong class="text-foreground">{{ data.providers.length }}</strong> agent{{ data.providers.length === 1 ? '' : 's' }}</span>
        <span><strong class="text-foreground">{{ totalGPUs }}</strong> GPU{{ totalGPUs === 1 ? '' : 's' }}</span>
        <span><strong class="text-foreground">{{ totalServices }}</strong> service{{ totalServices === 1 ? '' : 's' }}</span>
      </div>
    </header>

    <!-- empty state -->
    <div
      v-if="data.providers.length === 0"
      class="rounded-lg border bg-card p-10 text-center"
    >
      <p class="text-muted-foreground">
        @{{ data.github_login }} hasn't registered any inference nodes yet.
      </p>
    </div>

    <!-- one section per provider/agent -->
    <section
      v-for="provider in data.providers"
      :key="provider.id"
      class="mb-10"
    >
      <div class="flex items-center justify-between gap-3 mb-3">
        <div class="flex items-center gap-2">
          <h2 class="text-lg font-semibold">{{ provider.name }}</h2>
          <span
            class="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium"
            :class="provider.is_online
              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
              : 'bg-muted text-muted-foreground'"
          >
            <span
              class="size-1.5 rounded-full"
              :class="provider.is_online ? 'bg-emerald-500' : 'bg-muted-foreground/50'"
            />
            {{ provider.is_online ? 'online' : 'offline' }}
          </span>
        </div>
        <button
          v-if="isOwner && provider.manifest"
          class="text-xs text-muted-foreground hover:text-foreground underline-offset-4 hover:underline"
          @click="openRawModal(provider.id)"
        >
          View raw manifest
        </button>
      </div>

      <!-- no manifest yet -->
      <div
        v-if="!provider.manifest"
        class="rounded-lg border bg-card p-6 text-sm text-muted-foreground"
      >
        No manifest uploaded for this agent yet.
      </div>

      <!-- hosts grid -->
      <div
        v-else
        class="grid gap-4 sm:grid-cols-2"
      >
        <article
          v-for="host in provider.manifest.parsed.hosts"
          :key="host.id"
          class="rounded-lg border bg-card p-5"
        >
          <header class="flex items-start gap-2 mb-3">
            <Server class="size-4 mt-0.5 text-muted-foreground" />
            <div class="flex-1 min-w-0">
              <h3 class="font-medium truncate">{{ host.id }}</h3>
              <p v-if="host.hostname || host.address" class="text-xs text-muted-foreground truncate">
                <span v-if="host.hostname">{{ host.hostname }}</span>
                <span v-if="host.hostname && host.address"> · </span>
                <span v-if="host.address">{{ host.address }}</span>
              </p>
            </div>
          </header>

          <div
            v-if="host.gpu"
            class="flex items-center gap-2 mb-3 text-sm"
          >
            <Cpu class="size-4 text-muted-foreground" />
            <span class="font-medium">{{ host.gpu.model || 'GPU' }}</span>
            <span
              v-if="host.gpu.vendor"
              class="rounded bg-muted px-1.5 py-0.5 text-xs"
            >{{ vendorLabel(host.gpu.vendor) }}</span>
            <span
              v-if="host.gpu.vram_gb"
              class="text-xs text-muted-foreground"
            >{{ host.gpu.vram_gb }}&thinsp;GB</span>
            <span
              v-if="host.gpu.count && host.gpu.count > 1"
              class="text-xs text-muted-foreground"
            >× {{ host.gpu.count }}</span>
          </div>

          <p v-if="host.notes" class="text-xs text-muted-foreground italic mb-3">
            {{ host.notes }}
          </p>

          <div v-if="host.services && host.services.length" class="space-y-3 border-t pt-3">
            <div
              v-for="svc in host.services"
              :key="svc.name"
              class="space-y-1.5"
            >
              <div class="flex items-center gap-2 flex-wrap">
                <span
                  class="rounded bg-primary/10 text-primary px-1.5 py-0.5 text-xs font-medium"
                >{{ engineLabel(svc.engine) }}</span>
                <span class="text-sm font-medium">{{ svc.name }}</span>
              </div>
              <p class="text-xs text-muted-foreground font-mono break-all">{{ svc.url }}</p>
              <div
                v-if="svc.models && svc.models.length"
                class="flex flex-wrap gap-1.5 pt-0.5"
              >
                <span
                  v-for="m in svc.models"
                  :key="m.id"
                  class="rounded border px-1.5 py-0.5 text-xs font-mono"
                >{{ m.id }}</span>
              </div>
              <details v-if="svc.command" class="group">
                <summary class="text-xs text-muted-foreground cursor-pointer inline-flex items-center gap-1">
                  <Wrench class="size-3" />
                  command
                </summary>
                <pre class="mt-1 rounded bg-muted/60 p-2 text-xs overflow-auto whitespace-pre-wrap font-mono">{{ svc.command }}</pre>
              </details>
              <dl
                v-if="svc.extra && Object.keys(svc.extra).length"
                class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs"
              >
                <template
                  v-for="(value, key) in svc.extra"
                  :key="key"
                >
                  <dt class="text-muted-foreground font-mono">{{ key }}</dt>
                  <dd class="font-mono break-all">{{ value }}</dd>
                </template>
              </dl>
            </div>
          </div>
          <p v-else class="text-xs text-muted-foreground italic border-t pt-3">
            no services configured on this host
          </p>
        </article>
      </div>
    </section>

    <!-- owner-only raw YAML modal -->
    <div
      v-if="showRawModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4"
      @click.self="showRawModal = false"
    >
      <div class="bg-card border rounded-lg shadow-lg max-w-3xl w-full max-h-[80vh] flex flex-col">
        <div class="flex items-center justify-between px-5 py-3 border-b">
          <h3 class="font-medium">Raw manifest</h3>
          <button
            class="text-muted-foreground hover:text-foreground text-sm"
            @click="showRawModal = false"
          >
            Close
          </button>
        </div>
        <div class="flex-1 overflow-auto p-5">
          <p v-if="rawLoading" class="text-sm text-muted-foreground">loading…</p>
          <p v-else-if="rawError" class="text-sm text-destructive">{{ rawError }}</p>
          <template v-else-if="rawManifest">
            <p class="text-xs text-muted-foreground mb-2">
              uploaded {{ new Date(rawManifest.uploaded_at).toLocaleString() }}
              · schema v{{ rawManifest.schema_version }}
              <span
                v-if="!rawManifest.is_valid"
                class="ml-2 rounded bg-destructive/15 text-destructive px-1.5 py-0.5"
              >validation failed</span>
            </p>
            <ul
              v-if="rawManifest.validation_errors.length"
              class="text-xs text-destructive mb-3 list-disc pl-5 space-y-0.5"
            >
              <li v-for="(e, i) in rawManifest.validation_errors" :key="i">{{ e }}</li>
            </ul>
            <pre class="rounded bg-muted/60 p-3 text-xs overflow-auto font-mono whitespace-pre-wrap">{{ rawManifest.raw_yaml || '(empty raw_yaml)' }}</pre>
          </template>
        </div>
      </div>
    </div>
  </main>

</template>
