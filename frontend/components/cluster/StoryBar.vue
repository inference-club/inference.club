<script setup lang="ts">
// Story mode scrubber (PRD 07 V3): drag through the provider's manifest
// revisions and watch the cluster grow from its first Service to the full
// fleet. The bar owns only the selection; the page swaps the scene's
// snapshot to the chosen revision (live state and pulses pause off-live).
import { computed } from 'vue'
import { History, Radio } from 'lucide-vue-next'
import type { ManifestRevisionInfo } from '@/composables/useClusterState'

const props = defineProps<{
  revisions: ManifestRevisionInfo[]
  // Selected revision id; null = live (current manifest + live state).
  modelValue: number | null
}>()

const emit = defineEmits<{ 'update:modelValue': [id: number | null] }>()

const index = computed({
  get() {
    if (props.modelValue == null) return props.revisions.length - 1
    const i = props.revisions.findIndex(r => r.id === props.modelValue)
    return i === -1 ? props.revisions.length - 1 : i
  },
  set(i: number) {
    const rev = props.revisions[i]
    if (!rev) return
    // Scrubbing to the newest revision returns to live — the newest revision
    // IS the current manifest, and live beats a frozen copy of it.
    emit('update:modelValue', i === props.revisions.length - 1 ? null : rev.id)
  },
})

const current = computed(() => props.revisions[index.value])
const isLive = computed(() => props.modelValue == null)

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
</script>

<template>
  <div
    v-if="revisions.length > 1"
    class="flex items-center gap-3 rounded-lg border bg-card px-3 py-2"
  >
    <History class="size-4 shrink-0 text-muted-foreground" />
    <input
      v-model.number="index"
      type="range"
      :min="0"
      :max="revisions.length - 1"
      :step="1"
      class="h-1.5 flex-1 cursor-pointer accent-sky-500"
      :aria-label="`Cluster history (${revisions.length} revisions)`"
    />
    <div class="w-44 shrink-0 text-right text-xs">
      <p class="font-mono text-foreground">{{ current ? fmtDate(current.uploaded_at) : '' }}</p>
      <p class="text-muted-foreground">
        {{ current?.host_count ?? 0 }} hosts · {{ current?.service_count ?? 0 }} services
      </p>
    </div>
    <button
      class="inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium"
      :class="isLive
        ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
        : 'text-muted-foreground hover:text-foreground'"
      @click="emit('update:modelValue', null)"
    >
      <Radio class="size-3" /> Live
    </button>
  </div>
</template>
