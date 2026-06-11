<script setup lang="ts">
// Tinted modality badge: one hue per inference type so mixed lists scan at a
// glance. The single source of modality color+icon — reuse anywhere a type
// needs visual identity (cards, detail pages, playground strips).
import {
  MessageSquare, Mic, AudioLines, Music, Image as ImageIcon, Box, Clapperboard,
} from 'lucide-vue-next'
import type { InferenceType } from '@/types'

const props = defineProps<{ type: InferenceType }>()

const META: Record<InferenceType, { icon: unknown; classes: string }> = {
  LLM: {
    icon: MessageSquare,
    classes: 'bg-sky-500/10 text-sky-700 dark:text-sky-400 border-sky-500/25',
  },
  STT: {
    icon: Mic,
    classes: 'bg-teal-500/10 text-teal-700 dark:text-teal-400 border-teal-500/25',
  },
  TTS: {
    icon: AudioLines,
    classes: 'bg-violet-500/10 text-violet-700 dark:text-violet-400 border-violet-500/25',
  },
  MUSIC: {
    icon: Music,
    classes: 'bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-400 border-fuchsia-500/25',
  },
  IMAGE: {
    icon: ImageIcon,
    classes: 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/25',
  },
  MESH: {
    icon: Box,
    classes: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/25',
  },
  VIDEO: {
    icon: Clapperboard,
    classes: 'bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/25',
  },
}

const meta = computed(() => META[props.type] ?? META.LLM)
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium"
    :class="meta.classes"
  >
    <component :is="meta.icon" class="size-3" />
    {{ type }}
  </span>
</template>
