<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import {
  ArrowLeft, Trash2, Cpu, Server, Zap, Clock, Radio, ChevronDown, Brain, Github, Gauge,
} from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import { useInferenceRequestStore } from '@/stores/inferenceRequest'
import {
  statusVariant, formatAbsolute, formatLatency, totalTokens, roleClasses,
} from '@/utils/inference'

definePageMeta({
  layout: 'app',
})

const route = useRoute()
const store = useInferenceRequestStore()
const id = computed(() => String(route.params.id))

const req = computed(() => store.currentRequest)

const finishReason = computed<string | null>(() => {
  const choices = (req.value?.results as any)?.choices
  if (Array.isArray(choices) && choices[0]?.finish_reason) {
    return String(choices[0].finish_reason)
  }
  return null
})

// Sampling/other request parameters (everything in the payload that isn't the
// message content or model name), shown as a key/value grid.
const params = computed(() => {
  const p = req.value?.payload
  if (!p || typeof p !== 'object') return []
  const skip = new Set(['messages', 'prompt', 'model'])
  return Object.entries(p)
    .filter(([k]) => !skip.has(k))
    .map(([k, v]) => ({
      key: k,
      value: typeof v === 'object' ? JSON.stringify(v) : String(v),
    }))
})

const prettyPayload = computed(() =>
  req.value ? JSON.stringify(req.value.payload ?? {}, null, 2) : ''
)
const prettyResults = computed(() =>
  req.value ? JSON.stringify(req.value.results ?? {}, null, 2) : ''
)

const remove = async () => {
  try {
    await store.deleteRequest(id.value)
    toast.success('Inference request deleted')
    navigateTo('/dashboard/inference/requests')
  } catch {
    toast.error('Failed to delete inference request')
  }
}

onMounted(() => {
  store.fetchRequest(id.value).catch(() => {})
})
</script>

<template>
  <div class="container mx-auto py-6 max-w-4xl">
    <!-- Top bar -->
    <div class="flex items-center justify-between mb-6">
      <NuxtLink
        to="/dashboard/inference/requests"
        class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft class="size-4" /> Back to requests
      </NuxtLink>

      <AlertDialog v-if="req && req.is_owner">
        <AlertDialogTrigger as-child>
          <Button variant="outline" size="sm" class="text-destructive hover:text-destructive">
            <Trash2 class="size-4" /> Delete
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this inference request?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes request #{{ id }} and its stored prompt and
              response. This can't be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              class="bg-destructive text-white hover:bg-destructive/90"
              @click="remove"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>

    <!-- Loading -->
    <div v-if="store.loading && !req" class="space-y-4">
      <div class="h-8 w-64 bg-muted rounded animate-pulse" />
      <Card class="p-4 animate-pulse h-40" />
      <Card class="p-4 animate-pulse h-64" />
    </div>

    <div v-else-if="store.error" class="text-destructive text-center py-12">
      {{ store.error }}
    </div>

    <template v-else-if="req">
      <!-- Title + status badges -->
      <div class="mb-4">
        <h1 class="text-2xl font-bold">Request #{{ req.id }}</h1>
        <div class="flex items-center gap-2 flex-wrap mt-2">
          <Badge variant="outline">{{ req.inference_type }}</Badge>
          <Badge :variant="statusVariant(req.status)">{{ req.status }}</Badge>
          <Badge v-if="req.streamed" variant="outline" class="text-sky-600 dark:text-sky-400">
            <Radio class="size-3" /> streamed
          </Badge>
          <Badge v-if="finishReason" variant="secondary">finish: {{ finishReason }}</Badge>
          <a
            v-if="req.github_login"
            :href="`https://github.com/${req.github_login}`"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-md border font-mono hover:bg-accent hover:text-accent-foreground transition-colors"
            @click.stop
          >
            <Github class="h-3 w-3" /> {{ req.github_login }}
          </a>
          <Badge v-else-if="req.owner" variant="outline" class="font-mono">
            <Github class="size-3" /> {{ req.owner }}
          </Badge>
        </div>
      </div>

      <!-- Metadata grid -->
      <Card class="p-4 mb-4">
        <dl class="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-3 text-sm">
          <div>
            <dt class="text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1">
              <Cpu class="size-3" /> Model
            </dt>
            <dd class="font-mono mt-0.5 break-all">{{ req.model_name || '—' }}</dd>
          </div>
          <div>
            <dt class="text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1">
              <Server class="size-3" /> Provider
            </dt>
            <dd class="mt-0.5">{{ req.provider?.name || '—' }}</dd>
          </div>
          <div>
            <dt class="text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1">
              <Clock class="size-3" /> Latency
            </dt>
            <dd class="mt-0.5">{{ formatLatency(req.latency_ms) }}</dd>
          </div>
          <div v-if="req.ttft_ms != null">
            <dt class="text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1">
              <Clock class="size-3" /> TTFT
            </dt>
            <dd class="mt-0.5">{{ req.ttft_ms }} ms</dd>
          </div>
          <div v-if="req.tokens_per_second != null">
            <dt class="text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1">
              <Gauge class="size-3" /> Throughput
            </dt>
            <dd class="mt-0.5">{{ req.tokens_per_second }} tok/s</dd>
          </div>
          <div>
            <dt class="text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1">
              <Zap class="size-3" /> Tokens
            </dt>
            <dd class="mt-0.5">
              <template v-if="totalTokens(req) !== null">
                {{ totalTokens(req) }} total
                <span class="text-muted-foreground">
                  ({{ req.usage?.prompt_tokens ?? '?' }} in / {{ req.usage?.completion_tokens ?? '?' }} out)
                </span>
              </template>
              <template v-else>—</template>
            </dd>
          </div>
          <div>
            <dt class="text-xs uppercase tracking-wide text-muted-foreground">Created</dt>
            <dd class="mt-0.5">{{ formatAbsolute(req.created_on) }}</dd>
          </div>
          <div>
            <dt class="text-xs uppercase tracking-wide text-muted-foreground">Last updated</dt>
            <dd class="mt-0.5">{{ formatAbsolute(req.modified_on) }}</dd>
          </div>
        </dl>

        <template v-if="params.length">
          <Separator class="my-4" />
          <p class="text-xs uppercase tracking-wide text-muted-foreground mb-2">Request parameters</p>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="p in params"
              :key="p.key"
              class="inline-flex items-center gap-1 rounded-md border bg-muted/40 px-2 py-0.5 text-xs font-mono"
            >
              <span class="text-muted-foreground">{{ p.key }}:</span> {{ p.value }}
            </span>
          </div>
        </template>
      </Card>

      <!-- Conversation -->
      <Card class="p-4 mb-4">
        <h2 class="text-lg font-semibold mb-3">
          Conversation
          <span class="text-sm font-normal text-muted-foreground">
            ({{ req.messages?.length ?? 0 }} message{{ (req.messages?.length ?? 0) === 1 ? '' : 's' }})
          </span>
        </h2>
        <div v-if="!req.messages?.length" class="text-sm text-muted-foreground">
          No messages recorded for this request.
        </div>
        <div v-else class="space-y-3">
          <div
            v-for="(m, i) in req.messages"
            :key="i"
            class="rounded-lg border p-3"
          >
            <div class="mb-2">
              <span
                class="inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium capitalize"
                :class="roleClasses(m.role)"
              >
                {{ m.role || 'message' }}
              </span>
            </div>
            <MarkdownRenderer :content="m.content" />
          </div>
        </div>
      </Card>

      <!-- Thinking / reasoning trace -->
      <Card v-if="req.reasoning" class="p-4 mb-4">
        <Collapsible :default-open="true">
          <CollapsibleTrigger class="flex w-full items-center justify-between gap-2 text-lg font-semibold">
            <span class="flex items-center gap-2">
              <Brain class="size-4 text-amber-500" /> Thinking
              <Badge variant="outline" class="text-amber-600 dark:text-amber-400 font-normal">
                reasoning trace
              </Badge>
            </span>
            <ChevronDown class="size-4 shrink-0" />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div class="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-sm text-muted-foreground">
              <MarkdownRenderer :content="req.reasoning" />
            </div>
          </CollapsibleContent>
        </Collapsible>
      </Card>

      <!-- Response -->
      <Card class="p-4 mb-4">
        <h2 class="text-lg font-semibold mb-3 flex items-center gap-2">
          Response
          <Badge v-if="req.streamed" variant="outline" class="text-sky-600 dark:text-sky-400">
            <Radio class="size-3" /> streamed
          </Badge>
        </h2>
        <div
          v-if="req.response_text"
          class="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3"
        >
          <MarkdownRenderer :content="req.response_text" />
        </div>
        <div v-else class="text-sm text-muted-foreground">
          No response content stored
          <template v-if="req.status === 'REQUESTED'">— the upstream request failed.</template>
        </div>
      </Card>

      <!-- Raw JSON -->
      <div class="space-y-3">
        <Collapsible>
          <CollapsibleTrigger
            class="flex w-full items-center justify-between rounded-md border bg-muted/40 px-4 py-2 text-sm font-medium hover:bg-muted/60"
          >
            Raw request payload
            <ChevronDown class="size-4" />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <pre class="mt-2 overflow-x-auto rounded-md bg-zinc-950 p-4 text-xs text-zinc-100">{{ prettyPayload }}</pre>
          </CollapsibleContent>
        </Collapsible>

        <Collapsible>
          <CollapsibleTrigger
            class="flex w-full items-center justify-between rounded-md border bg-muted/40 px-4 py-2 text-sm font-medium hover:bg-muted/60"
          >
            Raw result
            <ChevronDown class="size-4" />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <pre class="mt-2 overflow-x-auto rounded-md bg-zinc-950 p-4 text-xs text-zinc-100">{{ prettyResults }}</pre>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </template>
  </div>
</template>
