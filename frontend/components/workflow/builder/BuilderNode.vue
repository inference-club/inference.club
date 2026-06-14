<script setup lang="ts">
/**
 * An editable node on the builder canvas. Shows the step's kind, modality and a
 * one-line summary; exposes connect handles and select/delete affordances. The
 * heavy editing happens in the inspector panel — this is the at-a-glance card.
 */
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { FileText, GitFork, Wrench, Layers, Hand, Sparkles, Trash2 } from 'lucide-vue-next'
import { modalityHex } from '@/composables/useClusterState'
import type { StepSpec } from '@/composables/useAsyncJobs'

// Vue Flow passes `selected` to custom nodes; `data` carries our step + delete cb.
const props = defineProps<{
  data: { step: StepSpec; onDelete?: (id: string) => void }
  selected?: boolean
}>()

const step = computed(() => props.data.step)

const KIND_ICON: Record<string, unknown> = {
  prompt: Sparkles, inference: FileText, map: GitFork, transform: Wrench, collect: Layers, gate: Hand,
}
const KIND_LABEL: Record<string, string> = {
  prompt: 'Prompt', inference: 'Inference', map: 'Fan-out', transform: 'Transform', collect: 'Collect', gate: 'Human gate',
}

// Modality drives the accent dot: prompt is an LLM call; inference/map use type.
const modality = computed(() => {
  if (step.value.kind === 'prompt') return 'llm'
  if (step.value.kind === 'inference' || step.value.kind === 'map') return step.value.type || ''
  return ''
})
const accent = computed(() => (modality.value ? modalityHex(modality.value) : '#94a3b8'))

const summary = computed(() => {
  const s = step.value
  if (s.kind === 'prompt') return `${s.target || 'image'} prompt${(s.count || 1) > 1 ? ` ×${s.count}` : ''}`
  if (s.kind === 'inference') return String((s.body as { prompt?: string })?.prompt || s.type || '')
  if (s.kind === 'map') return `over ${String(s.over || '…')}`
  if (s.kind === 'transform') return `${s.op || 'passthrough'}`
  if (s.kind === 'collect') return `from ${String(s.from || '…')}`
  if (s.kind === 'gate') return 'waits for approval'
  return ''
})
</script>

<template>
  <div
    class="group relative w-[240px] rounded-xl border-2 bg-background text-foreground transition-shadow"
    :class="selected ? 'border-primary shadow-[0_0_0_3px_hsl(var(--primary)/0.15)]' : 'border-border hover:border-primary/50'"
  >
    <Handle type="target" :position="Position.Left" class="!h-2.5 !w-2.5 !border-2 !bg-muted-foreground" />
    <Handle type="source" :position="Position.Right" class="!h-2.5 !w-2.5 !border-2 !bg-muted-foreground" />

    <div class="flex items-center justify-between gap-2 border-b px-3 py-2">
      <div class="flex min-w-0 items-center gap-1.5">
        <span class="size-2.5 shrink-0 rounded-full" :style="{ backgroundColor: accent }" />
        <component :is="KIND_ICON[step.kind] || FileText" class="size-3.5 shrink-0 text-muted-foreground" />
        <span class="truncate text-sm font-semibold" :title="step.title || step.id">{{ step.title || step.id }}</span>
      </div>
      <button
        class="shrink-0 rounded p-0.5 text-muted-foreground opacity-0 transition hover:bg-muted hover:text-rose-500 group-hover:opacity-100"
        title="Delete step"
        @pointerdown.stop
        @click.stop="data.onDelete?.(step.id)"
      >
        <Trash2 class="size-3.5" />
      </button>
    </div>

    <div class="px-3 py-2">
      <div class="mb-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
        <span class="rounded bg-muted px-1.5 py-0.5 font-medium uppercase">{{ KIND_LABEL[step.kind] }}</span>
        <span v-if="modality" class="rounded px-1.5 py-0.5 font-medium uppercase text-white" :style="{ backgroundColor: accent }">
          {{ modality }}
        </span>
      </div>
      <p class="line-clamp-2 text-xs text-muted-foreground">{{ summary || '—' }}</p>
    </div>
  </div>
</template>
