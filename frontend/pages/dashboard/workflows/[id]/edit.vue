<script setup lang="ts">
/** Edit an existing saved workflow in the builder (PRD 11). */
import { ref, onMounted } from 'vue'
import { ArrowLeft } from 'lucide-vue-next'
import WorkflowBuilder from '@/components/workflow/WorkflowBuilder.vue'
import { useAsyncJobs, type SavedWorkflow } from '@/composables/useAsyncJobs'

definePageMeta({ layout: 'app' })

const route = useRoute()
const { t } = useI18n()
const { getWorkflow } = useAsyncJobs()
const id = Number(route.params.id)

const wf = ref<SavedWorkflow | null>(null)
const error = ref<string | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    wf.value = await getWorkflow(id)
  } catch (e: unknown) {
    error.value = (e as Error)?.message || 'Failed to load workflow'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="mx-auto w-full max-w-7xl px-3 py-6 sm:px-6">
    <NuxtLink to="/dashboard/workflows" class="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft class="size-4" /> {{ t('workflows.backToLibrary') }}
    </NuxtLink>
    <div v-if="loading" class="py-16 text-center text-muted-foreground">{{ t('queue.loading') }}</div>
    <div v-else-if="error" class="py-16 text-center text-rose-500">{{ error }}</div>
    <ClientOnly v-else-if="wf">
      <WorkflowBuilder :id="id" :initial="{ name: wf.name, description: wf.description, spec: wf.spec }" />
    </ClientOnly>
  </div>
</template>
