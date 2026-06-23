<script setup lang="ts">
/** Blank-canvas workflow builder (PRD 11). */
import { ArrowLeft } from 'lucide-vue-next'
import WorkflowBuilder from '@/components/workflow/WorkflowBuilder.vue'

definePageMeta({ layout: 'app', requireAuth: true, gateTitleKey: 'dashboard.items.workflows' })
const { t } = useI18n()

const initial = { name: 'Untitled workflow', description: '', spec: { steps: [] } }
</script>

<template>
  <div class="mx-auto w-full max-w-7xl px-3 py-6 sm:px-6">
    <NuxtLink to="/dashboard/workflows" class="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft class="size-4" /> {{ t('workflows.backToLibrary') }}
    </NuxtLink>
    <ClientOnly>
      <WorkflowBuilder :id="null" :initial="initial" />
      <template #fallback>
        <div class="flex h-[60vh] items-center justify-center rounded-lg border bg-muted/20 text-sm text-muted-foreground">{{ t('queue.loading') }}</div>
      </template>
    </ClientOnly>
  </div>
</template>
