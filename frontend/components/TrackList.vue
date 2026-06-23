<script setup lang="ts">
// Spotify-style compact track rows. Clicking a row plays the whole list as the
// queue starting from that row (pass `single` to play rows individually);
// clicking the row that's already current toggles play/pause instead of
// restarting it. The current row shows a persistent now-playing cue (animated
// equalizer while playing, a pause glyph while paused).

import { computed, ref } from 'vue'
import { Music, Play, Pause, Cpu, ImagePlus } from 'lucide-vue-next'
import type { InferenceRequest } from '@/types'
import type { PlayerTrack } from '@/utils/player'
import { formatTrackTime } from '@/utils/player'
import { usePlayerStore } from '@/stores/player'

const props = withDefaults(
  defineProps<{
    tracks: PlayerTrack[]
    /** Play only the clicked track instead of queueing the whole list. */
    single?: boolean
    /** Source requests backing the tracks — rows whose request is found here
     * get star/bookmark quick actions + the overflow menu (rows without one,
     * e.g. a client-side recently-played strip, just omit them). */
    requests?: InferenceRequest[]
  }>(),
  { single: false, requests: undefined },
)

const player = usePlayerStore()
const isCurrent = (id: string) => player.current?.id === id

const requestsById = computed(() => {
  const m = new Map<string, InferenceRequest>()
  for (const r of props.requests ?? []) m.set(String(r.id), r)
  return m
})
const requestFor = (tr: PlayerTrack) => requestsById.value.get(tr.requestId)

const playRow = (i: number) => {
  const tr = props.tracks[i]
  // Already the current track → toggle pause/resume rather than reloading the
  // audio element (reloading mid-play was the "play/pause fails" bug).
  if (isCurrent(tr.id)) {
    player.toggle()
    return
  }
  if (props.single) player.playTrack(tr)
  else player.playQueue(props.tracks, i)
}

// Single cover-art dialog instance, retargeted per row when the owner clicks an
// empty thumbnail.
const coverOpen = ref(false)
const coverTarget = ref<{ kind: 'request'; id: string | number } | null>(null)
const coverSeed = ref<string | undefined>(undefined)
const openCover = (tr: PlayerTrack) => {
  const req = requestFor(tr)
  if (!req?.is_owner) return
  coverTarget.value = { kind: 'request', id: req.id }
  coverSeed.value = tr.title
  coverOpen.value = true
}
</script>

<template>
  <div class="rounded-xl border">
    <div
      v-for="(tr, i) in tracks"
      :key="tr.id"
      class="group flex cursor-pointer items-center gap-2 border-b px-2 py-2 last:border-b-0 hover:bg-accent/50 sm:gap-3 sm:px-3 sm:py-2.5"
      :class="isCurrent(tr.id) ? 'bg-accent/40' : ''"
      :data-testid="`track-row-${i}`"
      @click="playRow(i)"
    >
      <!-- Index / play-pause / now-playing cue -->
      <div class="flex w-7 shrink-0 items-center justify-center sm:w-8">
        <template v-if="isCurrent(tr.id)">
          <div v-if="player.playing" class="eq text-primary" aria-hidden="true" title="Now playing">
            <span /><span /><span />
          </div>
          <Pause v-else class="size-4 text-primary" />
        </template>
        <template v-else>
          <span
            class="text-sm tabular-nums text-muted-foreground group-hover:hidden"
          >{{ i + 1 }}</span>
          <Play class="hidden size-4 group-hover:block" />
        </template>
      </div>

      <!-- Album art (empty art is clickable for the owner → cover-art modal) -->
      <img
        v-if="tr.coverUrl"
        :src="tr.coverUrl"
        class="size-10 shrink-0 rounded-md border object-cover"
        :alt="tr.title"
        loading="lazy"
      />
      <button
        v-else-if="requestFor(tr)?.is_owner"
        type="button"
        class="group/art relative flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted hover:border-primary"
        title="Add cover art"
        @click.stop="openCover(tr)"
      >
        <Music class="size-4 text-muted-foreground group-hover/art:hidden" />
        <ImagePlus class="hidden size-4 text-primary group-hover/art:block" />
      </button>
      <div
        v-else
        class="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted"
      >
        <Music class="size-4 text-muted-foreground" />
      </div>

      <!-- Title + owner / GPU -->
      <div class="min-w-0 flex-1">
        <NuxtLink
          :to="`/dashboard/inference/requests/${tr.requestId}`"
          class="block text-sm hover:underline"
          :class="isCurrent(tr.id) ? 'font-medium text-primary' : ''"
          :title="tr.title"
          @click.stop
        >
          <MarqueeText :text="tr.title" />
        </NuxtLink>
        <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span v-if="tr.owner" class="truncate">{{ tr.owner }}</span>
          <span
            v-if="requestFor(tr)?.gpu_label"
            class="hidden shrink-0 items-center gap-1 rounded border px-1.5 py-px text-[10px] leading-none sm:inline-flex"
            :title="`Generated on ${requestFor(tr)?.gpu_label}`"
          >
            <Cpu class="size-2.5" /> {{ requestFor(tr)?.gpu_label }}
          </span>
        </div>
      </div>

      <!-- Inline quick actions + overflow menu -->
      <RequestQuickActions
        v-if="requestFor(tr)"
        :request="requestFor(tr)!"
      />
      <span class="shrink-0 text-xs tabular-nums text-muted-foreground">
        {{ formatTrackTime(tr.duration) }}
      </span>
      <SongRowMenu v-if="requestFor(tr)" :request="requestFor(tr)!" />
    </div>

    <GenerateCoverDialog
      v-if="coverTarget"
      v-model:open="coverOpen"
      :target="coverTarget"
      :seed-prompt="coverSeed"
    />
  </div>
</template>

<style scoped>
/* Three-bar now-playing equalizer. */
.eq {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 14px;
}
.eq span {
  width: 2px;
  height: 100%;
  background: currentColor;
  transform-origin: bottom;
  animation: eq-bounce 0.9s ease-in-out infinite;
}
.eq span:nth-child(2) {
  animation-delay: 0.25s;
}
.eq span:nth-child(3) {
  animation-delay: 0.5s;
}
@keyframes eq-bounce {
  0%,
  100% {
    transform: scaleY(0.3);
  }
  50% {
    transform: scaleY(1);
  }
}
@media (prefers-reduced-motion: reduce) {
  .eq span {
    animation: none;
    transform: scaleY(0.6);
  }
}
</style>
