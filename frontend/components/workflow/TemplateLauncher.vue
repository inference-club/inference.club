<script setup lang="ts">
/**
 * Sample-workflow gallery + dynamic input form. Each template declares an
 * input schema; picking one opens a form built from that schema. On submit we
 * start a run and jump to the live DAG viewer. Models are resolved server-side
 * from what the user can route to, so templates "just work".
 */
import { onMounted, ref } from 'vue'
import { BookOpen, Images, Clapperboard, Music, Mic, Workflow as WorkflowIcon,
  Loader2, X, Sparkles } from 'lucide-vue-next'
import { useAsyncJobs, type WorkflowTemplate } from '@/composables/useAsyncJobs'

const { t } = useI18n()
const { listTemplates, startFromTemplate } = useAsyncJobs()

const templates = ref<WorkflowTemplate[]>([])
const loading = ref(true)
const active = ref<WorkflowTemplate | null>(null)
const form = ref<Record<string, string | number>>({})
const submitting = ref(false)
const error = ref<string | null>(null)

const ICONS: Record<string, unknown> = {
  BookOpen, Images, Clapperboard, Music, Mic, Workflow: WorkflowIcon,
}
const iconFor = (name: string) => ICONS[name] || WorkflowIcon

onMounted(async () => {
  try {
    templates.value = await listTemplates()
  } finally {
    loading.value = false
  }
})

const open = (tpl: WorkflowTemplate) => {
  active.value = tpl
  error.value = null
  const f: Record<string, string | number> = {}
  for (const inp of tpl.inputs) f[inp.name] = inp.default ?? ''
  form.value = f
}
const close = () => { active.value = null }

const submit = async () => {
  if (!active.value) return
  submitting.value = true
  error.value = null
  try {
    const run = await startFromTemplate(active.value.key, { ...form.value })
    await navigateTo(`/dashboard/queue/runs/${run.id}`)
  } catch (e: unknown) {
    const data = (e as { data?: { error?: { message?: string } } })?.data
    error.value = data?.error?.message || (e as Error)?.message || 'Failed to start'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="mb-8">
    <h2 class="mb-3 flex items-center gap-2 text-lg font-semibold">
      <Sparkles class="size-5" /> {{ t('queue.templatesTitle') }}
    </h2>
    <p class="mb-3 text-sm text-muted-foreground">{{ t('queue.templatesSubtitle') }}</p>

    <div v-if="loading" class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <div v-for="i in 3" :key="i" class="h-28 animate-pulse rounded-lg border bg-muted/40" />
    </div>
    <div v-else class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <button v-for="tpl in templates" :key="tpl.key"
              class="group flex flex-col rounded-lg border bg-background p-4 text-left transition hover:border-primary hover:shadow-sm"
              @click="open(tpl)">
        <div class="mb-2 flex items-center gap-2">
          <span class="flex size-9 items-center justify-center rounded-md bg-primary/10 text-primary">
            <component :is="iconFor(tpl.icon)" class="size-5" />
          </span>
          <span class="font-semibold">{{ tpl.title }}</span>
        </div>
        <p class="flex-1 text-sm text-muted-foreground">{{ tpl.description }}</p>
        <span class="mt-2 text-xs text-muted-foreground">{{ tpl.step_count }} {{ t('queue.steps') }}</span>
      </button>
    </div>

    <!-- input form modal -->
    <div v-if="active" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
         @click.self="close">
      <div class="w-full max-w-md rounded-xl border bg-background p-5 shadow-xl">
        <div class="mb-4 flex items-start justify-between gap-3">
          <div class="flex items-center gap-2">
            <component :is="iconFor(active.icon)" class="size-5 text-primary" />
            <h3 class="text-lg font-semibold">{{ active.title }}</h3>
          </div>
          <button class="rounded p-1 text-muted-foreground hover:bg-muted" @click="close">
            <X class="size-4" />
          </button>
        </div>
        <p class="mb-4 text-sm text-muted-foreground">{{ active.description }}</p>

        <form class="space-y-3" @submit.prevent="submit">
          <div v-for="inp in active.inputs" :key="inp.name">
            <label class="mb-1 block text-sm font-medium">
              {{ inp.label }}<span v-if="inp.required" class="text-rose-500"> *</span>
            </label>
            <textarea v-if="inp.type === 'textarea'" v-model="form[inp.name]"
                      :placeholder="inp.placeholder" rows="3"
                      class="w-full rounded-md border bg-background px-3 py-2 text-sm" />
            <select v-else-if="inp.type === 'select'" v-model="form[inp.name]"
                    class="w-full rounded-md border bg-background px-3 py-2 text-sm">
              <option v-for="o in inp.options || []" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
            <input v-else-if="inp.type === 'number'" v-model.number="form[inp.name]" type="number"
                   :min="inp.min" :max="inp.max"
                   class="w-full rounded-md border bg-background px-3 py-2 text-sm" />
            <input v-else v-model="form[inp.name]" type="text" :placeholder="inp.placeholder"
                   class="w-full rounded-md border bg-background px-3 py-2 text-sm" />
          </div>

          <p v-if="error" class="text-sm text-rose-500">{{ error }}</p>

          <div class="flex justify-end gap-2 pt-1">
            <button type="button" class="rounded-md border px-3 py-2 text-sm hover:bg-muted" @click="close">
              {{ t('queue.cancel') }}
            </button>
            <button type="submit" :disabled="submitting"
                    class="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50">
              <Loader2 v-if="submitting" class="size-4 animate-spin" />
              {{ t('queue.runWorkflow') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>
