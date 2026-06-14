<script setup lang="ts">
/**
 * A rich custom node for the Vue Flow workflow graph. Shows everything about a
 * step at a glance: modality, kind, status, the model used, live media
 * thumbnails, per-job progress, timing, and gate controls / errors.
 */
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { CheckCircle2, Circle, Clock, Loader2, XCircle, Music, FileText,
  GitFork, Hand, Wrench, Layers } from 'lucide-vue-next'
import { modalityHex } from '@/composables/useClusterState'
import type { WorkflowStep, AsyncJob } from '@/composables/useAsyncJobs'

const props = defineProps<{
  data: { step: WorkflowStep; onGate?: (stepId: string, action: 'approve' | 'reject') => void }
}>()

const step = computed(() => props.data.step)

const KIND_ICON: Record<string, unknown> = {
  inference: FileText, map: GitFork, transform: Wrench, collect: Layers, gate: Hand,
}
const KIND_LABEL: Record<string, string> = {
  inference: 'Inference', map: 'Fan-out', transform: 'Transform', collect: 'Collect', gate: 'Human gate',
}
const STATUS: Record<string, { ring: string; pill: string; label: string; glow: string }> = {
  PENDING: { ring: 'border-border', pill: 'bg-muted text-muted-foreground', label: 'Pending', glow: '' },
  RUNNING: { ring: 'border-sky-400', pill: 'bg-sky-500/15 text-sky-600 dark:text-sky-400', label: 'Running', glow: 'shadow-[0_0_0_3px_rgba(56,189,248,0.15)]' },
  AWAITING: { ring: 'border-amber-400', pill: 'bg-amber-500/15 text-amber-600 dark:text-amber-400', label: 'Awaiting', glow: 'shadow-[0_0_0_3px_rgba(251,191,36,0.15)]' },
  DONE: { ring: 'border-emerald-400/70', pill: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400', label: 'Done', glow: '' },
  FAILED: { ring: 'border-rose-400', pill: 'bg-rose-500/15 text-rose-600 dark:text-rose-400', label: 'Failed', glow: '' },
  CANCELED: { ring: 'border-border', pill: 'bg-muted text-muted-foreground', label: 'Canceled', glow: '' },
  SKIPPED: { ring: 'border-dashed border-border', pill: 'bg-muted text-muted-foreground', label: 'Skipped', glow: '' },
}
const st = computed(() => STATUS[step.value.status] || STATUS.PENDING)
const statusIcon = (s: string) =>
  ({ RUNNING: Loader2, DONE: CheckCircle2, FAILED: XCircle, AWAITING: Clock }[s] || Circle)

const accent = computed(() => {
  const j = step.value.jobs?.[0]
  return j ? modalityHex(j.inference_type?.toLowerCase()) : '#94a3b8'
})
const modality = computed(() => step.value.jobs?.[0]?.inference_type || '')
const model = computed(() => step.value.jobs?.find((j) => j.model_name)?.model_name || '')

const jobs = computed(() => step.value.jobs || [])
const doneCount = computed(() => jobs.value.filter((j) => j.status === 'PROCESSED').length)

interface Thumb { type: 'image' | 'video' | 'audio' | 'text'; url?: string; label?: string }
const thumbOf = (j: AsyncJob): Thumb | null => {
  if (j.image_urls?.length) return { type: 'image', url: j.image_urls[0] }
  if (j.input_image_url) return { type: 'image', url: j.input_image_url }
  if (j.video_url) return { type: 'video', url: j.video_url }
  if (j.output_audio_url) return { type: 'audio', url: j.output_audio_url }
  if (j.inference_type === 'LLM') return { type: 'text', label: j.prompt_preview }
  return null
}
const thumbs = computed(() => jobs.value.map(thumbOf).filter((t): t is Thumb => !!t))

const duration = computed(() => {
  const s = step.value.started_at, f = step.value.finished_at
  if (!s) return ''
  const end = f ? new Date(f).getTime() : Date.now()
  const secs = Math.max(0, Math.round((end - new Date(s).getTime()) / 1000))
  return secs >= 60 ? `${Math.floor(secs / 60)}m ${secs % 60}s` : `${secs}s`
})

const runningHint = computed(() => {
  if (!jobs.value.length) return 'starting…'
  if (jobs.value.some((j) => j.status === 'PROCESSING')) return 'generating…'
  if (jobs.value.every((j) => j.status === 'QUEUED')) return 'waiting for a free provider…'
  return 'queued…'
})

// A short, human description of what this step does (the prompt / op / output).
const detail = computed(() => {
  const sp = (step.value as unknown as { spec?: Record<string, unknown> }).spec
  if (step.value.kind === 'transform') return `${(sp?.op as string) || 'transform'} step`
  const j = jobs.value[0]
  if (j?.prompt_preview) return j.prompt_preview
  if (step.value.kind === 'gate') return 'Waiting for your approval'
  return KIND_LABEL[step.value.kind] || ''
})
</script>

<template>
  <div class="w-[248px] rounded-xl border-2 bg-background text-foreground transition-shadow"
       :class="[st.ring, st.glow]">
    <Handle type="target" :position="Position.Left" class="!h-2 !w-2 !border-2 !bg-muted-foreground" />
    <Handle type="source" :position="Position.Right" class="!h-2 !w-2 !border-2 !bg-muted-foreground" />

    <!-- header -->
    <div class="flex items-center justify-between gap-2 border-b px-3 py-2">
      <div class="flex min-w-0 items-center gap-1.5">
        <span class="size-2.5 shrink-0 rounded-full" :style="{ backgroundColor: accent }" />
        <component :is="KIND_ICON[step.kind] || FileText" class="size-3.5 shrink-0 text-muted-foreground" />
        <span class="truncate text-sm font-semibold" :title="step.title">{{ step.title }}</span>
      </div>
      <span class="flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
            :class="st.pill">
        <component :is="statusIcon(step.status)" class="size-3"
                   :class="step.status === 'RUNNING' ? 'animate-spin' : ''" />
        {{ st.label }}
      </span>
    </div>

    <!-- meta row -->
    <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 px-3 pt-2 text-[10px] text-muted-foreground">
      <span class="rounded bg-muted px-1.5 py-0.5 font-medium uppercase">{{ KIND_LABEL[step.kind] }}</span>
      <span v-if="modality" class="rounded px-1.5 py-0.5 font-medium uppercase text-white"
            :style="{ backgroundColor: accent }">{{ modality }}</span>
      <span v-if="jobs.length > 1">{{ doneCount }}/{{ jobs.length }} done</span>
      <span v-if="duration">· {{ duration }}</span>
    </div>

    <div v-if="model" class="truncate px-3 pt-1 text-[10px] text-muted-foreground" :title="model">
      model: {{ model }}
    </div>

    <!-- body: media / detail -->
    <div class="px-3 py-2">
      <div v-if="thumbs.length" class="flex gap-1.5 overflow-x-auto">
        <div v-for="(th, i) in thumbs.slice(0, 6)" :key="i"
             class="relative h-14 w-14 shrink-0 overflow-hidden rounded-md border bg-muted">
          <img v-if="th.type === 'image' && th.url" :src="th.url" class="h-full w-full object-cover" loading="lazy" alt="" />
          <video v-else-if="th.type === 'video' && th.url" :src="th.url" class="h-full w-full object-cover" muted playsinline preload="metadata" />
          <div v-else-if="th.type === 'audio'" class="flex h-full items-center justify-center"><Music class="size-5 text-fuchsia-500" /></div>
          <div v-else class="flex h-full items-center justify-center"><FileText class="size-4 text-sky-500" /></div>
        </div>
        <span v-if="thumbs.length > 6" class="self-center text-xs text-muted-foreground">+{{ thumbs.length - 6 }}</span>
      </div>

      <div v-else-if="step.kind === 'gate' && step.status === 'AWAITING'" class="flex gap-2">
        <button class="flex-1 rounded-md bg-emerald-500 px-2 py-1.5 text-xs font-medium text-white hover:bg-emerald-600"
                @click="data.onGate?.(step.step_id, 'approve')">Approve</button>
        <button class="flex-1 rounded-md border px-2 py-1.5 text-xs font-medium hover:bg-muted"
                @click="data.onGate?.(step.step_id, 'reject')">Reject</button>
      </div>

      <p v-else-if="step.status === 'FAILED'" class="line-clamp-3 text-xs text-rose-500">
        {{ step.error?.message || 'Failed' }}
      </p>
      <p v-else-if="step.status === 'RUNNING'"
         class="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 class="size-3 animate-spin" /> {{ runningHint }}
      </p>
      <p v-else class="line-clamp-2 text-xs text-muted-foreground">{{ detail }}</p>
    </div>
  </div>
</template>
