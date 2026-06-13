<script setup lang="ts">
/**
 * Queue dashboard: your async jobs + workflow runs, with a one-click demo that
 * launches a fan-out workflow so the live DAG viewer has something to show.
 */
import { onMounted, onUnmounted, ref } from 'vue'
import { useIntervalFn } from '@vueuse/core'
import { Workflow as WorkflowIcon, Play, Loader2, CheckCircle2, XCircle,
  Clock, Hand, RotateCcw, Ban } from 'lucide-vue-next'
import { useAsyncJobs, type AsyncJob, type WorkflowRunSummary } from '@/composables/useAsyncJobs'

definePageMeta({ layout: 'app' })

const { t } = useI18n()
const config = useRuntimeConfig()
const { listJobs, listRuns, queueSummary, startRun, cancelJob, retryJob } = useAsyncJobs()

const jobs = ref<AsyncJob[]>([])
const runs = ref<WorkflowRunSummary[]>([])
const summary = ref<{ active: number; jobs: Record<string, number> } | null>(null)
const loading = ref(true)
const launching = ref(false)

const load = async () => {
  try {
    const [j, r, s] = await Promise.all([
      listJobs({ limit: 40 }).catch(() => []),
      listRuns().catch(() => []),
      queueSummary().catch(() => null),
    ])
    jobs.value = j
    runs.value = r
    summary.value = s
  } finally {
    loading.value = false
  }
}

onMounted(load)
// Keep the lists fresh while work is draining.
const { pause, resume } = useIntervalFn(load, 4000, { immediate: false })
onMounted(() => resume())
onUnmounted(() => pause())

// --- one-click demo workflow ---
const firstImageModel = async (): Promise<string> => {
  try {
    const res = await $fetch<{ data: { id: string; service_type?: string }[] }>(
      `${config.public.apiBase}/v1/models`, { credentials: 'include' },
    )
    const img = res.data.find((m) => m.service_type === 'image')
    return img?.id || res.data[0]?.id || 'flux'
  } catch {
    return 'flux'
  }
}

const runDemo = async () => {
  launching.value = true
  try {
    const model = await firstImageModel()
    const spec = {
      name: 'Demo — prompt fan-out',
      steps: [
        { id: 'ideas', kind: 'transform', op: 'passthrough', title: 'Scene ideas',
          input: ['a neon city skyline at night', 'a serene misty forest at dawn',
                  'a vast cosmic nebula in violet'] },
        { id: 'images', kind: 'map', type: 'image', model, title: 'Generate images',
          over: '{{steps.ideas.output}}', body: { prompt: '{{item}}' } },
        { id: 'review', kind: 'gate', depends_on: ['images'], title: 'Review & approve' },
      ],
    }
    const run = await startRun(spec, {}, spec.name)
    await navigateTo(`/dashboard/queue/runs/${run.id}`)
  } finally {
    launching.value = false
  }
}

const STATUS_ICON: Record<string, unknown> = {
  QUEUED: Clock, PROCESSING: Loader2, PROCESSED: CheckCircle2,
  FAILED: XCircle, CANCELED: Ban, REQUESTED: XCircle,
}
const STATUS_CLASS: Record<string, string> = {
  QUEUED: 'text-muted-foreground', PROCESSING: 'text-sky-500',
  PROCESSED: 'text-emerald-500', FAILED: 'text-rose-500',
  CANCELED: 'text-muted-foreground', REQUESTED: 'text-rose-500',
}
const RUN_PILL: Record<string, string> = {
  RUNNING: 'bg-sky-500/15 text-sky-600 dark:text-sky-400',
  AWAITING: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  DONE: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  FAILED: 'bg-rose-500/15 text-rose-600 dark:text-rose-400',
  PENDING: 'bg-muted text-muted-foreground', CANCELED: 'bg-muted text-muted-foreground',
}

const onCancel = async (id: string | number) => { await cancelJob(id).catch(() => {}); load() }
const onRetry = async (id: string | number) => { await retryJob(id).catch(() => {}); load() }
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-3 py-6 sm:px-6">
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">{{ t('queue.title') }}</h1>
        <p class="text-sm text-muted-foreground">{{ t('queue.subtitle') }}</p>
      </div>
      <button
        class="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        :disabled="launching" @click="runDemo">
        <Loader2 v-if="launching" class="size-4 animate-spin" />
        <Play v-else class="size-4" />
        {{ t('queue.runDemo') }}
      </button>
    </div>

    <!-- summary -->
    <div v-if="summary" class="mb-6 grid grid-cols-3 gap-3 sm:max-w-md">
      <div class="rounded-lg border bg-background p-3 text-center">
        <div class="text-2xl font-bold text-sky-500">{{ summary.active }}</div>
        <div class="text-xs text-muted-foreground">{{ t('queue.active') }}</div>
      </div>
      <div class="rounded-lg border bg-background p-3 text-center">
        <div class="text-2xl font-bold text-emerald-500">{{ summary.jobs?.PROCESSED || 0 }}</div>
        <div class="text-xs text-muted-foreground">{{ t('queue.done') }}</div>
      </div>
      <div class="rounded-lg border bg-background p-3 text-center">
        <div class="text-2xl font-bold text-rose-500">{{ summary.jobs?.FAILED || 0 }}</div>
        <div class="text-xs text-muted-foreground">{{ t('queue.failed') }}</div>
      </div>
    </div>

    <div v-if="loading" class="py-16 text-center text-muted-foreground">{{ t('queue.loading') }}</div>

    <template v-else>
      <!-- workflow runs -->
      <section class="mb-8">
        <h2 class="mb-3 flex items-center gap-2 text-lg font-semibold">
          <WorkflowIcon class="size-5" /> {{ t('queue.workflows') }}
        </h2>
        <p v-if="!runs.length" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          {{ t('queue.noWorkflows') }}
        </p>
        <div v-else class="grid gap-2">
          <NuxtLink v-for="r in runs" :key="r.id" :to="`/dashboard/queue/runs/${r.id}`"
                    class="flex items-center justify-between gap-3 rounded-lg border bg-background p-3 hover:bg-muted/50">
            <div class="flex min-w-0 items-center gap-2">
              <Hand v-if="r.status === 'AWAITING'" class="size-4 shrink-0 text-amber-500" />
              <WorkflowIcon v-else class="size-4 shrink-0 text-muted-foreground" />
              <span class="truncate font-medium">{{ r.name || t('queue.untitledRun') }}</span>
              <span class="shrink-0 text-xs text-muted-foreground">· {{ r.step_count }} {{ t('queue.steps') }}</span>
            </div>
            <span class="shrink-0 rounded-full px-2 py-0.5 text-xs font-medium"
                  :class="RUN_PILL[r.status] || RUN_PILL.PENDING">{{ r.status }}</span>
          </NuxtLink>
        </div>
      </section>

      <!-- jobs -->
      <section>
        <h2 class="mb-3 text-lg font-semibold">{{ t('queue.jobs') }}</h2>
        <p v-if="!jobs.length" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          {{ t('queue.noJobs') }}
        </p>
        <div v-else class="overflow-hidden rounded-lg border">
          <div v-for="job in jobs" :key="job.id"
               class="flex items-center justify-between gap-3 border-b bg-background p-3 last:border-b-0">
            <div class="flex min-w-0 items-center gap-2.5">
              <component :is="STATUS_ICON[job.status] || Clock" class="size-4 shrink-0"
                         :class="[STATUS_CLASS[job.status], job.status === 'PROCESSING' ? 'animate-spin' : '']" />
              <span class="rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold uppercase">{{ job.inference_type }}</span>
              <span class="truncate text-sm">{{ job.prompt_preview || job.model_name || `#${job.id}` }}</span>
            </div>
            <div class="flex shrink-0 items-center gap-2">
              <span class="text-xs text-muted-foreground">{{ job.status }}</span>
              <button v-if="job.status === 'QUEUED' || job.status === 'PROCESSING'"
                      class="rounded p-1 text-muted-foreground hover:bg-muted hover:text-rose-500"
                      :title="t('queue.cancel')" @click="onCancel(job.id)"><Ban class="size-4" /></button>
              <button v-else-if="job.status === 'FAILED' || job.status === 'CANCELED'"
                      class="rounded p-1 text-muted-foreground hover:bg-muted hover:text-sky-500"
                      :title="t('queue.retry')" @click="onRetry(job.id)"><RotateCcw class="size-4" /></button>
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
