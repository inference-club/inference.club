<script setup lang="ts">
// Videos home — the YouTube-ish counterpart to /dashboard/music: your video
// playlists (collections containing videos) and a responsive thumbnail grid
// of your generated videos. No persistent player; cards open /dashboard/watch/:id.

import { onMounted, ref } from 'vue'
import { Clapperboard, ListVideo, Plus } from 'lucide-vue-next'
import type { Collection, InferenceRequest } from '@/types'
import { useInferenceRequest } from '@/composables/useInferenceRequest'
import { useContentSharing } from '@/composables/useContentSharing'

definePageMeta({ layout: 'app' })

const { t } = useI18n()
const { listInferenceRequests } = useInferenceRequest()
const { listCollections } = useContentSharing()

const videos = ref<InferenceRequest[]>([])
const videoCount = ref(0)
const playlists = ref<Collection[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const [videosRes, cols] = await Promise.all([
      listInferenceRequests(50, 0, { type: 'VIDEO' }),
      listCollections().catch(() => [] as Collection[]),
    ])
    videos.value = (videosRes?.results ?? []).filter(
      (r: InferenceRequest) => r.video_url,
    )
    videoCount.value = videosRes?.count ?? videos.value.length
    playlists.value = (cols ?? []).filter((c) => (c.video_count ?? 0) > 0)
  } finally {
    loading.value = false
  }
})

useHead({ title: 'Videos' })
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-3 sm:px-6 py-6">
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">{{ t('media.videosTitle') }}</h1>
        <p class="text-sm text-muted-foreground">
          {{ t('media.videosSubtitle') }}
        </p>
      </div>
      <NuxtLink to="/dashboard/playground/videos">
        <Button class="gap-2">
          <Plus class="size-4" /> {{ t('media.createVideo') }}
        </Button>
      </NuxtLink>
    </div>

    <div v-if="loading" class="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
      <div v-for="i in 6" :key="i">
        <div class="aspect-video animate-pulse rounded-xl bg-muted" />
        <div class="mt-2 h-4 w-3/4 animate-pulse rounded bg-muted" />
      </div>
    </div>

    <template v-else>
      <!-- Playlists (collections containing videos) -->
      <section v-if="playlists.length" class="mb-8">
        <h2 class="mb-3 flex items-center gap-2 text-lg font-semibold">
          <ListVideo class="size-5" /> {{ t('media.yourPlaylists') }}
        </h2>
        <div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          <NuxtLink
            v-for="col in playlists"
            :key="col.id"
            :to="`/dashboard/inference/collections/${col.slug}`"
            class="group"
          >
            <div class="aspect-video overflow-hidden rounded-xl border bg-muted shadow-sm transition-shadow group-hover:shadow-md">
              <img
                v-if="col.cover_image_url"
                :src="col.cover_image_url"
                class="size-full object-cover transition-transform group-hover:scale-[1.03]"
                :alt="col.name"
                loading="lazy"
              />
              <div v-else class="flex size-full items-center justify-center">
                <Clapperboard class="size-8 text-muted-foreground" />
              </div>
            </div>
            <p class="mt-2 truncate text-sm font-medium" :title="col.name">{{ col.name }}</p>
            <p class="truncate text-xs text-muted-foreground">
              {{ col.video_count }} {{ t('media.videos', col.video_count ?? 0) }}
            </p>
          </NuxtLink>
        </div>
      </section>

      <!-- All your videos -->
      <section>
        <div class="mb-3 flex flex-wrap items-center gap-3">
          <h2 class="flex items-center gap-2 text-lg font-semibold">
            <Clapperboard class="size-5" /> {{ t('media.yourVideos') }}
          </h2>
          <span v-if="videos.length" class="text-sm text-muted-foreground">
            {{ videoCount }} {{ t('media.videos', videoCount) }}
          </span>
        </div>

        <div
          v-if="videos.length"
          class="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2 lg:grid-cols-3"
          data-testid="video-grid"
        >
          <VideoCard v-for="r in videos" :key="r.id" :request="r" />
        </div>
        <div v-else class="rounded-xl border py-12 text-center text-muted-foreground">
          {{ t('media.noVideosYet') }}
          <NuxtLink to="/dashboard/playground/videos" class="underline">
            {{ t('media.createFirstVideo') }}
          </NuxtLink>
        </div>
      </section>
    </template>
  </div>
</template>
