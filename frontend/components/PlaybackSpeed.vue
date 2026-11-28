<script setup lang="ts">
// The speed control: a small button showing the current speed that opens a
// slider from 0.5× to 3× with a few one-tap presets. It changes the shared
// speed (usePlaybackRate), so every player on the page follows.
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Slider } from '@/components/ui/slider'
import { RATE_MAX, RATE_MIN, RATE_PRESETS, RATE_STEP, usePlaybackRate } from '@/composables/usePlaybackRate'

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
const { t } = useI18n()
const { rate, setRate, label } = usePlaybackRate()
</script>

<template>
  <Popover>
    <PopoverTrigger as-child>
      <button
        type="button"
        class="shrink-0 rounded-md border font-mono tabular-nums transition-colors hover:bg-accent"
        :class="[compact ? 'px-1.5 py-0.5 text-[11px]' : 'px-2 py-1 text-xs', rate !== 1 ? 'border-primary/50 text-primary' : 'text-muted-foreground']"
        :aria-label="`${t('player.speed')}: ${label}`"
        :title="t('player.speed')"
        data-testid="playback-speed"
        @click.stop
      >{{ label }}</button>
    </PopoverTrigger>
    <PopoverContent align="end" class="w-64 p-3" @click.stop>
      <div class="mb-2 flex items-baseline justify-between">
        <span class="text-sm font-medium">{{ t('player.speed') }}</span>
        <span class="font-mono text-sm tabular-nums" data-testid="playback-speed-value">{{ label }}</span>
      </div>
      <Slider
        :model-value="[rate]"
        :min="RATE_MIN"
        :max="RATE_MAX"
        :step="RATE_STEP"
        :aria-label="t('player.speed')"
        data-testid="playback-speed-slider"
        @update:model-value="(v) => v && setRate(v[0] ?? 1)"
      />
      <div class="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
        <span>{{ RATE_MIN }}×</span><span>{{ RATE_MAX }}×</span>
      </div>
      <div class="mt-2 flex flex-wrap gap-1">
        <button
          v-for="p in RATE_PRESETS"
          :key="p"
          type="button"
          class="rounded-md border px-2 py-1 font-mono text-xs tabular-nums transition-colors hover:bg-accent"
          :class="Math.abs(rate - p) < 0.01 ? 'border-primary bg-primary/10 text-primary' : 'text-muted-foreground'"
          @click="setRate(p)"
        >{{ p }}×</button>
      </div>
    </PopoverContent>
  </Popover>
</template>
