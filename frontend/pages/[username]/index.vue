<script setup lang="ts">
import {
  Activity, BookOpen, Box, Boxes, Clapperboard, Cpu, ExternalLink, Github, Image as ImageIcon, KeyRound, MessageSquare, Music, Server, Sparkles, VenetianMask,
} from 'lucide-vue-next'
import type { Ref } from 'vue'
import type {
  CatalogModelInfo,
  OwnerServiceManifest,
  PublicProfile,
} from '@/composables/useManifest'
import { useInferenceRequest } from '@/composables/useInferenceRequest'
import { useContentSharing } from '@/composables/useContentSharing'
import { tracksFromRequests } from '@/utils/player'
import type { Collection, InferenceRequest } from '@/types'
import { useAuthStore } from '@/stores/auth'
import CollectionCard from '@/components/CollectionCard.vue'

const route = useRoute()
const config = useRuntimeConfig()
const auth = useAuthStore()

const username = computed(() => String(route.params.username || ''))

// Deterministic identicon hue for accounts without a (GitHub) avatar.
const identiconColor = computed(() => {
  const source = data.value?.handle || username.value
  let hash = 0
  for (const ch of source) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return `hsl(${hash % 360} 55% 45%)`
})

// The public, production API base shown in the "use it" snippets (matches the
// homepage examples), independent of the dev/SSR apiBase used for fetching.
const PUBLIC_API_BASE = 'https://api.inference.club/v1'

// --- featured content by modality (public, most recent) --------------------
// The profile leads with the owner's creative output, one row per modality:
// images · videos · songs · 3D models · LLM chats. Each is an independent
// best-effort fetch off the public per-handle requests endpoint (?type=…); an
// empty or failing modality simply hides its section. Registered BEFORE the
// top-level `await useFetch` below so the onMounted hook binds to the component
// (lifecycle hooks only bind during the synchronous part of setup).
const { listPublicUserRequests } = useInferenceRequest()
const lightbox = useImageLightbox()

const MODALITY_LIMIT = 12

const imageReqs = ref<InferenceRequest[]>([])
const videoReqs = ref<InferenceRequest[]>([])
const songReqs = ref<InferenceRequest[]>([])
const modelReqs = ref<InferenceRequest[]>([])
const chatReqs = ref<InferenceRequest[]>([])

// A single IMAGE request can yield several images — flatten to tiles for the
// horizontal strip, capped so a prolific generator doesn't blow out the row.
const imageTiles = computed(() =>
  imageReqs.value
    .flatMap((r) => (r.image_urls ?? []).map((url) => ({
      url, id: String(r.id), prompt: r.prompt_preview || '',
    })))
    .slice(0, 20),
)

// MUSIC requests → player tracks for the global bar (Spotify-style rows).
const songTracks = computed(() => tracksFromRequests(songReqs.value))

const loadModality = async (
  type: string,
  target: Ref<InferenceRequest[]>,
  keep?: (r: InferenceRequest) => boolean,
) => {
  if (!username.value) return
  try {
    const res = await listPublicUserRequests(
      username.value, 'consumed', MODALITY_LIMIT, 0, { type },
    )
    target.value = keep ? res.results.filter(keep) : res.results
  } catch {
    // non-fatal — the section just stays hidden if this fails
  }
}

onMounted(() => {
  loadModality('IMAGE', imageReqs, (r) => !!r.image_urls?.length)
  loadModality('VIDEO', videoReqs, (r) => !!r.video_url)
  loadModality('MUSIC', songReqs, (r) => !!r.output_audio_url)
  loadModality('MESH', modelReqs, (r) => !!r.model_url)
  loadModality('LLM', chatReqs)
})

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

// Largest machine memory across the whole profile — the reference the relative
// memory gauges on each MachineCard size themselves against.
const maxMemoryGb = computed(() => {
  let max = 0
  for (const p of data.value?.providers ?? []) {
    for (const h of p.manifest?.parsed.hosts ?? []) {
      if (h.gpu?.vram_gb) max = Math.max(max, h.gpu.vram_gb)
    }
  }
  return max
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

const fmtN = (n: number | null | undefined) => (n ?? 0).toLocaleString()

// --- served models + "use it" CTA ------------------------------------------
const models = computed<CatalogModelInfo[]>(() => data.value?.models ?? [])
const firstModel = computed(() => models.value[0] ?? null)
const playgroundLink = (slug: string) => `/dashboard/playground?model=${encodeURIComponent(slug)}`

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
      <!-- Identicon for anonymous/aliased accounts: deterministic hue from the
           handle, never an avatar that could identify anyone. -->
      <div
        v-else
        class="flex size-20 shrink-0 items-center justify-center rounded-full ring-1 ring-border text-white font-semibold text-xl"
        :style="{ backgroundColor: identiconColor }"
      >
        {{ (data.handle || data.github_login || '?').slice(0, 2).toUpperCase() }}
      </div>
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
        <!-- Provenance badge without a link: GitHub-verified (aliased) or anonymous. -->
        <span
          v-else
          class="inline-flex items-center gap-1.5 text-sm text-muted-foreground"
          :title="data.account_badge === 'github'
            ? 'GitHub-verified account going by an alias'
            : 'Anonymous account'"
        >
          <Github v-if="data.account_badge === 'github'" class="size-3.5" />
          <VenetianMask v-else class="size-3.5" />
          @{{ data.handle || data.github_login }}
          <span class="text-xs">
            · {{ data.account_badge === 'github' ? 'GitHub account' : 'anonymous' }}
          </span>
        </span>
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

    <!-- featured content by modality: images · videos · songs · 3D · chats -->
    <section v-if="imageTiles.length" class="mb-10">
      <h2 class="font-semibold flex items-center gap-2 mb-3">
        <ImageIcon class="size-4 text-fuchsia-500" /> Images
      </h2>
      <div class="flex gap-3 overflow-x-auto pb-2">
        <img
          v-for="(img, i) in imageTiles"
          :key="i"
          :src="img.url"
          :alt="img.prompt"
          :title="img.prompt"
          loading="lazy"
          class="h-40 w-auto shrink-0 cursor-zoom-in rounded-lg border object-cover transition-opacity hover:opacity-90"
          @click="lightbox.open(img.url)"
        >
      </div>
    </section>

    <section v-if="videoReqs.length" class="mb-10">
      <h2 class="font-semibold flex items-center gap-2 mb-3">
        <Clapperboard class="size-4 text-rose-500" /> Videos
      </h2>
      <div class="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <VideoCard v-for="r in videoReqs" :key="r.id" :request="r" />
      </div>
    </section>

    <section v-if="songTracks.length" class="mb-10">
      <h2 class="font-semibold flex items-center gap-2 mb-3">
        <Music class="size-4 text-emerald-500" /> Songs
      </h2>
      <TrackList :tracks="songTracks" :requests="songReqs" />
    </section>

    <section v-if="modelReqs.length" class="mb-10">
      <h2 class="font-semibold flex items-center gap-2 mb-3">
        <Box class="size-4 text-amber-500" /> 3D models
      </h2>
      <div class="grid gap-4 sm:grid-cols-2">
        <InferenceRequestCard
          v-for="r in modelReqs"
          :key="r.id"
          :request="r"
          :linkable="true"
        />
      </div>
    </section>

    <section v-if="chatReqs.length" class="mb-10">
      <h2 class="font-semibold flex items-center gap-2 mb-3">
        <MessageSquare class="size-4 text-sky-500" /> LLM chats
      </h2>
      <div class="grid gap-3 sm:grid-cols-2">
        <InferenceRequestCard
          v-for="r in chatReqs"
          :key="r.id"
          :request="r"
          :linkable="true"
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

      <!-- machines grid: the new resource + service visualization -->
      <div v-else>
        <ProviderMachineGrid
          :provider-id="provider.id"
          :hosts="provider.manifest.parsed.hosts"
          :discovery="provider.manifest.parsed.discovery"
          :max-memory-gb="maxMemoryGb"
          :online="provider.is_online"
          :catalog="models"
          :show-command="isOwner"
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
