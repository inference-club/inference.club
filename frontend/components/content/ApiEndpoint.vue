<script setup lang="ts">
// Inline endpoint chip for API reference pages. Usage:
//   ::api-endpoint{method="POST" path="/v1/chat/completions"}
// Optional: async="true" to flag endpoints that also accept `async: true`.
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{ method?: string; path?: string; async?: boolean }>(),
  { method: 'GET', path: '' },
)

const method = computed(() => props.method.toUpperCase())
const color = computed(() => ({
  GET: 'text-emerald-600 dark:text-emerald-400 border-emerald-500/30 bg-emerald-500/10',
  POST: 'text-sky-600 dark:text-sky-400 border-sky-500/30 bg-sky-500/10',
  PUT: 'text-amber-600 dark:text-amber-400 border-amber-500/30 bg-amber-500/10',
  PATCH: 'text-violet-600 dark:text-violet-400 border-violet-500/30 bg-violet-500/10',
  DELETE: 'text-rose-600 dark:text-rose-400 border-rose-500/30 bg-rose-500/10',
}[method.value] ?? 'text-foreground border-border bg-muted'))
</script>

<template>
  <div class="not-prose my-4 flex flex-wrap items-center gap-2.5 rounded-xl border bg-card px-3 py-2.5">
    <span class="rounded-md border px-2 py-0.5 font-mono text-2xs font-bold tracking-wide" :class="color">{{ method }}</span>
    <code class="min-w-0 break-all font-mono text-sm text-foreground">{{ path }}</code>
    <span v-if="async" class="ml-auto rounded-md border border-orange-500/30 bg-orange-500/10 px-2 py-0.5 text-2xs font-medium text-orange-600 dark:text-orange-400">async-capable</span>
  </div>
</template>
