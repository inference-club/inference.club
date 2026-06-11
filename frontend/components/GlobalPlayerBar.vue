<script setup lang="ts">
// Spotify-style persistent bottom bar for the global music player. Mounted in
// the layouts (app + default) and hidden until a queue exists; survives
// navigation because the audio element lives in the player store, not here.

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  Music, Play, Pause, SkipBack, SkipForward, Shuffle, Repeat, Repeat1,
  ListMusic, Volume2, VolumeX, X,
} from 'lucide-vue-next'
import { usePlayerStore } from '@/stores/player'
import { formatTrackTime } from '@/utils/player'
import { getSharedAnalyser } from '@/utils/audio'

const { t } = useI18n()
const player = usePlayerStore()

const current = computed(() => player.current)

// --- seek slider (local while dragging so timeupdate doesn't fight the thumb)
const dragging = ref(false)
const dragValue = ref(0)
const sliderValue = computed(() =>
  dragging.value ? [dragValue.value] : [player.currentTime],
)
const onSliderInput = (v?: number[]) => {
  if (!v) return
  dragging.value = true
  dragValue.value = v[0] ?? 0
}
const onSliderCommit = (v?: number[]) => {
  dragging.value = false
  if (v) player.seek(v[0] ?? 0)
}

// --- mini equalizer driven by the store's audio element ---------------------
const BAR_COUNT = 16
const IDLE = 0.15
const levels = ref<number[]>(Array(BAR_COUNT).fill(IDLE))
let analyser: AnalyserNode | null = null
let freq: Uint8Array | null = null
let raf = 0

const tick = () => {
  if (!analyser || !freq) return
  analyser.getByteFrequencyData(freq)
  const usable = Math.floor(freq.length * 0.75)
  const next = new Array<number>(BAR_COUNT)
  for (let i = 0; i < BAR_COUNT; i++) {
    const start = Math.floor((i / BAR_COUNT) * usable)
    const end = Math.max(start + 1, Math.floor(((i + 1) / BAR_COUNT) * usable))
    let sum = 0
    for (let j = start; j < end; j++) sum += freq[j]
    next[i] = Math.min(1, Math.max(IDLE, sum / (end - start) / 255))
  }
  levels.value = next
  raf = requestAnimationFrame(tick)
}

watch(
  () => player.playing,
  (playing) => {
    if (playing) {
      const el = player.audioElement()
      if (el && !analyser) {
        analyser = getSharedAnalyser(el)
        if (analyser) freq = new Uint8Array(analyser.frequencyBinCount)
      }
      if (analyser && !raf) raf = requestAnimationFrame(tick)
    } else {
      if (raf) cancelAnimationFrame(raf)
      raf = 0
      levels.value = Array(BAR_COUNT).fill(IDLE)
    }
  },
)

onBeforeUnmount(() => {
  if (raf) cancelAnimationFrame(raf)
  raf = 0
})

const repeatIcon = computed(() => (player.repeat === 'one' ? Repeat1 : Repeat))
const muted = computed(() => player.volume === 0)
const lastVolume = ref(1)
const toggleMute = () => {
  if (muted.value) {
    player.setVolume(lastVolume.value || 1)
  } else {
    lastVolume.value = player.volume
    player.setVolume(0)
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="player.hasQueue"
      class="fixed inset-x-0 bottom-0 z-50 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80"
      data-testid="global-player-bar"
    >
      <div class="mx-auto flex h-20 max-w-7xl items-center gap-3 px-3 sm:gap-4 sm:px-6">
        <!-- Track identity -->
        <NuxtLink
          v-if="current"
          :to="`/dashboard/inference/requests/${current.requestId}`"
          class="flex min-w-0 flex-1 items-center gap-3 sm:flex-initial sm:basis-1/4"
        >
          <img
            v-if="current.coverUrl"
            :src="current.coverUrl"
            class="size-12 shrink-0 rounded-md border object-cover"
            :alt="current.title"
          />
          <div
            v-else
            class="flex size-12 shrink-0 items-center justify-center rounded-md border bg-muted"
          >
            <Music class="size-5 text-muted-foreground" />
          </div>
          <div class="min-w-0">
            <p class="truncate text-sm font-medium" :title="current.title">
              {{ current.title }}
            </p>
            <p v-if="current.owner" class="truncate text-xs text-muted-foreground">
              {{ current.owner }}
            </p>
          </div>
        </NuxtLink>

        <!-- Transport + seek -->
        <div class="flex min-w-0 flex-1 flex-col items-center gap-1">
          <div class="flex items-center gap-1 sm:gap-2">
            <Button
              variant="ghost"
              size="icon"
              class="hidden size-8 sm:inline-flex"
              :class="player.shuffle ? 'text-primary' : 'text-muted-foreground'"
              :title="t('player.shuffle')"
              data-testid="player-shuffle"
              @click="player.toggleShuffle()"
            >
              <Shuffle class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              class="size-8 text-muted-foreground"
              :disabled="!player.hasPrev"
              :title="t('player.previous')"
              @click="player.prev()"
            >
              <SkipBack class="size-4" />
            </Button>
            <Button
              size="icon"
              class="size-9 rounded-full"
              :title="player.playing ? t('player.pause') : t('player.play')"
              data-testid="player-toggle"
              @click="player.toggle()"
            >
              <Pause v-if="player.playing" class="size-4" />
              <Play v-else class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              class="size-8 text-muted-foreground"
              :disabled="!player.hasNext"
              :title="t('player.next')"
              @click="player.next()"
            >
              <SkipForward class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              class="hidden size-8 sm:inline-flex"
              :class="player.repeat !== 'off' ? 'text-primary' : 'text-muted-foreground'"
              :title="t('player.repeat')"
              @click="player.cycleRepeat()"
            >
              <component :is="repeatIcon" class="size-4" />
            </Button>
          </div>
          <div class="hidden w-full max-w-xl items-center gap-2 sm:flex">
            <span class="w-10 text-right text-2xs tabular-nums text-muted-foreground">
              {{ formatTrackTime(player.currentTime) }}
            </span>
            <Slider
              :model-value="sliderValue"
              :max="Math.max(player.duration, 1)"
              :step="1"
              class="flex-1"
              @update:model-value="onSliderInput"
              @value-commit="onSliderCommit"
            />
            <span class="w-10 text-2xs tabular-nums text-muted-foreground">
              {{ formatTrackTime(player.duration) }}
            </span>
          </div>
        </div>

        <!-- EQ + queue + volume + close -->
        <div class="flex shrink-0 items-center gap-1 sm:basis-1/4 sm:justify-end sm:gap-2">
          <div class="hidden h-6 w-16 items-end gap-[2px] lg:flex" aria-hidden="true">
            <span
              v-for="(lvl, i) in levels"
              :key="i"
              class="flex-1 rounded-sm bg-primary/70 transition-transform duration-75"
              :style="{ transform: `scaleY(${lvl})`, transformOrigin: 'bottom', height: '100%' }"
            />
          </div>

          <Popover>
            <PopoverTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="size-8 text-muted-foreground"
                :title="t('player.queue')"
                data-testid="player-queue"
              >
                <ListMusic class="size-4" />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" class="w-80 p-2">
              <p class="px-2 py-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {{ t('player.queue') }} · {{ player.queue.length }}
              </p>
              <div class="max-h-72 space-y-0.5 overflow-y-auto">
                <div
                  v-for="(track, i) in player.queue"
                  :key="`${player.queueVersion}-${track.id}`"
                  class="group flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
                  :class="i === player.index ? 'bg-accent/60 text-primary' : ''"
                >
                  <button
                    class="flex min-w-0 flex-1 items-center gap-2 text-left"
                    @click="player.jumpTo(i)"
                  >
                    <span class="w-5 shrink-0 text-xs tabular-nums text-muted-foreground">{{ i + 1 }}</span>
                    <span class="min-w-0 truncate">{{ track.title }}</span>
                  </button>
                  <span class="text-2xs tabular-nums text-muted-foreground">
                    {{ formatTrackTime(track.duration) }}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    class="size-6 opacity-0 group-hover:opacity-100"
                    :title="t('player.removeFromQueue')"
                    @click="player.removeFromQueue(i)"
                  >
                    <X class="size-3.5" />
                  </Button>
                </div>
              </div>
            </PopoverContent>
          </Popover>

          <div class="hidden items-center gap-2 md:flex">
            <Button
              variant="ghost"
              size="icon"
              class="size-8 text-muted-foreground"
              :title="muted ? t('player.unmute') : t('player.mute')"
              @click="toggleMute"
            >
              <VolumeX v-if="muted" class="size-4" />
              <Volume2 v-else class="size-4" />
            </Button>
            <Slider
              :model-value="[player.volume]"
              :max="1"
              :step="0.01"
              class="w-20"
              @update:model-value="(v) => v && player.setVolume(v[0] ?? 1)"
            />
          </div>

          <Button
            variant="ghost"
            size="icon"
            class="size-8 text-muted-foreground"
            :title="t('player.close')"
            data-testid="player-close"
            @click="player.clear()"
          >
            <X class="size-4" />
          </Button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
