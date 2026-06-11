<script setup lang="ts">
// YouTube-style grid card for a VIDEO request: 16:9 thumbnail (the input
// image when present, else the video's first frame), duration badge, prompt
// as title, owner + age, and star/bookmark quick actions. Clicking opens the
// watch page — no inline playback here.

import { computed, ref } from 'vue'
import { Clapperboard } from 'lucide-vue-next'
import type { InferenceRequest } from '@/types'
import { formatRelative } from '@/utils/inference'
import { formatTrackTime } from '@/utils/player'

const props = defineProps<{
  request: InferenceRequest
  /** Appended as ?list= so the watch page shows the playlist's up-next panel. */
  listSlug?: string
}>()

const { t } = useI18n()

// First-frame thumbnails need a <video preload="metadata"> — defer that
// network hit until the card is near the viewport (same pattern as
// InferenceRequestCard; <img> gets it natively via loading="lazy").
const mediaEl = ref<HTMLElement | null>(null)
const mediaInView = useInView(mediaEl)

const title = computed(() => {
  const payloadPrompt =
    typeof props.request.payload?.prompt === 'string'
      ? (props.request.payload.prompt as string)
      : ''
  return (props.request.prompt_preview || payloadPrompt || '').trim()
})

const to = computed(() => ({
  path: `/dashboard/watch/${props.request.id}`,
  query: props.listSlug ? { list: props.listSlug } : {},
}))
</script>

<template>
  <div class="group min-w-0">
    <NuxtLink :to="to" class="block" :data-testid="`video-card-${request.id}`">
      <div
        ref="mediaEl"
        class="relative aspect-video w-full overflow-hidden rounded-xl border bg-black"
      >
        <img
          v-if="request.input_image_url"
          :src="request.input_image_url"
          class="size-full object-cover transition-transform group-hover:scale-[1.02]"
          loading="lazy"
          alt=""
        />
        <video
          v-else-if="mediaInView && request.video_url"
          :src="request.video_url"
          preload="metadata"
          muted
          playsinline
          tabindex="-1"
          class="pointer-events-none size-full object-cover"
        />
        <div v-else class="flex size-full items-center justify-center">
          <Clapperboard class="size-8 text-muted-foreground" />
        </div>
        <span
          v-if="request.video?.seconds"
          class="absolute bottom-1.5 right-1.5 rounded bg-black/80 px-1.5 py-0.5 text-xs tabular-nums text-white"
        >
          {{ formatTrackTime(request.video.seconds) }}
        </span>
      </div>
    </NuxtLink>

    <div class="mt-2 flex items-start gap-1">
      <div class="min-w-0 flex-1">
        <NuxtLink
          :to="to"
          class="line-clamp-2 text-sm font-medium leading-snug hover:underline"
          :title="title"
        >
          {{ title || t('media.untitledVideo') }}
        </NuxtLink>
        <p class="mt-0.5 truncate text-xs text-muted-foreground">
          <template v-if="request.github_login || request.owner">
            {{ request.github_login || request.owner }} ·
          </template>
          {{ formatRelative(request.created_on) }}
        </p>
      </div>
      <RequestQuickActions :request="request" />
    </div>
  </div>
</template>
