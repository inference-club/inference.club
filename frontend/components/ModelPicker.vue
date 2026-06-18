<script setup lang="ts">
// Compact, in-composer model picker — a Popover triggered by a pill button that
// shows the current model + readiness. Built to be the reusable pattern for the
// other playground modalities (pass any ModelInfo[] + v-model the id).
import { computed, ref } from 'vue'
import { Check, ChevronsUpDown } from 'lucide-vue-next'
import type { ModelInfo } from '@/composables/usePlayground'
import { MODALITY_META } from '@/utils/modelCapabilities'

const props = defineProps<{
  models: ModelInfo[]
  modelValue: string
  loading?: boolean
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const open = ref(false)
const selected = computed(() => props.models.find((m) => m.id === props.modelValue))
// Drop the org prefix for the pill so a long id doesn't dominate the composer.
const shortName = computed(() => {
  const id = props.modelValue || ''
  return id.includes('/') ? id.split('/').pop() : id
})

const pick = (id: string) => {
  emit('update:modelValue', id)
  open.value = false
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <Button
        variant="ghost"
        size="sm"
        class="h-9 gap-1.5 rounded-full px-3 text-xs font-medium text-muted-foreground hover:text-foreground max-w-[55vw] sm:max-w-[16rem]"
        :disabled="loading || !models.length"
        :title="modelValue || 'Select a model'"
      >
        <ReadinessDot v-if="selected" :online="true" />
        <span class="truncate">{{ loading ? 'Loading…' : shortName || 'Select model' }}</span>
        <ChevronsUpDown class="size-3.5 shrink-0 opacity-60" />
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-72 p-1.5" align="start">
      <div class="max-h-80 overflow-y-auto">
        <p v-if="!models.length" class="px-2 py-3 text-xs text-muted-foreground text-center">
          No models available.
        </p>
        <button
          v-for="m in models"
          :key="m.id"
          type="button"
          class="w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-muted/60"
          :class="m.id === modelValue ? 'bg-primary/[0.06] ring-1 ring-primary/30' : ''"
          @click="pick(m.id)"
        >
          <ReadinessDot :online="true" />
          <span class="font-mono truncate flex-1">{{ m.id }}</span>
          <component
            :is="MODALITY_META[mod]?.icon"
            v-for="mod in m.input_modalities.filter((x) => x !== 'text')"
            :key="mod"
            class="size-3 text-muted-foreground shrink-0"
          />
          <Check v-if="m.id === modelValue" class="size-3.5 text-primary shrink-0" />
        </button>
      </div>
    </PopoverContent>
  </Popover>
</template>
