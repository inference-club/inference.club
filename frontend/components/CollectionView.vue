<script setup lang="ts">
// A collection as other people see it: cover, who made it, one button to play
// it, then its contents grouped by kind (songs as a track list, pictures as a
// gallery, video as a grid, anything else as cards). Used by the share link
// (/c/<token>) and the profile collection page.
import { computed } from 'vue'
import { Play, Pause, Shuffle, Library, Lock } from 'lucide-vue-next'
import type { Collection, InferenceRequest } from '@/types'
import { usePlayerStore } from '@/stores/player'
import { tracksFromRequests, formatRuntime } from '@/utils/player'
import InferenceRequestCard from '@/components/InferenceRequestCard.vue'

const props = defineProps<{
  collection: Collection
  /** Link to share; the current page when omitted. */
  shareUrl?: string
}>()

const { t } = useI18n()
const player = usePlayerStore()
const lightbox = useImageLightbox()

const items = computed<InferenceRequest[]>(() => props.collection.items ?? [])
const songs = computed(() => items.value.filter((r) => r.inference_type === 'MUSIC' && r.output_audio_url))
const tracks = computed(() => tracksFromRequests(songs.value))
const pictures = computed(() =>
  items.value.filter((r) => r.inference_type === 'IMAGE' && r.image_urls?.length),
)
const pictureUrls = computed(() => pictures.value.flatMap((r) => r.image_urls ?? []))
const videos = computed(() => items.value.filter((r) => r.video_url))
const others = computed(() =>
  items.value.filter(
    (r) => !songs.value.includes(r) && !pictures.value.includes(r) && !videos.value.includes(r),
  ),
)
const owner = computed(() => props.collection.github_login || props.collection.owner || '')
const runtime = computed(() =>
  formatRuntime(tracks.value.reduce((s, tr) => s + (tr.duration ?? 0), 0)),
)

// The collection's own cover, else a mosaic of what is inside it.
const mosaic = computed(() => {
  const urls = [
    ...songs.value.map((r) => r.cover_image_url),
    ...pictureUrls.value,
  ].filter((u): u is string => !!u)
  return [...new Set(urls)].slice(0, 4)
})

const playingHere = computed(
  () => player.playing && tracks.value.some((tr) => tr.id === player.current?.id),
)
const playAll = () => {
  if (tracks.value.some((tr) => tr.id === player.current?.id)) player.toggle()
  else player.playQueue(tracks.value, 0)
}
const shuffleAll = () => player.playQueue(tracks.value, -1, { shuffle: true })

// Index of a request's first picture within the flat lightbox list.
const openPicture = (r: InferenceRequest) => {
  const first = r.image_urls?.[0]
  lightbox.openList(pictureUrls.value, Math.max(0, pictureUrls.value.indexOf(first ?? '')))
}
const hidden = computed(() => Math.max(0, props.collection.item_count - items.value.length))
</script>

<template>
  <div class="min-w-0">
    <!-- Hero -->
    <header class="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:gap-6">
      <div class="mx-auto size-44 shrink-0 overflow-hidden rounded-2xl border bg-muted shadow-md sm:mx-0 sm:size-52">
        <img
          v-if="collection.cover_image_url"
          :src="collection.cover_image_url"
          :alt="collection.name"
          class="size-full object-cover"
        />
        <div v-else-if="mosaic.length >= 4" class="grid size-full grid-cols-2">
          <img v-for="u in mosaic" :key="u" :src="u" alt="" class="size-full object-cover" />
        </div>
        <img v-else-if="mosaic.length" :src="mosaic[0]" alt="" class="size-full object-cover" />
        <div v-else class="flex size-full items-center justify-center">
          <Library class="size-12 text-muted-foreground" />
        </div>
      </div>

      <div class="min-w-0 flex-1 text-center sm:text-left">
        <p class="text-xs font-medium uppercase tracking-widest text-muted-foreground">
          {{ t('collectionShare.label') }}
        </p>
        <h1 class="mt-1 text-2xl font-bold tracking-tight break-words sm:text-4xl" data-testid="collection-name">
          {{ collection.name }}
        </h1>
        <p v-if="collection.description" class="mt-2 text-muted-foreground break-words">
          {{ collection.description }}
        </p>
        <p class="mt-2 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-sm text-muted-foreground sm:justify-start">
          <NuxtLink
            v-if="owner"
            :to="`/${owner}`"
            class="inline-flex items-center gap-1.5 font-medium text-foreground hover:underline"
          >
            <img
              v-if="collection.github_login"
              :src="`https://github.com/${collection.github_login}.png?size=48`"
              alt=""
              class="size-5 rounded-full border"
              loading="lazy"
            />
            @{{ owner }}
          </NuxtLink>
          <span v-if="owner" aria-hidden="true">·</span>
          <span>{{ t('collectionShare.items', { n: items.length }, items.length) }}</span>
          <template v-if="runtime"><span aria-hidden="true">·</span><span>{{ runtime }}</span></template>
        </p>
        <div class="mt-4 flex flex-wrap items-center justify-center gap-2 sm:justify-start">
          <Button v-if="tracks.length" class="gap-2 rounded-full" data-testid="collection-play" @click="playAll">
            <component :is="playingHere ? Pause : Play" class="size-4" />
            {{ playingHere ? t('request.pause') : t('media.play') }}
          </Button>
          <Button v-if="tracks.length > 1" variant="outline" class="gap-2 rounded-full" @click="shuffleAll">
            <Shuffle class="size-4" /> {{ t('media.shuffle') }}
          </Button>
          <ShareButton :url="shareUrl" :text="collection.name" size="default" />
        </div>
      </div>
    </header>

    <p v-if="!items.length" class="rounded-2xl border border-dashed py-14 text-center text-muted-foreground">
      {{ t('collectionShare.empty') }}
    </p>

    <!-- Songs -->
    <section v-if="songs.length" class="mb-8">
      <h2 v-if="pictures.length || videos.length || others.length" class="mb-3 text-sm font-semibold">
        {{ t('collectionShare.songs') }}
      </h2>
      <TrackList :tracks="tracks" :requests="songs" />
    </section>

    <!-- Pictures -->
    <section v-if="pictures.length" class="mb-8">
      <h2 v-if="songs.length || videos.length || others.length" class="mb-3 text-sm font-semibold">
        {{ t('collectionShare.pictures') }}
      </h2>
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        <button
          v-for="r in pictures"
          :key="r.id"
          type="button"
          class="group relative aspect-square cursor-zoom-in overflow-hidden rounded-xl border bg-muted"
          :aria-label="r.title || r.prompt_preview || t('request.openImage')"
          @click="openPicture(r)"
        >
          <img
            :src="r.image_urls![0]"
            :alt="r.title || r.prompt_preview || ''"
            class="size-full object-cover transition duration-300 group-hover:scale-105"
            loading="lazy"
          />
          <span
            v-if="r.title || r.prompt_preview"
            class="pointer-events-none absolute inset-x-0 bottom-0 line-clamp-2 bg-gradient-to-t from-black/75 to-transparent px-2.5 pb-2 pt-6 text-left text-xs text-white opacity-0 transition group-hover:opacity-100"
          >{{ r.title || r.prompt_preview }}</span>
        </button>
      </div>
    </section>

    <!-- Video -->
    <section v-if="videos.length" class="mb-8">
      <h2 v-if="songs.length || pictures.length || others.length" class="mb-3 text-sm font-semibold">
        {{ t('collectionShare.videos') }}
      </h2>
      <div class="grid gap-3 sm:grid-cols-2">
        <figure v-for="r in videos" :key="r.id" class="min-w-0">
          <video
            :src="r.video_url!"
            :poster="r.input_image_url || undefined"
            controls
            playsinline
            preload="metadata"
            class="aspect-video w-full rounded-xl border bg-black object-contain"
          />
          <figcaption v-if="r.title || r.prompt_preview" class="mt-1.5 line-clamp-2 text-sm text-muted-foreground">
            {{ r.title || r.prompt_preview }}
          </figcaption>
        </figure>
      </div>
    </section>

    <!-- Everything else -->
    <section v-if="others.length" class="space-y-4">
      <h2 v-if="songs.length || pictures.length || videos.length" class="text-sm font-semibold">
        {{ t('collectionShare.more') }}
      </h2>
      <InferenceRequestCard
        v-for="r in others"
        :key="r.id"
        :request="r"
        :actions="false"
        show-owner
      />
    </section>

    <!-- Owner only: what link holders do not get -->
    <p
      v-if="collection.is_owner && (collection.unshareable_count ?? 0) > 0"
      class="mt-6 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm"
    >
      <Lock class="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
      {{ t('collectionShare.blocked', { n: collection.unshareable_count }, collection.unshareable_count ?? 0) }}
    </p>
    <p v-else-if="!collection.is_owner && hidden > 0" class="mt-6 text-center text-xs text-muted-foreground">
      {{ t('collectionShare.hidden', { n: hidden }, hidden) }}
    </p>
  </div>
</template>
