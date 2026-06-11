<script setup lang="ts">
// Presentation-first card for the home-page featured showcase: big media, one
// quiet metadata line (who prompted it, whose compute + GPU, stars). Links to
// the public share page so anonymous visitors can open it.

import { computed } from 'vue'
import { Star, Server, Cpu, Play, Pause, Music, Github } from 'lucide-vue-next'
import type { FeaturedItem } from '@/types'
import { usePlayerStore } from '@/stores/player'
import { trackFromRequest } from '@/utils/player'

const props = defineProps<{ item: FeaturedItem }>()

const type = computed(() => props.item.inference_type)
const shareUrl = computed(() => `/s/${props.item.share_token}`)
const gpu = computed(() => {
  const list = props.item.gpus || []
  if (!list.length) return null
  return list.length === 1 ? list[0] : `${list[0]} +${list.length - 1}`
})

// MUSIC plays in place through the global player — the showcase doubles as a
// demo of the player bar.
const player = usePlayerStore()
const track = computed(() => trackFromRequest(props.item))
const isCurrent = computed(() => !!track.value && player.current?.id === track.value.id)
const playPause = () => {
  if (!track.value) return
  if (isCurrent.value) player.toggle()
  else player.playTrack(track.value)
}
</script>

<template>
  <NuxtLink
    :to="shareUrl"
    class="group flex min-w-0 flex-col overflow-hidden rounded-xl border bg-card shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
  >
    <!-- Media -->
    <div class="relative aspect-[4/3] w-full overflow-hidden bg-muted">
      <!-- IMAGE -->
      <img
        v-if="type === 'IMAGE' && item.image_urls?.length"
        :src="item.image_urls[0]"
        class="size-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
        :alt="item.prompt_preview || 'Generated image'"
        loading="lazy"
      />

      <!-- VIDEO: autoplaying muted loop, the classic showcase treatment -->
      <video
        v-else-if="type === 'VIDEO' && item.video_url"
        :src="item.video_url"
        :poster="item.input_image_url ?? undefined"
        muted
        loop
        autoplay
        playsinline
        preload="metadata"
        class="size-full object-cover"
      />

      <!-- MUSIC: square cover + play-in-place -->
      <div v-else-if="type === 'MUSIC'" class="relative size-full">
        <img
          v-if="item.cover_image_url"
          :src="item.cover_image_url"
          class="size-full object-cover"
          :alt="item.prompt_preview || 'Song cover'"
          loading="lazy"
        />
        <div v-else class="flex size-full items-center justify-center bg-gradient-to-br from-fuchsia-500/25 via-violet-500/20 to-cyan-500/25">
          <Music class="size-12 text-muted-foreground" />
        </div>
        <button
          v-if="track"
          type="button"
          class="absolute bottom-3 right-3 flex size-11 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105"
          :title="isCurrent && player.playing ? 'Pause' : 'Play'"
          @click.prevent.stop="playPause"
        >
          <Pause v-if="isCurrent && player.playing" class="size-5" />
          <Play v-else class="size-5 translate-x-px" />
        </button>
        <p class="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/60 to-transparent px-3 pb-2 pt-8 text-sm text-white">
          {{ item.prompt_preview }}
        </p>
      </div>

      <!-- MESH: interactive 3D viewer -->
      <div v-else-if="type === 'MESH' && item.model_url" class="size-full" @click.prevent.stop>
        <ModelViewer
          :src="item.model_url"
          :poster-src="item.input_image_url"
          :lazy="true"
          :downloadable="false"
          alt="Generated 3D model"
          class="size-full"
        />
      </div>

      <!-- TTS / STT: text + compact audio -->
      <div
        v-else-if="type === 'TTS' || type === 'STT'"
        class="flex size-full flex-col justify-between gap-3 p-4"
        @click.prevent.stop
      >
        <p class="line-clamp-4 text-sm text-muted-foreground">
          “{{ type === 'TTS' ? item.prompt_preview : item.response_preview }}”
        </p>
        <audio
          v-if="item.output_audio_url || item.audio_url"
          :src="(item.output_audio_url || item.audio_url) ?? undefined"
          controls
          preload="metadata"
          class="h-9 w-full"
        />
      </div>

      <!-- LLM: prompt → response snippet -->
      <div v-else class="flex size-full flex-col gap-2.5 p-4 text-sm">
        <div class="rounded-lg rounded-br-sm bg-primary/10 px-3 py-2 self-end max-w-[90%]">
          <p class="line-clamp-2">{{ item.prompt_preview }}</p>
        </div>
        <div class="rounded-lg rounded-bl-sm bg-muted px-3 py-2 self-start max-w-[90%]">
          <p class="line-clamp-5 text-muted-foreground">{{ item.response_preview }}</p>
        </div>
      </div>

      <div class="absolute left-3 top-3">
        <ModalityBadge :type="type" class="shadow-sm" />
      </div>
    </div>

    <!-- One quiet metadata line: who prompted · whose compute/GPU · stars -->
    <div class="flex items-center gap-3 px-4 py-3 text-xs text-muted-foreground">
      <span v-if="item.github_login || item.owner" class="inline-flex min-w-0 items-center gap-1">
        <Github class="size-3.5 shrink-0" />
        <span class="truncate font-mono">{{ item.github_login || item.owner }}</span>
      </span>
      <span v-if="item.provider" class="inline-flex min-w-0 items-center gap-1">
        <Server class="size-3.5 shrink-0" />
        <span class="truncate">{{ item.provider.name }}</span>
      </span>
      <span v-if="gpu" class="hidden items-center gap-1 sm:inline-flex">
        <Cpu class="size-3.5 shrink-0" /> {{ gpu }}
      </span>
      <span v-if="item.star_count" class="ml-auto inline-flex shrink-0 items-center gap-1">
        <Star class="size-3.5 fill-current text-amber-500" /> {{ item.star_count }}
      </span>
    </div>
  </NuxtLink>
</template>
