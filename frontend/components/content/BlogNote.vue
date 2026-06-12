<script setup lang="ts">
// MDC callout for blog/docs markdown. Usage:
//   ::blog-note{type="update" date="2026-06-12"}
//   The device plugin issue below was fixed in v0.17.4.
//   ::
// Types map to editorial intents: note (context), tip (advice), warning
// (sharp edges), update (post-publication addition), correction (we were
// wrong), disclaimer (scope/caveat).
import { computed } from 'vue'
import { Info, Lightbulb, TriangleAlert, RefreshCw, Pencil, ShieldAlert } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    type?: 'note' | 'tip' | 'warning' | 'update' | 'correction' | 'disclaimer'
    title?: string
    // ISO date shown next to the label — use for updates/corrections so
    // readers can tell what was added after publication.
    date?: string
  }>(),
  { type: 'note' },
)

const styles = {
  note: { icon: Info, label: 'Note', box: 'border-sky-500/30 bg-sky-500/5', accent: 'text-sky-600 dark:text-sky-400' },
  tip: { icon: Lightbulb, label: 'Tip', box: 'border-emerald-500/30 bg-emerald-500/5', accent: 'text-emerald-600 dark:text-emerald-400' },
  warning: { icon: TriangleAlert, label: 'Warning', box: 'border-amber-500/30 bg-amber-500/5', accent: 'text-amber-600 dark:text-amber-400' },
  update: { icon: RefreshCw, label: 'Update', box: 'border-violet-500/30 bg-violet-500/5', accent: 'text-violet-600 dark:text-violet-400' },
  correction: { icon: Pencil, label: 'Correction', box: 'border-rose-500/30 bg-rose-500/5', accent: 'text-rose-600 dark:text-rose-400' },
  disclaimer: { icon: ShieldAlert, label: 'Disclaimer', box: 'border-border bg-muted/50', accent: 'text-muted-foreground' },
} as const

const s = computed(() => styles[props.type])
</script>

<template>
  <aside class="not-prose my-6 rounded-lg border px-4 py-3" :class="s.box">
    <p class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide" :class="s.accent">
      <component :is="s.icon" class="size-3.5 shrink-0" />
      {{ title ?? s.label }}
      <time v-if="date" :datetime="date" class="font-normal normal-case tracking-normal text-muted-foreground">{{ date }}</time>
    </p>
    <div class="mt-1.5 text-sm leading-relaxed text-foreground/90 [&_a]:underline [&_a]:underline-offset-4 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[0.85em] [&_p]:my-1">
      <slot />
    </div>
  </aside>
</template>
