<script setup lang="ts">
// Music home (docs/prd/06-media-playback-experience.md, phase 3): the
// Spotify-ish surface. Order: a short recently-played strip (client-side), then
// popular albums (collections, ranked by summed song stars), then the full,
// paginated song library.

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Play, Shuffle, Music, Plus, History, Disc3, LogIn, ImagePlus, Sparkles, Loader2,
} from 'lucide-vue-next'
import type { Collection, InferenceRequest } from '@/types'
import { useInferenceRequest } from '@/composables/useInferenceRequest'
import { useContentSharing } from '@/composables/useContentSharing'
import { useAuth } from '@/composables/useAuth'
import { usePagination } from '@/composables/usePagination'
import { usePlayerStore } from '@/stores/player'
import {
  tracksFromRequests, recentlyPlayed, formatRuntime, type PlayerTrack,
} from '@/utils/player'

definePageMeta({ layout: 'app' })

const PAGE_SIZE = 10

const { t } = useI18n()
const { listInferenceRequests, listAllInferenceRequests } = useInferenceRequest()
const { listCollections, missingCoverCount, generateMissingCovers } = useContentSharing()
const { isAuthenticated } = useAuth()
const player = usePlayerStore()

const songs = ref<InferenceRequest[]>([])
const songCount = ref(0)
const albums = ref<Collection[]>([])
const recents = ref<PlayerTrack[]>([])
const loading = ref(true)
const songsTop = ref<HTMLElement | null>(null)

const pagination = usePagination(songCount, PAGE_SIZE)

// Current page's tracks — Play/Shuffle-all queue what's on screen.
const tracks = computed(() => tracksFromRequests(songs.value))
const runtime = computed(() =>
  formatRuntime(tracks.value.reduce((s, tr) => s + (tr.duration ?? 0), 0)),
)

const loadSongs = async (page: number, quiet = false) => {
  // A quiet reload (cover art arriving) must not flash the skeleton.
  if (!quiet) loading.value = true
  const offset = (page - 1) * PAGE_SIZE
  try {
    const res = isAuthenticated.value
      ? await listInferenceRequests(PAGE_SIZE, offset, { type: 'MUSIC' })
      : await listAllInferenceRequests(PAGE_SIZE, offset, {
          type: 'MUSIC',
          sort: 'popular',
        })
    songs.value = (res?.results ?? []).filter(
      (r: InferenceRequest) => r.output_audio_url,
    )
    songCount.value = res?.count ?? songs.value.length
  } finally {
    loading.value = false
  }
}

// --- cover art ---------------------------------------------------------------
// Covers are generated on the server when a song finishes, a few seconds to a
// minute later. While songs on screen are still waiting for theirs, reload the
// page of songs quietly so the art appears without a refresh.
const missingCovers = ref(0)
const makingCovers = ref(false)
let coverPoll: ReturnType<typeof setInterval> | null = null
let coverPollsLeft = 0

const stopCoverPoll = () => {
  if (coverPoll) clearInterval(coverPoll)
  coverPoll = null
  makingCovers.value = false
}

const watchForCovers = (polls = 30) => {
  coverPollsLeft = polls
  if (coverPoll) return
  coverPoll = setInterval(async () => {
    await loadSongs(pagination.currentPage.value, true)
    const waiting = songs.value.some((s) => s.is_owner && !s.cover_image_url)
    if (!waiting || --coverPollsLeft <= 0) {
      stopCoverPoll()
      missingCovers.value = await missingCoverCount().catch(() => 0)
    }
  }, 6000)
}

const makeCovers = async () => {
  makingCovers.value = true
  try {
    const res = await generateMissingCovers(25)
    missingCovers.value = res.missing
    if (res.queued > 0) watchForCovers()
    else makingCovers.value = false
  } catch {
    makingCovers.value = false
  }
}

onBeforeUnmount(stopCoverPoll)

onMounted(async () => {
  recents.value = recentlyPlayed()
  // Albums are owner-scoped — only signed-in members have collections.
  if (isAuthenticated.value) {
    const cols = await listCollections().catch(() => [] as Collection[])
    albums.value = (cols ?? [])
      .filter((c) => (c.audio_count ?? 0) > 0)
      .sort((a, b) => (b.star_total ?? 0) - (a.star_total ?? 0))
      .slice(0, 10)
  }
  await loadSongs(1)
  if (isAuthenticated.value) {
    missingCovers.value = await missingCoverCount().catch(() => 0)
    // A song made in the last few minutes is probably still getting its art.
    const fresh = songs.value.some(
      (s) =>
        s.is_owner &&
        !s.cover_image_url &&
        Date.now() - new Date(s.created_on).getTime() < 5 * 60_000,
    )
    if (fresh) watchForCovers(15)
  }
})

watch(pagination.currentPage, (page) => {
  stopCoverPoll()
  loadSongs(page)
  songsTop.value?.scrollIntoView({ behavior: 'smooth' })
})

const playAll = () => player.playQueue(tracks.value, 0)
const shuffleAll = () => player.playQueue(tracks.value, -1, { shuffle: true })

// Owner clicks empty album art on a collection tile → cover-art modal.
const coverOpen = ref(false)
const coverSlug = ref<string | null>(null)
const openAlbumCover = (col: Collection) => {
  if (!col.is_owner) return
  coverSlug.value = col.slug
  coverOpen.value = true
}
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-3 sm:px-6 py-6">
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">{{ t('media.musicTitle') }}</h1>
        <p class="text-sm text-muted-foreground">
          {{ isAuthenticated ? t('media.musicSubtitle') : t('media.musicSubtitlePublic') }}
        </p>
      </div>
      <NuxtLink v-if="isAuthenticated" to="/dashboard/playground/music">
        <Button class="gap-2">
          <Plus class="size-4" /> {{ t('media.createSong') }}
        </Button>
      </NuxtLink>
      <NuxtLink v-else to="/login">
        <Button class="gap-2">
          <LogIn class="size-4" /> {{ t('media.signInToCreate') }}
        </Button>
      </NuxtLink>
    </div>

    <!-- Recently played (client-side, top 3) -->
    <section v-if="recents.length" class="mb-8">
      <h2 class="mb-3 flex items-center gap-2 text-lg font-semibold">
        <History class="size-5" /> {{ t('media.recentlyPlayed') }}
      </h2>
      <TrackList :tracks="recents.slice(0, 3)" :requests="songs" />
    </section>

    <!-- Popular albums (collections ranked by summed song stars) -->
    <section v-if="albums.length" class="mb-8">
      <h2 class="mb-3 flex items-center gap-2 text-lg font-semibold">
        <Disc3 class="size-5" /> {{ t('media.popularAlbums') }}
      </h2>
      <div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <div v-for="col in albums" :key="col.id" class="group">
          <NuxtLink :to="`/dashboard/inference/collections/${col.slug}`">
            <div class="aspect-square overflow-hidden rounded-xl border bg-muted shadow-sm transition-shadow group-hover:shadow-md">
              <img
                v-if="col.cover_image_url"
                :src="col.cover_image_url"
                class="size-full object-cover transition-transform group-hover:scale-[1.03]"
                :alt="col.name"
                loading="lazy"
              />
              <button
                v-else-if="col.is_owner"
                type="button"
                class="group/art flex size-full flex-col items-center justify-center gap-1 hover:bg-accent/40"
                :title="t('media.generateCover')"
                @click.prevent="openAlbumCover(col)"
              >
                <ImagePlus class="size-7 text-muted-foreground group-hover/art:text-primary" />
                <span class="text-[10px] text-muted-foreground">{{ t('media.generateCover') }}</span>
              </button>
              <div v-else class="flex size-full items-center justify-center">
                <Music class="size-10 text-muted-foreground" />
              </div>
            </div>
          </NuxtLink>
          <p class="mt-2 truncate text-sm font-medium" :title="col.name">{{ col.name }}</p>
          <p class="truncate text-xs text-muted-foreground">
            {{ col.audio_count }} {{ t('media.songs', col.audio_count ?? 0) }}
            <template v-if="formatRuntime(col.total_audio_seconds)">
              · {{ formatRuntime(col.total_audio_seconds) }}
            </template>
          </p>
        </div>
      </div>
    </section>

    <!-- All songs (paginated) -->
    <section ref="songsTop">
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <h2 class="flex items-center gap-2 text-lg font-semibold">
          <Music class="size-5" /> {{ isAuthenticated ? t('media.yourSongs') : t('media.musicFromClub') }}
        </h2>
        <span v-if="songCount" class="text-sm text-muted-foreground">
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

      <div
        v-if="missingCovers > 0 || makingCovers"
        class="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border bg-muted/40 px-3 py-2 text-sm"
        data-testid="missing-covers"
      >
        <span class="min-w-0 flex-1 text-muted-foreground">
          {{ makingCovers ? t('media.makingCovers') : t('media.missingCovers', { n: missingCovers }, missingCovers) }}
        </span>
        <Button
          size="sm"
          variant="outline"
          class="gap-1.5"
          :disabled="makingCovers"
          @click="makeCovers"
        >
          <Loader2 v-if="makingCovers" class="size-4 animate-spin" />
          <Sparkles v-else class="size-4" />
          {{ t('media.makeCovers') }}
        </Button>
      </div>

      <div v-if="loading" class="space-y-2">
        <div v-for="n in 6" :key="n" class="h-14 animate-pulse rounded-xl bg-muted" />
      </div>

      <template v-else>
        <TrackList v-if="tracks.length" :tracks="tracks" :requests="songs" />
        <div v-else-if="isAuthenticated" class="rounded-xl border py-12 text-center text-muted-foreground">
          {{ t('media.noSongsYet') }}
          <NuxtLink to="/dashboard/playground/music" class="underline">
            {{ t('media.createFirstSong') }}
          </NuxtLink>
        </div>
        <div v-else class="rounded-xl border py-12 text-center text-muted-foreground">
          {{ t('media.noPublicSongsYet') }}
        </div>

        <div v-if="pagination.pageCount.value > 1" class="mt-4 flex justify-center">
          <PaginationControls
            :current-page="pagination.currentPage.value"
            :current-page-size="pagination.currentPageSize.value"
            :page-count="pagination.pageCount.value"
            :visible-pages="pagination.visiblePages.value"
            :is-first-page="pagination.isFirstPage.value"
            :is-last-page="pagination.isLastPage.value"
            :prev="pagination.prev"
            :next="pagination.next"
            :on-page-change="(page: number) => { pagination.currentPage.value = page }"
          />
        </div>
      </template>
    </section>

    <GenerateCoverDialog
      v-if="coverSlug"
      v-model:open="coverOpen"
      :target="{ kind: 'collection', slug: coverSlug }"
    />
  </div>
</template>
