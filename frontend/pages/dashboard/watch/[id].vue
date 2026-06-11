<script setup lang="ts">
// YouTube-style watch page (docs/prd/06-media-playback-experience.md, phase 4):
// big player + metadata, and — with ?list=<collection-slug> — an up-next panel
// over the collection's ordered video items with autoplay-next.

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  ArrowLeft, Shuffle, SkipForward, Clapperboard, ChevronDown, ChevronUp,
} from 'lucide-vue-next'
import type { Collection, InferenceRequest } from '@/types'
import { useInferenceRequest } from '@/composables/useInferenceRequest'
import { useContentSharing } from '@/composables/useContentSharing'
import { formatRelative } from '@/utils/inference'

definePageMeta({ layout: 'app' })

const { t } = useI18n()
const route = useRoute()
const { getInferenceRequest } = useInferenceRequest()
const { getCollection } = useContentSharing()

const requestId = computed(() => String(route.params.id))
const listSlug = computed(() => {
  const v = route.query.list
  return typeof v === 'string' && v ? v : null
})

const request = ref<InferenceRequest | null>(null)
const collection = ref<Collection | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const autoplayNext = ref(true)
const shuffle = ref(false)
const detailsOpen = ref(false)

const playlist = computed<InferenceRequest[]>(() =>
  (collection.value?.items ?? []).filter((r) => r.video_url),
)
const currentIndex = computed(() =>
  playlist.value.findIndex((r) => String(r.id) === requestId.value),
)

const promptText = computed(() => {
  const r = request.value
  if (!r) return ''
  const payloadPrompt =
    typeof r.payload?.prompt === 'string' ? (r.payload.prompt as string) : ''
  return r.prompt_preview || payloadPrompt || ''
})

const loadRequest = async () => {
  loading.value = true
  error.value = null
  try {
    request.value = await getInferenceRequest(requestId.value)
    if (!request.value?.video_url) {
      error.value = t('media.notAVideo')
    }
  } catch {
    error.value = t('media.videoNotFound')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadRequest()
  if (listSlug.value) {
    try {
      collection.value = await getCollection(listSlug.value)
    } catch {
      collection.value = null // list is best-effort; the video still plays
    }
  }
})

// Same component instance handles next/prev — reload on id change.
watch(requestId, loadRequest)

const goTo = (r: InferenceRequest) => {
  navigateTo({
    path: `/dashboard/watch/${r.id}`,
    query: listSlug.value ? { list: listSlug.value } : {},
  })
}

const pickNext = (): InferenceRequest | null => {
  const list = playlist.value
  if (!list.length) return null
  if (shuffle.value) {
    const others = list.filter((r) => String(r.id) !== requestId.value)
    if (!others.length) return null
    return others[Math.floor(Math.random() * others.length)]
  }
  const i = currentIndex.value
  return i >= 0 && i < list.length - 1 ? list[i + 1] : null
}

const next = () => {
  const n = pickNext()
  if (n) goTo(n)
}

const onEnded = () => {
  if (autoplayNext.value && listSlug.value) next()
}

useHead(() => ({
  title: promptText.value ? `${promptText.value.slice(0, 60)} · Watch` : 'Watch',
}))
</script>

<template>
  <div class="mx-auto w-full max-w-7xl px-3 sm:px-6 py-6">
    <NuxtLink
      :to="listSlug ? `/dashboard/inference/collections/${listSlug}` : '/dashboard/inference/requests'"
      class="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft class="size-4" />
      {{ listSlug && collection ? collection.name : t('media.backToRequests') }}
    </NuxtLink>

    <div v-if="loading" class="aspect-video w-full animate-pulse rounded-xl bg-muted" />
    <div v-else-if="error" class="py-16 text-center text-muted-foreground">{{ error }}</div>

    <div v-else-if="request" class="grid gap-6 lg:grid-cols-[1fr_360px]">
      <!-- Main player column -->
      <div class="min-w-0">
        <video
          :key="request.id"
          :src="request.video_url ?? undefined"
          :poster="request.input_image_url ?? undefined"
          controls
          autoplay
          playsinline
          class="aspect-video w-full rounded-xl border bg-black object-contain"
          data-testid="watch-video"
          @ended="onEnded"
        />

        <div class="mt-4">
          <h1 class="break-words text-lg font-semibold leading-snug">
            {{ promptText || t('media.untitledVideo') }}
          </h1>
          <div class="mt-2 flex flex-wrap items-center gap-3">
            <span v-if="request.github_login || request.owner" class="text-sm text-muted-foreground">
              {{ request.github_login || request.owner }}
            </span>
            <span class="text-sm text-muted-foreground">
              {{ formatRelative(request.created_on) }}
            </span>
            <div class="ml-auto">
              <RequestActionBar :request="request" />
            </div>
          </div>

          <!-- Generation details, collapsed by default -->
          <button
            class="mt-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
            @click="detailsOpen = !detailsOpen"
          >
            <component :is="detailsOpen ? ChevronUp : ChevronDown" class="size-4" />
            {{ t('media.generationDetails') }}
          </button>
          <Card v-if="detailsOpen" class="mt-2 p-4 text-sm">
            <dl class="grid gap-x-6 gap-y-2 sm:grid-cols-2">
              <div v-if="request.model_name" class="flex justify-between gap-3">
                <dt class="text-muted-foreground">Model</dt>
                <dd class="break-all font-mono text-xs">{{ request.model_name }}</dd>
              </div>
              <div v-if="request.video?.width && request.video?.height" class="flex justify-between gap-3">
                <dt class="text-muted-foreground">Resolution</dt>
                <dd>{{ request.video.width }}×{{ request.video.height }}</dd>
              </div>
              <div v-if="request.video?.fps" class="flex justify-between gap-3">
                <dt class="text-muted-foreground">FPS</dt>
                <dd>{{ request.video.fps }}</dd>
              </div>
              <div v-if="request.video?.seconds" class="flex justify-between gap-3">
                <dt class="text-muted-foreground">Duration</dt>
                <dd>{{ request.video.seconds }}s</dd>
              </div>
              <div v-if="request.video?.seed != null" class="flex justify-between gap-3">
                <dt class="text-muted-foreground">Seed</dt>
                <dd class="font-mono text-xs">{{ request.video.seed }}</dd>
              </div>
              <div v-if="request.provider" class="flex justify-between gap-3">
                <dt class="text-muted-foreground">Provider</dt>
                <dd>{{ request.provider.name }}</dd>
              </div>
            </dl>
          </Card>
        </div>
      </div>

      <!-- Up next (playlist mode) -->
      <aside v-if="listSlug && playlist.length" class="min-w-0">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="flex min-w-0 items-center gap-2 text-sm font-semibold">
            <Clapperboard class="size-4 shrink-0" />
            <span class="truncate">{{ collection?.name || t('media.upNext') }}</span>
            <span v-if="currentIndex >= 0" class="shrink-0 text-xs text-muted-foreground">
              {{ currentIndex + 1 }}/{{ playlist.length }}
            </span>
          </h2>
          <div class="flex shrink-0 items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              class="size-8"
              :class="shuffle ? 'text-primary' : 'text-muted-foreground'"
              :title="t('media.shuffle')"
              @click="shuffle = !shuffle"
            >
              <Shuffle class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              class="size-8 text-muted-foreground"
              :title="t('media.next')"
              :disabled="!pickNext()"
              data-testid="watch-next"
              @click="next"
            >
              <SkipForward class="size-4" />
            </Button>
          </div>
        </div>

        <label class="mb-3 flex items-center gap-2 text-sm text-muted-foreground">
          <Switch v-model="autoplayNext" />
          {{ t('media.autoplayNext') }}
        </label>

        <div class="space-y-2">
          <button
            v-for="(r, i) in playlist"
            :key="r.id"
            type="button"
            class="flex w-full items-center gap-3 rounded-lg border p-2 text-left transition-colors hover:bg-accent/50"
            :class="String(r.id) === requestId ? 'border-primary/50 bg-accent/40' : ''"
            :data-testid="`up-next-${i}`"
            @click="goTo(r)"
          >
            <span class="w-5 shrink-0 text-center text-xs tabular-nums text-muted-foreground">
              {{ i + 1 }}
            </span>
            <div class="relative aspect-video w-28 shrink-0 overflow-hidden rounded-md border bg-black">
              <img
                v-if="r.input_image_url"
                :src="r.input_image_url"
                class="size-full object-cover"
                loading="lazy"
                alt=""
              />
              <div v-else class="flex size-full items-center justify-center">
                <Clapperboard class="size-5 text-muted-foreground" />
              </div>
            </div>
            <div class="min-w-0">
              <p class="line-clamp-2 text-sm">{{ r.prompt_preview || '—' }}</p>
              <p class="mt-0.5 truncate text-xs text-muted-foreground">
                {{ r.github_login || r.owner }}
              </p>
            </div>
          </button>
        </div>
      </aside>
    </div>
  </div>
</template>
