<script setup lang="ts">
import {
  Activity, BookOpen, Boxes, Cpu, ExternalLink, Github, Image as ImageIcon, KeyRound, Server, Sparkles, Wrench,
} from 'lucide-vue-next'
import {
  ENGINE_LABELS,
  VENDOR_LABELS,
  type CatalogModelInfo,
  type ManifestModel,
  type OwnerServiceManifest,
  type PublicProfile,
} from '@/composables/useManifest'
import { useInferenceRequest } from '@/composables/useInferenceRequest'
import { useContentSharing } from '@/composables/useContentSharing'
import { usePagination } from '@/composables/usePagination'
import type { Collection, InferenceRequest } from '@/types'
import { useAuthStore } from '@/stores/auth'
import CollectionCard from '@/components/CollectionCard.vue'

const route = useRoute()
const config = useRuntimeConfig()
const auth = useAuthStore()

const username = computed(() => String(route.params.username || ''))

// The public, production API base shown in the "use it" snippets (matches the
// homepage examples), independent of the dev/SSR apiBase used for fetching.
const PUBLIC_API_BASE = 'https://api.inference.club/v1'

// --- inference requests (public, tabbed, paginated) ------------------------
// NOTE: registered BEFORE the top-level `await useFetch` below — lifecycle
// hooks (onMounted/watch) only bind to the component when registered during
// the synchronous part of setup, i.e. before the first await.
const { listPublicUserRequests } = useInferenceRequest()
const reqScope = ref<'consumed' | 'served' | 'bookmarked'>('consumed')
const requests = ref<InferenceRequest[]>([])
const reqCount = ref(0)
const reqLoading = ref(false)
const reqError = ref<string | null>(null)
const reqPager = usePagination(computed(() => reqCount.value), 10)

const loadRequests = async () => {
  if (!username.value) return
  reqLoading.value = true
  reqError.value = null
  try {
    const offset = (reqPager.currentPage.value - 1) * reqPager.currentPageSize.value
    const res = await listPublicUserRequests(
      username.value, reqScope.value, reqPager.currentPageSize.value, offset,
    )
    requests.value = res.results
    reqCount.value = res.count
  } catch (e) {
    reqError.value = e instanceof Error ? e.message : 'Failed to load inference requests'
  } finally {
    reqLoading.value = false
  }
}

// Switching tabs resets to page 1; the combined watcher fires the reload.
watch(reqScope, () => { reqPager.currentPage.value = 1 })
watch([reqScope, reqPager.currentPage], () => { loadRequests() })
onMounted(loadRequests)

// Recently generated images — a quick visual strip at the top of the profile.
const lightbox = useImageLightbox()
const recentImages = ref<{ url: string; id: string; prompt: string }[]>([])
const loadRecentImages = async () => {
  if (!username.value) return
  try {
    const res = await listPublicUserRequests(username.value, 'consumed', 12, 0, { type: 'IMAGE' })
    recentImages.value = res.results
      .flatMap((r) => (r.image_urls ?? []).map((url) => ({
        url, id: String(r.id), prompt: r.prompt_preview || '',
      })))
      .slice(0, 20)
  } catch {
    // non-fatal — the strip just stays hidden if this fails
  }
}
onMounted(loadRecentImages)

// Public collections strip.
const { listPublicCollections } = useContentSharing()
const collections = ref<Collection[]>([])
const loadCollections = async () => {
  if (!username.value) return
  try {
    collections.value = await listPublicCollections(username.value)
  } catch {
    // non-fatal — section stays hidden
  }
}
onMounted(loadCollections)

// During SSR (inside the container) the browser-facing apiBase may be
// unreachable; use the server-only internal base when set.
const apiBase =
  import.meta.server && config.apiBaseInternal
    ? config.apiBaseInternal
    : config.public.apiBase

// Don't use onResponseError — that fires inside ofetch and the thrown
// error gets swallowed by useFetch's own error handling. Instead let
// useFetch swallow non-2xx into ``error`` and convert it to a Nuxt
// fatal-error after the await, so SSR returns the right status code.
const { data, error } = await useFetch<PublicProfile>(
  () => `${apiBase}/api/users/${encodeURIComponent(username.value)}/`,
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

const fmtN = (n: number | null | undefined) => (n ?? 0).toLocaleString()

// --- served models + "use it" CTA ------------------------------------------
const models = computed<CatalogModelInfo[]>(() => data.value?.models ?? [])
const firstModel = computed(() => models.value[0] ?? null)
const playgroundLink = (slug: string) => `/dashboard/playground?model=${encodeURIComponent(slug)}`

// Map a manifest model (declared per host/service) to its catalog entry so the
// node topology can show capabilities + a playground link. The slug is just
// `(hf || id).toLowerCase()` (see slugify_model_id on the backend), which is
// also the catalog slug and the /v1 model id.
const modelByKey = computed(() => {
  const map = new Map<string, CatalogModelInfo>()
  for (const m of models.value) {
    map.set(m.slug, m)
    if (m.hf_repo_id) map.set(m.hf_repo_id.toLowerCase(), m)
  }
  return map
})
const modelSlug = (m: ManifestModel) => (m.hf || m.id || '').trim().toLowerCase()
const catalogFor = (m: ManifestModel) => modelByKey.value.get(modelSlug(m)) ?? null
const modelLabel = (m: ManifestModel) => catalogFor(m)?.display_name || m.id || m.hf || 'model'

// Copy-paste examples for the first served model, reusing the <CodeTabs>
// component. The model id is the slug — what both /v1 and the playground expect.
const snippets = computed(() => {
  const m = firstModel.value?.slug ?? 'MODEL_ID'
  return [
    {
      label: 'curl',
      lang: 'bash',
      code: `curl ${PUBLIC_API_BASE}/chat/completions \\
  -H "Authorization: Bearer $INFERENCE_CLUB_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${m}",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`,
    },
    {
      label: 'python',
      lang: 'python',
      code: `from openai import OpenAI

client = OpenAI(
    base_url="${PUBLIC_API_BASE}",
    api_key="YOUR_INFERENCE_CLUB_API_KEY",
)

resp = client.chat.completions.create(
    model="${m}",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(resp.choices[0].message.content)`,
    },
    {
      label: 'typescript',
      lang: 'typescript',
      code: `import OpenAI from "openai"

const client = new OpenAI({
  baseURL: "${PUBLIC_API_BASE}",
  apiKey: process.env.INFERENCE_CLUB_API_KEY,
})

const resp = await client.chat.completions.create({
  model: "${m}",
  messages: [{ role: "user", content: "Hello!" }],
})
console.log(resp.choices[0].message.content)`,
    },
  ]
})

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

    <!-- recently generated images: a quick visual strip -->
    <section v-if="recentImages.length" class="mb-10">
      <h2 class="font-semibold flex items-center gap-2 mb-3">
        <ImageIcon class="size-4 text-fuchsia-500" /> Recently generated
      </h2>
      <div class="flex gap-3 overflow-x-auto pb-2">
        <img
          v-for="(img, i) in recentImages"
          :key="i"
          :src="img.url"
          :alt="img.prompt"
          :title="img.prompt"
          loading="lazy"
          class="h-40 w-auto shrink-0 cursor-zoom-in rounded-lg border object-cover transition-opacity hover:opacity-90"
          @click="lightbox.open(img.url)"
        />
      </div>
    </section>

    <!-- empty state: no nodes -->
    <div
      v-if="data.providers.length === 0"
      class="mb-10 rounded-lg border bg-card p-10 text-center"
    >
      <p class="text-muted-foreground">
        @{{ data.github_login }} hasn't registered any inference nodes yet.
      </p>
    </div>

    <!-- nodes: one section per agent → hosts → services → models (enriched) -->
    <section
      v-for="provider in data.providers"
      :key="provider.id"
      class="mb-10"
    >
      <div class="flex items-center justify-between gap-3 mb-3">
        <div class="flex items-center gap-2">
          <Server class="size-4 text-muted-foreground" />
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
          <NuxtLink
            v-if="provider.manifest?.parsed.discovery === 'kubernetes'"
            :to="`/${data.github_login}/cluster?provider=${provider.id}`"
            class="inline-flex items-center gap-1 rounded-full bg-sky-500/10 px-2 py-0.5 text-xs font-medium text-sky-600 dark:text-sky-400 hover:bg-sky-500/20"
          >
            <Boxes class="size-3" /> 3D cluster
          </NuxtLink>
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
      <div v-else class="grid gap-4 lg:grid-cols-2">
        <article
          v-for="host in provider.manifest.parsed.hosts"
          :key="host.id"
          class="rounded-lg border bg-card p-5"
        >
          <header class="flex items-start gap-2 mb-3">
            <Server class="size-4 mt-0.5 text-muted-foreground" />
            <div class="flex-1 min-w-0">
              <h3 class="font-medium truncate">{{ host.id }}</h3>
              <p v-if="host.hostname || host.address" class="text-xs text-muted-foreground truncate font-mono">
                <span v-if="host.hostname">{{ host.hostname }}</span>
                <span v-if="host.hostname && host.address"> · </span>
                <span v-if="host.address">{{ host.address }}</span>
              </p>
            </div>
          </header>

          <div v-if="host.gpu" class="flex items-center gap-2 mb-3 text-sm">
            <Cpu class="size-4 text-muted-foreground" />
            <span class="font-medium">{{ host.gpu.model || 'GPU' }}</span>
            <span v-if="host.gpu.vendor" class="rounded bg-muted px-1.5 py-0.5 text-xs">{{ vendorLabel(host.gpu.vendor) }}</span>
            <span v-if="host.gpu.vram_gb" class="text-xs text-muted-foreground">{{ host.gpu.vram_gb }}&thinsp;GB</span>
            <span v-if="host.gpu.count && host.gpu.count > 1" class="text-xs text-muted-foreground">× {{ host.gpu.count }}</span>
          </div>

          <p v-if="host.notes" class="text-xs text-muted-foreground italic mb-3">{{ host.notes }}</p>

          <div v-if="host.services && host.services.length" class="space-y-4 border-t pt-3">
            <div v-for="svc in host.services" :key="svc.name" class="space-y-2">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="rounded bg-primary/10 text-primary px-1.5 py-0.5 text-xs font-medium">{{ engineLabel(svc.engine) }}</span>
                <span class="text-sm font-medium">{{ svc.name }}</span>
              </div>
              <p class="text-xs text-muted-foreground font-mono break-all">{{ svc.url }}</p>

              <!-- models served by this service, enriched with capabilities -->
              <div v-if="svc.models && svc.models.length" class="space-y-2">
                <div
                  v-for="m in svc.models"
                  :key="modelSlug(m)"
                  class="rounded-md border bg-background p-2.5"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span class="font-mono text-xs break-all min-w-0">{{ modelLabel(m) }}</span>
                    <NuxtLink
                      v-if="modelSlug(m)"
                      :to="playgroundLink(modelSlug(m))"
                      class="shrink-0 inline-flex items-center gap-1 text-xs text-primary hover:underline underline-offset-4"
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
                <template v-for="(value, key) in svc.extra" :key="key">
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

    <!-- inference requests: tabbed (made / served), paginated -->
    <section class="mb-10">
      <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h2 class="font-semibold flex items-center gap-2">
          <Activity class="size-4 text-sky-500" /> Inference requests
          <span v-if="reqCount" class="text-sm font-normal text-muted-foreground">({{ fmtN(reqCount) }})</span>
        </h2>
        <div class="inline-flex rounded-md border p-0.5 text-sm">
          <button
            class="px-3 py-1 rounded"
            :class="reqScope === 'consumed' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'"
            @click="reqScope = 'consumed'"
          >
            Made
          </button>
          <button
            class="px-3 py-1 rounded"
            :class="reqScope === 'served' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'"
            @click="reqScope = 'served'"
          >
            Served
          </button>
          <button
            class="px-3 py-1 rounded"
            :class="reqScope === 'bookmarked' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'"
            @click="reqScope = 'bookmarked'"
          >
            Bookmarked
          </button>
        </div>
      </div>

      <div v-if="reqLoading && requests.length === 0" class="space-y-3">
        <Card v-for="i in 3" :key="i" class="p-4 animate-pulse">
          <div class="space-y-3 w-full">
            <div class="flex items-center gap-2">
              <div class="h-6 w-20 bg-muted rounded" />
              <div class="h-6 w-24 bg-muted rounded" />
            </div>
            <div class="h-4 bg-muted rounded w-3/4" />
            <div class="h-4 bg-muted rounded w-1/2" />
          </div>
        </Card>
      </div>

      <div v-else-if="reqError" class="text-destructive text-sm text-center py-6">
        {{ reqError }}
      </div>

      <div
        v-else-if="requests.length === 0"
        class="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground"
      >
        <template v-if="reqScope === 'bookmarked'">@{{ data.github_login }} hasn't bookmarked any requests yet.</template>
        <template v-else>@{{ data.github_login }} hasn't {{ reqScope === 'consumed' ? 'made' : 'served' }} any inference requests yet.</template>
      </div>

      <div v-else class="space-y-3">
        <InferenceRequestCard
          v-for="r in requests"
          :key="r.id"
          :request="r"
          :linkable="true"
          :show-owner="reqScope !== 'consumed'"
        />
        <PaginationControls
          v-if="reqPager.pageCount.value > 1"
          :current-page="reqPager.currentPage.value"
          :current-page-size="reqPager.currentPageSize.value"
          :page-count="reqPager.pageCount.value"
          :visible-pages="reqPager.visiblePages.value"
          :is-first-page="reqPager.isFirstPage.value"
          :is-last-page="reqPager.isLastPage.value"
          :prev="reqPager.prev"
          :next="reqPager.next"
          :on-page-change="(page) => { reqPager.currentPage.value = page }"
        />
      </div>
    </section>

    <!-- collections -->
    <section v-if="collections.length" class="mb-10">
      <h2 class="font-semibold flex items-center gap-2 mb-3">
        <Boxes class="size-4 text-primary" /> Collections
        <span class="text-sm font-normal text-muted-foreground">({{ collections.length }})</span>
      </h2>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <CollectionCard
          v-for="col in collections"
          :key="col.slug"
          :collection="col"
          :to="`/${username}/collections/${col.slug}`"
        />
      </div>
    </section>

    <!-- activity: provided compute + consumed inference -->
    <section v-if="data.stats" class="mb-10 grid gap-5">
      <div class="rounded-lg border bg-card p-5">
        <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
          <h2 class="font-semibold flex items-center gap-2">
            <Cpu class="size-4 text-emerald-500" /> Compute provided
          </h2>
          <p class="text-sm text-muted-foreground">
            <strong class="text-foreground">{{ fmtN(data.stats.provider.lifetime.requests) }}</strong>
            requests served ·
            <strong class="text-foreground">{{ fmtN(data.stats.provider.lifetime.total_tokens) }}</strong>
            tokens
          </p>
        </div>
        <ContributionHeatmap :data="data.stats.provider.daily" scheme="emerald" />
      </div>

      <div class="rounded-lg border bg-card p-5">
        <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
          <h2 class="font-semibold flex items-center gap-2">
            <Activity class="size-4 text-sky-500" /> Inference used
          </h2>
          <p class="text-sm text-muted-foreground">
            <strong class="text-foreground">{{ fmtN(data.stats.consumer.lifetime.requests) }}</strong>
            requests ·
            <strong class="text-foreground">{{ fmtN(data.stats.consumer.lifetime.total_tokens) }}</strong>
            tokens
            <span class="whitespace-nowrap">
              ({{ fmtN(data.stats.consumer.lifetime.prompt_tokens) }} in /
              {{ fmtN(data.stats.consumer.lifetime.completion_tokens) }} out)
            </span>
          </p>
        </div>
        <ContributionHeatmap :data="data.stats.consumer.daily" scheme="sky" />
      </div>
    </section>

    <!-- use these models: CTA + API usage snippets (moved to the bottom) -->
    <section v-if="models.length" class="mb-10 rounded-lg border bg-card p-5">
      <div class="flex flex-wrap items-start justify-between gap-3 mb-5">
        <div>
          <h2 class="font-semibold flex items-center gap-2">
            <Boxes class="size-4 text-primary" />
            Models @{{ data.github_login }} is serving
          </h2>
          <p class="text-sm text-muted-foreground mt-1">
            Run them free in the playground or from your own code via the OpenAI-compatible API.
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <NuxtLink
            v-if="firstModel"
            :to="playgroundLink(firstModel.slug)"
            class="inline-flex items-center gap-1.5 rounded-md bg-primary text-primary-foreground px-3 py-1.5 text-sm font-medium hover:bg-primary/90"
          >
            <Sparkles class="size-4" /> Open in Playground
          </NuxtLink>
          <NuxtLink
            to="/dashboard/settings/token"
            class="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent"
          >
            <KeyRound class="size-4" /> Get an API key
          </NuxtLink>
          <NuxtLink
            to="/docs/quickstart"
            class="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent"
          >
            <BookOpen class="size-4" /> Docs
          </NuxtLink>
        </div>
      </div>

      <CodeTabs :snippets="snippets" filename="POST /chat/completions" />
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
