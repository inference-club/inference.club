<script setup lang="ts">
// Compact one-line row for the "narrow" view of the requests list — a dense
// alternative to the full InferenceRequestCard. Same click-through + delete.
import { computed } from 'vue'
import { Clock, Zap, Trash2 } from 'lucide-vue-next'
import type { InferenceRequest } from '@/types'
import { statusVariant, statusLabel, formatRelative, formatLatency, totalTokens } from '@/utils/inference'

const props = defineProps<{ request: InferenceRequest; deleting?: boolean }>()
const emit = defineEmits<{ (e: 'delete', id: string): void }>()

const showStatus = computed(
  () => props.request.status !== 'PROCESSED' && props.request.status !== 'SAVED',
)
const preview = computed(
  () => props.request.prompt_preview || props.request.response_preview || props.request.model_name || '—',
)
const go = () => {
  const ref = props.request.public_id || props.request.id
  navigateTo(`/dashboard/inference/requests/${ref}`)
}
</script>

<template>
  <div
    class="group flex items-center gap-3 rounded-md border px-3 py-2 min-w-0 cursor-pointer transition-colors hover:border-primary/50 hover:bg-accent/30"
    @click="go"
  >
    <ModalityBadge :type="request.inference_type" />
    <span class="min-w-0 flex-1 truncate text-sm">{{ preview }}</span>

    <Badge v-if="showStatus" :variant="statusVariant(request.status)" class="shrink-0">
      {{ statusLabel(request.status) }}
    </Badge>
    <span
      v-if="request.model_name"
      class="hidden md:inline max-w-[11rem] truncate font-mono text-xs text-muted-foreground shrink-0"
      :title="request.model_name"
    >{{ request.model_name }}</span>
    <span
      v-if="totalTokens(request) !== null"
      class="hidden sm:inline-flex items-center gap-1 text-xs text-muted-foreground shrink-0 tabular-nums"
    >
      <Zap class="size-3" /> {{ totalTokens(request) }}
    </span>
    <span class="hidden lg:inline-flex items-center gap-1 text-xs text-muted-foreground shrink-0 tabular-nums">
      <Clock class="size-3" /> {{ formatLatency(request.latency_ms) }}
    </span>
    <span class="text-xs text-muted-foreground shrink-0 w-16 text-right tabular-nums">
      {{ formatRelative(request.created_on) }}
    </span>

    <AlertDialog v-if="request.is_owner">
      <AlertDialogTrigger as-child @click.stop>
        <Button
          variant="ghost"
          size="icon"
          class="size-7 text-muted-foreground hover:text-destructive shrink-0"
          :disabled="deleting"
          aria-label="Delete request"
        >
          <Trash2 class="size-3.5" />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent @click.stop>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this inference request?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes this request and its stored prompt and
            response. This can't be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            class="bg-destructive text-white hover:bg-destructive/90"
            @click="emit('delete', String(request.id))"
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
