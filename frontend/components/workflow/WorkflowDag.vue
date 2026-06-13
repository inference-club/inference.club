<script setup lang="ts">
/**
 * Real-time DAG view of a workflow run. Steps are laid out left→right by
 * dependency depth; edges are drawn as an SVG layer behind absolutely-
 * positioned HTML node cards (so each node can show live media thumbnails and
 * gate buttons). Re-renders whenever the polled `run` updates.
 */
import { computed } from 'vue'
import { CheckCircle2, Circle, Clock, Loader2, XCircle,
  Music, FileText, GitFork, Hand, Wrench, Layers } from 'lucide-vue-next'
import { modalityHex } from '@/composables/useClusterState'
import type { WorkflowRun, WorkflowStep, AsyncJob } from '@/composables/useAsyncJobs'

const props = defineProps<{ run: WorkflowRun }>()
const emit = defineEmits<{ (e: 'gate', payload: { stepId: string; action: 'approve' | 'reject' }): void }>()

const NODE_W = 200
const NODE_H = 128
const GAP_X = 72
const GAP_Y = 28

// Map each step to a dependency depth (longest path from a root), then to a
// pixel position: depth → column, order-within-column → row.
const layout = computed(() => {
  const steps = props.run.steps
  const byId: Record<string, WorkflowStep> = {}
  steps.forEach((s) => { byId[s.step_id] = s })

  const depthCache: Record<string, number> = {}
  const depthOf = (id: string, seen = new Set<string>()): number => {
    if (depthCache[id] != null) return depthCache[id]
    if (seen.has(id)) return 0
    seen.add(id)
    const deps = (byId[id]?.depends_on || []).filter((d) => byId[d])
    const d = deps.length ? Math.max(...deps.map((dep) => depthOf(dep, seen))) + 1 : 0
    depthCache[id] = d
    return d
  }

  const columns: Record<number, WorkflowStep[]> = {}
  for (const s of steps) {
    const d = depthOf(s.step_id)
    ;(columns[d] ||= []).push(s)
  }
  const pos: Record<string, { x: number; y: number }> = {}
  let maxRows = 0
  Object.keys(columns).map(Number).sort((a, b) => a - b).forEach((d) => {
    const col = columns[d].sort((a, b) => a.position - b.position)
    maxRows = Math.max(maxRows, col.length)
    col.forEach((s, row) => {
      pos[s.step_id] = { x: d * (NODE_W + GAP_X), y: row * (NODE_H + GAP_Y) }
    })
  })
  const depthCount = Object.keys(columns).length
  return {
    pos,
    width: Math.max(1, depthCount) * (NODE_W + GAP_X) - GAP_X,
    height: Math.max(1, maxRows) * (NODE_H + GAP_Y) - GAP_Y,
  }
})

const edges = computed(() =>
  props.run.edges
    .filter((e) => layout.value.pos[e.from] && layout.value.pos[e.to])
    .map((e) => {
      const a = layout.value.pos[e.from]
      const b = layout.value.pos[e.to]
      const x1 = a.x + NODE_W
      const y1 = a.y + NODE_H / 2
      const x2 = b.x
      const y2 = b.y + NODE_H / 2
      const mx = (x1 + x2) / 2
      return { d: `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`, to: e.to }
    }),
)

const STATUS_STYLE: Record<string, { ring: string; pill: string; label: string }> = {
  PENDING: { ring: 'border-border', pill: 'bg-muted text-muted-foreground', label: 'Pending' },
  RUNNING: { ring: 'border-sky-400 shadow-sky-500/20 shadow-lg', pill: 'bg-sky-500/15 text-sky-600 dark:text-sky-400', label: 'Running' },
  AWAITING: { ring: 'border-amber-400 shadow-amber-500/20 shadow-lg', pill: 'bg-amber-500/15 text-amber-600 dark:text-amber-400', label: 'Awaiting' },
  DONE: { ring: 'border-emerald-400/70', pill: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400', label: 'Done' },
  FAILED: { ring: 'border-rose-400', pill: 'bg-rose-500/15 text-rose-600 dark:text-rose-400', label: 'Failed' },
  CANCELED: { ring: 'border-border', pill: 'bg-muted text-muted-foreground', label: 'Canceled' },
  SKIPPED: { ring: 'border-dashed border-border', pill: 'bg-muted text-muted-foreground', label: 'Skipped' },
}
const styleFor = (s: string) => STATUS_STYLE[s] || STATUS_STYLE.PENDING

const KIND_ICON: Record<string, unknown> = {
  inference: FileText, map: GitFork, transform: Wrench, collect: Layers, gate: Hand,
}
const statusIcon = (s: string) =>
  ({ RUNNING: Loader2, DONE: CheckCircle2, FAILED: XCircle, AWAITING: Clock }[s] || Circle)

// Modality accent for a node (matches the cluster palette). Inference/map
// nodes take their colour from the job they spawned; non-inference nodes
// (transform/collect/gate) fall back to a neutral slate.
const accent = (step: WorkflowStep): string => {
  const job = step.jobs?.[0]
  if (job) return modalityHex(job.inference_type?.toLowerCase())
  return '#94a3b8' // slate-400
}

interface Thumb { type: 'image' | 'video' | 'audio' | 'text'; url?: string; label?: string }
const thumbFor = (job: AsyncJob): Thumb | null => {
  if (job.image_urls && job.image_urls.length) return { type: 'image', url: job.image_urls[0] }
  if (job.input_image_url) return { type: 'image', url: job.input_image_url }
  if (job.video_url) return { type: 'video', url: job.video_url }
  if (job.output_audio_url) return { type: 'audio', url: job.output_audio_url }
  if (job.inference_type === 'LLM') return { type: 'text', label: job.prompt_preview }
  return null
}
const stepThumbs = (step: WorkflowStep): Thumb[] =>
  (step.jobs || []).map(thumbFor).filter((t): t is Thumb => !!t).slice(0, 4)
</script>

<template>
  <div class="relative overflow-auto rounded-lg border bg-muted/20 p-6"
       :style="{ minHeight: '320px' }">
    <div class="relative" :style="{ width: `${layout.width}px`, height: `${layout.height}px` }">
      <!-- edges -->
      <svg class="pointer-events-none absolute inset-0 overflow-visible"
           :width="layout.width" :height="layout.height">
        <defs>
          <marker id="dag-arrow" viewBox="0 0 10 10" refX="9" refY="5"
                  markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" class="fill-muted-foreground/50" />
          </marker>
        </defs>
        <path v-for="(e, i) in edges" :key="i" :d="e.d" fill="none"
              class="stroke-muted-foreground/40" stroke-width="2"
              marker-end="url(#dag-arrow)" />
      </svg>

      <!-- nodes -->
      <div
        v-for="step in run.steps" :key="step.step_id"
        class="absolute rounded-xl border-2 bg-background p-3 transition-all"
        :class="styleFor(step.status).ring"
        :style="{
          left: `${layout.pos[step.step_id]?.x ?? 0}px`,
          top: `${layout.pos[step.step_id]?.y ?? 0}px`,
          width: `${NODE_W}px`, height: `${NODE_H}px`,
        }"
      >
        <div class="flex items-center justify-between gap-2">
          <div class="flex min-w-0 items-center gap-1.5">
            <span class="inline-block size-2.5 shrink-0 rounded-full"
                  :style="{ backgroundColor: accent(step) }" />
            <component :is="KIND_ICON[step.kind] || FileText" class="size-3.5 shrink-0 text-muted-foreground" />
            <span class="truncate text-sm font-semibold" :title="step.title">{{ step.title }}</span>
          </div>
          <span class="flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
                :class="styleFor(step.status).pill">
            <component :is="statusIcon(step.status)" class="size-3"
                       :class="step.status === 'RUNNING' ? 'animate-spin' : ''" />
            {{ styleFor(step.status).label }}
          </span>
        </div>

        <!-- media / output preview -->
        <div class="mt-2 flex h-[68px] items-center gap-1.5 overflow-hidden">
          <template v-if="stepThumbs(step).length">
            <div v-for="(th, i) in stepThumbs(step)" :key="i"
                 class="relative h-[60px] flex-1 overflow-hidden rounded-md border bg-muted">
              <img v-if="th.type === 'image' && th.url" :src="th.url"
                   class="h-full w-full object-cover" loading="lazy" alt="" />
              <video v-else-if="th.type === 'video' && th.url" :src="th.url"
                     class="h-full w-full object-cover" muted playsinline preload="metadata" />
              <div v-else-if="th.type === 'audio'" class="flex h-full items-center justify-center">
                <Music class="size-5 text-fuchsia-500" />
              </div>
              <div v-else class="flex h-full items-center justify-center p-1">
                <FileText class="size-4 shrink-0 text-sky-500" />
              </div>
            </div>
            <span v-if="step.kind === 'map' && step.jobs.length > 4"
                  class="shrink-0 text-xs text-muted-foreground">+{{ step.jobs.length - 4 }}</span>
          </template>

          <!-- gate controls -->
          <div v-else-if="step.kind === 'gate' && step.status === 'AWAITING'"
               class="flex w-full items-center justify-center gap-2">
            <button class="rounded-md bg-emerald-500 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-600"
                    @click="emit('gate', { stepId: step.step_id, action: 'approve' })">Approve</button>
            <button class="rounded-md border px-2.5 py-1 text-xs font-medium hover:bg-muted"
                    @click="emit('gate', { stepId: step.step_id, action: 'reject' })">Reject</button>
          </div>

          <!-- error / empty -->
          <p v-else-if="step.status === 'FAILED'" class="line-clamp-3 text-xs text-rose-500">
            {{ step.error?.message || 'Failed' }}
          </p>
          <p v-else class="text-xs capitalize text-muted-foreground">{{ step.kind }}</p>
        </div>

        <div v-if="step.kind === 'map' && step.jobs.length"
             class="absolute bottom-1.5 right-2 text-[10px] text-muted-foreground">
          {{ step.jobs.filter((j) => j.status === 'PROCESSED').length }}/{{ step.jobs.length }}
        </div>
      </div>
    </div>
  </div>
</template>
