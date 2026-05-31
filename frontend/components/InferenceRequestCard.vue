<script setup lang="ts">
import {
  Cpu, Server, Zap, Clock, Trash2, MessageSquare, Radio, ArrowRight, Brain, Github,
} from 'lucide-vue-next'
import type { InferenceRequest } from '@/types'
import { statusVariant, formatRelative, formatLatency, totalTokens } from '@/utils/inference'

const props = withDefaults(
  defineProps<{
    request: InferenceRequest
    showOwner?: boolean
    deleting?: boolean
    // When false the card is display-only: no click-through to the (auth-gated)
    // detail page, no delete button. Used on the public profile.
    linkable?: boolean
  }>(),
  { linkable: true },
)

const emit = defineEmits<{ (e: 'delete', id: string): void }>()

const onClick = () => {
  if (props.linkable) navigateTo(`/dashboard/inference/requests/${props.request.id}`)
}
</script>

<template>
  <Card
    class="p-4 transition-colors group"
    :class="linkable ? 'hover:border-primary/50 hover:bg-accent/30 cursor-pointer' : ''"
    @click="onClick"
  >
    <!-- Header: badges + delete -->
    <div class="flex items-start justify-between gap-3">
      <div class="flex items-center gap-2 flex-wrap">
        <Badge variant="outline">{{ props.request.inference_type }}</Badge>
        <Badge :variant="statusVariant(props.request.status)">{{ props.request.status }}</Badge>
        <Badge v-if="props.request.model_name" variant="secondary" class="font-mono">
          <Cpu class="size-3" /> {{ props.request.model_name }}
        </Badge>
        <Badge v-if="props.request.provider" variant="outline">
          <Server class="size-3" /> {{ props.request.provider.name }}
        </Badge>
        <Badge v-if="props.request.streamed" variant="outline" class="text-sky-600 dark:text-sky-400">
          <Radio class="size-3" /> streamed
        </Badge>
        <Badge v-if="props.request.has_reasoning" variant="outline" class="text-amber-600 dark:text-amber-400">
          <Brain class="size-3" /> thinking
        </Badge>
        <Badge v-if="showOwner" variant="outline" class="font-mono">
          <Github class="size-3" /> {{ props.request.github_login || props.request.owner }}
        </Badge>
      </div>

      <AlertDialog v-if="props.linkable && props.request.is_owner">
        <AlertDialogTrigger as-child @click.stop>
          <Button
            variant="ghost"
            size="icon"
            class="size-8 text-muted-foreground hover:text-destructive shrink-0"
            :disabled="deleting"
            aria-label="Delete request"
          >
            <Trash2 class="size-4" />
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent @click.stop>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this inference request?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes request #{{ props.request.id }} and its stored
              prompt and response. This can't be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              class="bg-destructive text-white hover:bg-destructive/90"
              @click="emit('delete', String(props.request.id))"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>

    <!-- Prompt preview -->
    <div class="mt-3">
      <p class="text-[11px] uppercase tracking-wide text-muted-foreground mb-0.5">Prompt</p>
      <p class="text-sm line-clamp-2">{{ props.request.prompt_preview || '—' }}</p>
    </div>

    <!-- Response preview -->
    <div class="mt-2">
      <p class="text-[11px] uppercase tracking-wide text-muted-foreground mb-0.5">Response</p>
      <p class="text-sm text-muted-foreground line-clamp-2">{{ props.request.response_preview || '—' }}</p>
    </div>

    <!-- Footer metadata -->
    <div class="mt-3 pt-3 border-t flex items-center gap-4 flex-wrap text-xs text-muted-foreground">
      <span class="inline-flex items-center gap-1" title="Messages in this request">
        <MessageSquare class="size-3.5" /> {{ props.request.message_count ?? 0 }} msg
      </span>
      <span v-if="totalTokens(props.request) !== null" class="inline-flex items-center gap-1" title="Token usage">
        <Zap class="size-3.5" /> {{ totalTokens(props.request) }} tok
        <template v-if="props.request.usage">
          ({{ props.request.usage.prompt_tokens ?? '?' }} in / {{ props.request.usage.completion_tokens ?? '?' }} out)
        </template>
      </span>
      <span class="inline-flex items-center gap-1" title="Latency">
        <Clock class="size-3.5" /> {{ formatLatency(props.request.latency_ms) }}
      </span>
      <span class="ml-auto inline-flex items-center gap-1" :class="linkable ? 'group-hover:text-foreground' : ''">
        {{ formatRelative(props.request.created_on) }}
        <ArrowRight v-if="linkable" class="size-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
      </span>
    </div>
  </Card>
</template>
