<script setup lang="ts">
// Docs callout. Usage in markdown:
//   ::callout{type="construction" title="Active development"}
//   This subsystem is still moving. Expect rough edges.
//   ::
// Types: note (context), tip (advice), warning (sharp edges), construction
// (actively being built / known-incomplete), limitation (a deliberate gap).
import { computed } from 'vue'
import { Info, Lightbulb, TriangleAlert, HardHat, CircleDashed } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    type?: 'note' | 'tip' | 'warning' | 'construction' | 'limitation'
    title?: string
  }>(),
  { type: 'note' },
)

const styles = {
  note: { icon: Info, label: 'Note', box: 'border-sky-500/25 bg-sky-500/[0.06]', bar: 'bg-sky-500', accent: 'text-sky-600 dark:text-sky-400' },
  tip: { icon: Lightbulb, label: 'Tip', box: 'border-emerald-500/25 bg-emerald-500/[0.06]', bar: 'bg-emerald-500', accent: 'text-emerald-600 dark:text-emerald-400' },
  warning: { icon: TriangleAlert, label: 'Heads up', box: 'border-amber-500/25 bg-amber-500/[0.06]', bar: 'bg-amber-500', accent: 'text-amber-600 dark:text-amber-400' },
  construction: { icon: HardHat, label: 'Active development', box: 'border-orange-500/25 bg-orange-500/[0.06]', bar: 'bg-orange-500', accent: 'text-orange-600 dark:text-orange-400' },
  limitation: { icon: CircleDashed, label: 'Known limitation', box: 'border-border bg-muted/40', bar: 'bg-muted-foreground/40', accent: 'text-muted-foreground' },
} as const

const s = computed(() => styles[props.type])
</script>

<template>
  <aside class="not-prose my-5 flex overflow-hidden rounded-xl border" :class="s.box">
    <div class="w-1 shrink-0" :class="s.bar" />
    <div class="min-w-0 flex-1 px-4 py-3">
      <p class="flex items-center gap-2 text-2xs font-semibold uppercase tracking-wide" :class="s.accent">
        <component :is="s.icon" class="size-3.5 shrink-0" />
        {{ title ?? s.label }}
      </p>
      <div class="mt-1.5 text-sm leading-relaxed text-foreground/90 [&_a]:font-medium [&_a]:underline [&_a]:underline-offset-4 [&_code]:rounded [&_code]:bg-background/70 [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[0.85em] [&_li]:my-0.5 [&_p]:my-1.5 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ul]:my-1.5 [&_ul]:list-disc [&_ul]:pl-5">
        <slot />
      </div>
    </div>
  </aside>
</template>
