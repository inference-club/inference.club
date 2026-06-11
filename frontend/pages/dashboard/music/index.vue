<script setup lang="ts">
// Music home (docs/prd/06-media-playback-experience.md, phase 3): the
// Spotify-ish surface — your songs, your playlists (collections with music),
// and a client-side recently-played strip.

import { computed, onMounted, ref } from 'vue'
import { Play, Shuffle, Music, Plus, History, ListMusic } from 'lucide-vue-next'
import type { Collection, InferenceRequest } from '@/types'
import { useInferenceRequest } from '@/composables/useInferenceRequest'
import { useContentSharing } from '@/composables/useContentSharing'
import { usePlayerStore } from '@/stores/player'
import {
  tracksFromRequests, recentlyPlayed, formatRuntime, type PlayerTrack,
} from '@/utils/player'

definePageMeta({ layout: 'app' })

const { t } = useI18n()
const { listInferenceRequests } = useInferenceRequest()
const { listCollections } = useContentSharing()
const player = usePlayerStore()

const songs = ref<InferenceRequest[]>([])
const songCount = ref(0)
const playlists = ref<Collection[]>([])
const recents = ref<PlayerTrack[]>([])
const loading = ref(true)

const tracks = computed(() => tracksFromRequests(songs.value))
const runtime = computed(() =>
  formatRuntime(tracks.value.reduce((s, tr) => s + (tr.duration ?? 0), 0)),
)

onMounted(async () => {
  recents.value = recentlyPlayed()
  try {
    const [songsRes, cols] = await Promise.all([
      listInferenceRequests(50, 0, { type: 'MUSIC' }),
      listCollections().catch(() => [] as Collection[]),
    ])
    songs.value = (songsRes?.results ?? []).filter(
      (r: InferenceRequest) => r.output_audio_url,
    )
    songCount.value = songsRes?.count ?? songs.value.length
    playlists.value = (cols ?? []).filter((c) => (c.audio_count ?? 0) > 0)
  } finally {
    loading.value = false
  }
})

const playAll = () => player.playQueue(tracks.value, 0)
const shuffleAll = () => player.playQueue(tracks.value, -1, { shuffle: true })
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-4 sm:px-6 py-6">
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">{{ t('media.musicTitle') }}</h1>
        <p class="text-sm text-muted-foreground">
          {{ t('media.musicSubtitle') }}
        </p>
      </div>
      <NuxtLink to="/dashboard/playground/music">
        <Button class="gap-2">
          <Plus class="size-4" /> {{ t('media.createSong') }}
        </Button>
      </NuxtLink>
    </div>

    <div v-if="loading" class="space-y-4">
      <div class="h-8 w-48 animate-pulse rounded bg-muted" />
      <Card class="h-48 animate-pulse p-4" />
    </div>

    <template v-else>
      <!-- Playlists (collections containing music) -->
      <section v-if="playlists.length" class="mb-8">
        <h2 class="mb-3 flex items-center gap-2 text-lg font-semibold">
          <ListMusic class="size-5" /> {{ t('media.yourPlaylists') }}
        </h2>
        <div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          <NuxtLink
            v-for="col in playlists"
            :key="col.id"
            :to="`/dashboard/inference/collections/${col.slug}`"
            class="group"
          >
            <div class="aspect-square overflow-hidden rounded-xl border bg-muted shadow-sm transition-shadow group-hover:shadow-md">
              <img
                v-if="col.cover_image_url"
                :src="col.cover_image_url"
                class="size-full object-cover transition-transform group-hover:scale-[1.03]"
                :alt="col.name"
                loading="lazy"
              />
              <div v-else class="flex size-full items-center justify-center">
                <Music class="size-10 text-muted-foreground" />
              </div>
            </div>
            <p class="mt-2 truncate text-sm font-medium" :title="col.name">{{ col.name }}</p>
            <p class="truncate text-xs text-muted-foreground">
              {{ col.audio_count }} {{ t('media.songs', col.audio_count ?? 0) }}
              <template v-if="formatRuntime(col.total_audio_seconds)">
                · {{ formatRuntime(col.total_audio_seconds) }}
              </template>
            </p>
          </NuxtLink>
        </div>
      </section>

      <!-- Recently played (client-side) -->
      <section v-if="recents.length" class="mb-8">
        <h2 class="mb-3 flex items-center gap-2 text-lg font-semibold">
          <History class="size-5" /> {{ t('media.recentlyPlayed') }}
        </h2>
        <TrackList :tracks="recents.slice(0, 8)" />
      </section>

      <!-- All your songs -->
      <section>
        <div class="mb-3 flex flex-wrap items-center gap-3">
          <h2 class="flex items-center gap-2 text-lg font-semibold">
            <Music class="size-5" /> {{ t('media.yourSongs') }}
          </h2>
          <span v-if="tracks.length" class="text-sm text-muted-foreground">
            {{ songCount }} {{ t('media.songs', songCount) }}<template v-if="runtime"> · {{ runtime }}</template>
          </span>
          <div v-if="tracks.length" class="ml-auto flex gap-2">
            <Button class="gap-2 rounded-full" data-testid="music-play-all" @click="playAll">
              <Play class="size-4" /> {{ t('media.play') }}
            </Button>
            <Button
              v-if="tracks.length > 1"
              variant="outline"
              class="gap-2 rounded-full"
              data-testid="music-shuffle-all"
              @click="shuffleAll"
            >
              <Shuffle class="size-4" /> {{ t('media.shuffle') }}
            </Button>
          </div>
        </div>

        <TrackList v-if="tracks.length" :tracks="tracks" />
        <div v-else class="rounded-xl border py-12 text-center text-muted-foreground">
          {{ t('media.noSongsYet') }}
          <NuxtLink to="/dashboard/playground/music" class="underline">
            {{ t('media.createFirstSong') }}
          </NuxtLink>
        </div>
      </section>
    </template>
  </div>
</template>
