<script setup lang="ts">
/**
 * Workflow library (PRD 11): your saved, reusable workflows plus the curated
 * templates you can fork into the builder. Distinct from /dashboard/queue,
 * which shows live runs.
 */
import { onMounted, ref } from 'vue'
import { Workflow as WorkflowIcon, Plus, Play, Pencil, Trash2, GitFork,
  BookOpen, Images, Clapperboard, Music, Mic, HardHat, Newspaper, Loader2 } from 'lucide-vue-next'
import { useAsyncJobs, type SavedWorkflowSummary, type WorkflowTemplate } from '@/composables/useAsyncJobs'

definePageMeta({ layout: 'app', requireAuth: true, gateTitleKey: 'dashboard.items.workflows' })

const { t } = useI18n()
const { listWorkflows, deleteWorkflow, runSavedWorkflow, listTemplates, forkTemplate } = useAsyncJobs()

const workflows = ref<SavedWorkflowSummary[]>([])
const templates = ref<WorkflowTemplate[]>([])
const loading = ref(true)
const busy = ref<number | string | null>(null)

const ICONS: Record<string, unknown> = { BookOpen, Images, Clapperboard, Music, Mic, HardHat, Newspaper, Workflow: WorkflowIcon }
const iconFor = (n: string) => ICONS[n] || WorkflowIcon

const load = async () => {
  try {
    const [w, tpl] = await Promise.all([
      listWorkflows().catch(() => []),
      listTemplates().catch(() => []),
    ])
    workflows.value = w
    templates.value = tpl
  } finally {
    loading.value = false
  }
}
onMounted(load)

const onRun = async (id: number) => {
  busy.value = id
  try {
    const run = await runSavedWorkflow(id)
    await navigateTo(`/dashboard/queue/runs/${run.id}`)
  } catch {
    // A workflow with required inputs opens in the builder's run modal instead.
    await navigateTo(`/dashboard/workflows/${id}/edit`)
  } finally {
    busy.value = null
  }
}
const onDelete = async (id: number) => {
  if (!confirm(t('workflows.confirmDelete'))) return
  await deleteWorkflow(id).catch(() => {})
  load()
}
const onFork = async (key: string) => {
  busy.value = `tpl-${key}`
  try {
    const wf = await forkTemplate(key)
    await navigateTo(`/dashboard/workflows/${wf.id}/edit`)
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-3 py-6 sm:px-6">
    <div class="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="flex items-center gap-2 text-2xl font-bold"><WorkflowIcon class="size-6" /> {{ t('workflows.title') }}</h1>
        <p class="text-sm text-muted-foreground">{{ t('workflows.subtitle') }}</p>
      </div>
      <NuxtLink
to="/dashboard/workflows/new"
                class="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90">
        <Plus class="size-4" /> {{ t('workflows.create') }}
      </NuxtLink>
    </div>

    <div v-if="loading" class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <div v-for="i in 3" :key="i" class="h-28 animate-pulse rounded-lg border bg-muted/40" />
    </div>

    <template v-else>
      <!-- saved workflows -->
      <section class="mb-8">
        <h2 class="mb-3 text-lg font-semibold">{{ t('workflows.yours') }}</h2>
        <p v-if="!workflows.length" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          {{ t('workflows.empty') }}
        </p>
        <div v-else class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div v-for="w in workflows" :key="w.id" class="flex flex-col rounded-lg border bg-background p-4">
            <div class="mb-1 flex items-start justify-between gap-2">
              <span class="truncate font-semibold" :title="w.name">{{ w.name }}</span>
            </div>
            <p class="mb-3 line-clamp-2 flex-1 text-sm text-muted-foreground">{{ w.description || '—' }}</p>
            <div class="mb-3 flex gap-2 text-xs text-muted-foreground">
              <span>{{ w.step_count }} {{ t('queue.steps') }}</span>
              <span v-if="w.run_count">· {{ w.run_count }} {{ t('workflows.runs') }}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <button
class="inline-flex flex-1 items-center justify-center gap-1.5 rounded-md bg-primary px-2.5 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
                      :disabled="busy === w.id" @click="onRun(w.id)">
                <Loader2 v-if="busy === w.id" class="size-3.5 animate-spin" /><Play v-else class="size-3.5" /> {{ t('workflows.run') }}
              </button>
              <NuxtLink
:to="`/dashboard/workflows/${w.id}/edit`"
                        class="rounded-md border p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" :title="t('workflows.edit')">
                <Pencil class="size-4" />
              </NuxtLink>
              <button
class="rounded-md border p-1.5 text-muted-foreground hover:bg-muted hover:text-rose-500" :title="t('workflows.delete')"
                      @click="onDelete(w.id)"><Trash2 class="size-4" /></button>
            </div>
          </div>
        </div>
      </section>

      <!-- templates to fork -->
      <section>
        <h2 class="mb-1 text-lg font-semibold">{{ t('workflows.startFrom') }}</h2>
        <p class="mb-3 text-sm text-muted-foreground">{{ t('workflows.startFromHint') }}</p>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div v-for="tpl in templates" :key="tpl.key" class="flex flex-col rounded-lg border bg-background p-4">
            <div class="mb-2 flex items-center gap-2">
              <span class="flex size-9 items-center justify-center rounded-md bg-primary/10 text-primary">
                <component :is="iconFor(tpl.icon)" class="size-5" />
              </span>
              <span class="font-semibold">{{ tpl.title }}</span>
            </div>
            <p class="mb-3 flex-1 text-sm text-muted-foreground">{{ tpl.description }}</p>
            <button
class="inline-flex items-center justify-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm hover:border-primary hover:bg-muted/50 disabled:opacity-50"
                    :disabled="busy === `tpl-${tpl.key}`" @click="onFork(tpl.key)">
              <Loader2 v-if="busy === `tpl-${tpl.key}`" class="size-3.5 animate-spin" /><GitFork v-else class="size-3.5" />
              {{ t('workflows.fork') }}
            </button>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
