<script setup lang="ts">
import { computed } from 'vue'
import { Type, Wrench } from 'lucide-vue-next'
import { FEATURE_META, MODALITY_META, fmtCtx } from '@/utils/modelCapabilities'

const props = withDefaults(
  defineProps<{
    contextLength?: number | null
    inputModalities?: string[]
    supportedFeatures?: string[]
    showLabel?: boolean
  }>(),
  { contextLength: null, inputModalities: () => ['text'], supportedFeatures: () => [], showLabel: false },
)

const ctx = computed(() => fmtCtx(props.contextLength))
</script>

<template>
  <div class="flex flex-wrap items-center gap-1.5">
    <span v-if="showLabel" class="text-xs text-muted-foreground mr-1">Capabilities:</span>
    <span
      v-if="ctx"
      class="inline-flex items-center rounded bg-muted px-1.5 py-0.5 text-xs font-mono"
    >{{ ctx }}</span>
    <span
      v-for="mod in inputModalities"
      :key="mod"
      class="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-xs"
    >
      <component :is="MODALITY_META[mod]?.icon || Type" class="size-3" />
      {{ MODALITY_META[mod]?.label || mod }}
    </span>
    <span
      v-for="f in supportedFeatures"
      :key="f"
      class="inline-flex items-center gap-1 rounded bg-primary/10 text-primary px-1.5 py-0.5 text-xs"
    >
      <component :is="FEATURE_META[f]?.icon || Wrench" class="size-3" />
      {{ FEATURE_META[f]?.label || f }}
    </span>
  </div>
</template>
