<script setup lang="ts">
// Spotify-style compact track rows. Clicking a row plays the whole list as the
// queue starting from that row (pass `single` to play rows individually).

import { Music, Play, Pause } from 'lucide-vue-next'
import type { PlayerTrack } from '@/utils/player'
import { formatTrackTime } from '@/utils/player'
import { usePlayerStore } from '@/stores/player'

const props = withDefaults(
  defineProps<{
    tracks: PlayerTrack[]
    /** Play only the clicked track instead of queueing the whole list. */
    single?: boolean
  }>(),
  { single: false },
)

const player = usePlayerStore()
const isCurrent = (id: string) => player.current?.id === id

const playRow = (i: number) => {
  if (props.single) player.playTrack(props.tracks[i])
  else player.playQueue(props.tracks, i)
}
</script>

<template>
  <div class="rounded-xl border">
    <div
      v-for="(tr, i) in tracks"
      :key="tr.id"
      class="group flex cursor-pointer items-center gap-3 border-b px-3 py-2.5 last:border-b-0 hover:bg-accent/50"
      :class="isCurrent(tr.id) ? 'bg-accent/40' : ''"
      :data-testid="`track-row-${i}`"
      @click="playRow(i)"
    >
      <div class="flex w-8 shrink-0 items-center justify-center">
        <span
          class="text-sm tabular-nums text-muted-foreground group-hover:hidden"
          :class="isCurrent(tr.id) ? 'text-primary' : ''"
        >{{ i + 1 }}</span>
        <component
          :is="isCurrent(tr.id) && player.playing ? Pause : Play"
          class="hidden size-4 group-hover:block"
        />
      </div>
      <img
        v-if="tr.coverUrl"
        :src="tr.coverUrl"
        class="size-10 shrink-0 rounded-md border object-cover"
        :alt="tr.title"
        loading="lazy"
      />
      <div v-else class="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
        <Music class="size-4 text-muted-foreground" />
      </div>
      <div class="min-w-0 flex-1">
        <NuxtLink
          :to="`/dashboard/inference/requests/${tr.requestId}`"
          class="block truncate text-sm hover:underline"
          :class="isCurrent(tr.id) ? 'text-primary font-medium' : ''"
          :title="tr.title"
          @click.stop
        >
          {{ tr.title }}
        </NuxtLink>
        <p v-if="tr.owner" class="truncate text-xs text-muted-foreground">{{ tr.owner }}</p>
      </div>
      <span class="shrink-0 text-xs tabular-nums text-muted-foreground">
        {{ formatTrackTime(tr.duration) }}
      </span>
    </div>
  </div>
</template>
