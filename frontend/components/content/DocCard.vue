<script setup lang="ts">
// A single linked card inside ::doc-cards. Author passes a short icon name.
import { computed } from 'vue'
import {
  Rocket, Bot, Boxes, Server, Network, Cpu, KeyRound, BookOpen, Code2,
  Image, Mic, Music, Video, Waves, Workflow, Share2, ShieldCheck, Layers,
  Sparkles, GitBranch, Gauge, CircleHelp, ArrowRight,
} from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{ title?: string; to?: string; icon?: string }>(),
  { title: '', to: '' },
)

const icons: Record<string, any> = {
  rocket: Rocket, bot: Bot, boxes: Boxes, server: Server, network: Network,
  cpu: Cpu, key: KeyRound, book: BookOpen, code: Code2, image: Image,
  mic: Mic, music: Music, video: Video, waves: Waves, workflow: Workflow,
  share: Share2, shield: ShieldCheck, layers: Layers, sparkles: Sparkles,
  git: GitBranch, gauge: Gauge, help: CircleHelp,
}
const localePath = useLocalePath()
const Glyph = computed(() => icons[props.icon ?? ''] ?? BookOpen)
const href = computed(() => (props.to ? localePath(props.to) : undefined))
</script>

<template>
  <NuxtLink
    :to="href"
    class="group not-prose flex items-start gap-3 rounded-xl border bg-card px-4 py-3.5 transition-colors hover:border-foreground/20 hover:bg-accent/50"
  >
    <span class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border bg-muted/50 text-foreground/80 transition-colors group-hover:text-foreground">
      <component :is="Glyph" class="size-4.5" />
    </span>
    <span class="min-w-0 flex-1">
      <span class="flex items-center gap-1 font-medium text-foreground">
        {{ title }}
        <ArrowRight class="size-3.5 -translate-x-1 opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100" />
      </span>
      <span class="mt-0.5 block text-sm leading-snug text-muted-foreground"><slot /></span>
    </span>
  </NuxtLink>
</template>
