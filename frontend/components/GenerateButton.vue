<script setup lang="ts">
// The playground's primary action button, with an optional split dropdown on
// its right edge for queueing N requests at once. A plain click runs the
// synchronous generation (the existing path); the dropdown emits `queue` with a
// count, which the page turns into N async jobs via useQueueGenerations.
import { computed, type Component } from 'vue'
import { ChevronDown, ListPlus, Loader2, Sparkles } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const props = withDefaults(
  defineProps<{
    /** Disable the primary (synchronous) run action — e.g. while a generation
     *  is already in flight or the form is incomplete. */
    disabled?: boolean
    /** Disable the queue dropdown. Defaults to `disabled`; pass a looser
     *  condition (e.g. ignoring `running`) to keep queueing async jobs while a
     *  sync generation is busy. */
    queueDisabled?: boolean
    /** Show the spinner + treat the primary action as in-flight. */
    running?: boolean
    label?: string
    /** Idle icon for the primary button (a lucide component). */
    icon?: Component
    /** Show the queue split dropdown. Off for pages where async isn't supported. */
    queueable?: boolean
    /** Preset counts offered in the dropdown. */
    counts?: number[]
    /** Singular noun for the menu labels ("image", "song", …). */
    noun?: string
  }>(),
  {
    disabled: false,
    queueDisabled: undefined,
    running: false,
    label: 'Generate',
    icon: undefined,
    queueable: true,
    counts: () => [2, 3, 5, 10],
    noun: 'request',
  },
)

const emit = defineEmits<{
  (e: 'generate'): void
  (e: 'queue', count: number): void
}>()

// The queue chevron defaults to the same gate as the primary button, but a page
// can pass `queueDisabled` to keep queueing live while the sync run is busy.
const queueOff = computed(() =>
  props.queueDisabled === undefined ? props.disabled : props.queueDisabled,
)
</script>

<template>
  <div class="inline-flex shrink-0 items-stretch">
    <Button
      :disabled="disabled"
      class="gap-2"
      :class="queueable ? 'rounded-r-none' : ''"
      @click="emit('generate')"
    >
      <component
        :is="running ? Loader2 : (props.icon ?? Sparkles)"
        class="size-4"
        :class="running ? 'animate-spin' : ''"
      />
      {{ label }}
    </Button>

    <DropdownMenu v-if="queueable">
      <DropdownMenuTrigger as-child>
        <Button
          :disabled="queueOff"
          class="rounded-l-none border-l border-primary-foreground/25 px-1.5"
          :aria-label="`Queue several ${label.toLowerCase()} requests`"
        >
          <ChevronDown class="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" class="w-56">
        <DropdownMenuLabel class="flex items-center gap-2 text-xs font-normal text-muted-foreground">
          <ListPlus class="size-3.5" /> Queue several (runs one at a time)
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          v-for="c in counts"
          :key="c"
          class="justify-between"
          @select="emit('queue', c)"
        >
          <span>Queue {{ c }}</span>
          <span class="text-xs text-muted-foreground">{{ c }} {{ noun }}s</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
</template>
