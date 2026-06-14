<script setup lang="ts">
/**
 * Workflow run detail — the live DAG. Polls the run while it's in flight so
 * media thumbnails and step statuses fill in as jobs complete; lets the owner
 * resolve human gates inline.
 */
import { onMounted, ref } from 'vue'
import { ArrowLeft, RefreshCw, GitFork } from 'lucide-vue-next'
import { useWorkflowRunPoller, useAsyncJobs } from '@/composables/useAsyncJobs'
import WorkflowGraph from '@/components/workflow/WorkflowGraph.vue'

definePageMeta({ layout: 'app' })

const route = useRoute()
const { t } = useI18n()
const runId = route.params.id as string
const { run, error, loading, start, refresh } = useWorkflowRunPoller(runId)
const { resolveGate, rerunStep, forkRun } = useAsyncJobs()

onMounted(() => start())

const onGate = async (payload: { stepId: string; action: 'approve' | 'reject' }) => {
  try {
    await resolveGate(runId, payload.stepId, payload.action)
  } finally {
    refresh()
  }
}

const onRerun = async (stepId: string) => {
  try {
    await rerunStep(runId, stepId)
  } finally {
    refresh()
  }
}

const forking = ref(false)
const onForkToBuilder = async () => {
  forking.value = true
  try {
    const wf = await forkRun(runId)
    await navigateTo(`/dashboard/workflows/${wf.id}/edit`)
  } finally {
    forking.value = false
  }
}

const RUN_PILL: Record<string, string> = {
  RUNNING: 'bg-sky-500/15 text-sky-600 dark:text-sky-400',
  AWAITING: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  DONE: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  FAILED: 'bg-rose-500/15 text-rose-600 dark:text-rose-400',
  PENDING: 'bg-muted text-muted-foreground',
  CANCELED: 'bg-muted text-muted-foreground',
}
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-3 py-6 sm:px-6">
    <NuxtLink
to="/dashboard/queue"
              class="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft class="size-4" /> {{ t('queue.backToQueue') }}
    </NuxtLink>

    <div v-if="loading && !run" class="py-16 text-center text-muted-foreground">
      {{ t('queue.loading') }}
    </div>
    <div v-else-if="error && !run" class="py-16 text-center text-rose-500">{{ error }}</div>

    <template v-else-if="run">
      <div class="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0">
          <h1 class="truncate text-2xl font-bold">{{ run.name || t('queue.untitledRun') }}</h1>
          <p class="text-sm text-muted-foreground">
            {{ t('queue.runHashLabel') }}{{ run.id }} ·
            {{ run.steps.length }} {{ t('queue.steps') }}
          </p>
        </div>
        <div class="flex items-center gap-2">
          <span
class="rounded-full px-2.5 py-1 text-xs font-medium"
                :class="RUN_PILL[run.status] || RUN_PILL.PENDING">{{ run.status }}</span>
          <button
class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm hover:bg-muted disabled:opacity-50"
                  :disabled="forking" @click="onForkToBuilder">
            <GitFork class="size-3.5" /> {{ t('workflows.saveAsWorkflow') }}
          </button>
          <button
class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm hover:bg-muted"
                  @click="refresh">
            <RefreshCw class="size-3.5" /> {{ t('queue.refresh') }}
          </button>
        </div>
      </div>

      <ClientOnly>
        <WorkflowGraph :run="run" @gate="onGate" @rerun="onRerun" />
        <template #fallback>
          <div class="flex h-[70vh] min-h-[420px] items-center justify-center rounded-lg border bg-muted/20 text-sm text-muted-foreground">
            {{ t('queue.loading') }}
          </div>
        </template>
      </ClientOnly>

      <p v-if="run.status === 'AWAITING'" class="mt-3 text-sm text-amber-600 dark:text-amber-400">
        {{ t('queue.awaitingHint') }}
      </p>
    </template>
  </div>
</template>
