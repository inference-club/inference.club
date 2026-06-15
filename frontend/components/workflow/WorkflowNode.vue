<script setup lang="ts">
/**
 * A rich custom node for the Vue Flow workflow graph. Shows everything about a
 * step at a glance: modality, kind, status, the model used, live media
 * thumbnails, per-job progress, timing, and gate controls / errors.
 */
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { CheckCircle2, Circle, Clock, Loader2, XCircle, Music, FileText,
  GitFork, Hand, Wrench, Layers, Sparkles, RotateCcw, Download, X,
  Maximize2, Brain } from 'lucide-vue-next'
import { modalityHex } from '@/composables/useClusterState'
import { roleClasses } from '@/utils/inference'
import type { WorkflowStep, AsyncJob } from '@/composables/useAsyncJobs'
import type { InferenceRequest } from '@/types'

const props = defineProps<{
  data: {
    step: WorkflowStep
    onGate?: (stepId: string, action: 'approve' | 'reject') => void
    onRerun?: (stepId: string) => void
  }
}>()

const step = computed(() => props.data.step)

const KIND_ICON: Record<string, unknown> = {
  prompt: Sparkles, inference: FileText, map: GitFork, transform: Wrench, collect: Layers, gate: Hand,
}
const KIND_LABEL: Record<string, string> = {
  prompt: 'Prompt', inference: 'Inference', map: 'Fan-out', transform: 'Transform', collect: 'Collect', gate: 'Human gate',
}

// A finished generation step can be re-rolled (and its downstream re-flowed).
const canRerun = computed(() =>
  ['inference', 'map', 'prompt'].includes(step.value.kind) &&
  ['DONE', 'FAILED'].includes(step.value.status))
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

interface Thumb { type: 'image' | 'video' | 'audio'; url?: string }
const thumbOf = (j: AsyncJob): Thumb | null => {
  // Video first: an image-to-video job carries its conditioning frame as
  // input_image_url too, but the result we want to show is the video.
  if (j.video_url) return { type: 'video', url: j.video_url }
  if (j.image_urls?.length) return { type: 'image', url: j.image_urls[0] }
  if (j.input_image_url) return { type: 'image', url: j.input_image_url }
  if (j.output_audio_url) return { type: 'audio', url: j.output_audio_url }
  return null
}
const thumbs = computed(() => jobs.value.map(thumbOf).filter((t): t is Thumb => !!t))
// Videos play inline in the node (with controls) so a result is watchable right
// here — no need to open the inference/videos tab. Images/audio stay as small
// click-to-lightbox thumbnails.
const videoThumbs = computed(() => thumbs.value.filter((t) => t.type === 'video' && t.url))
const otherThumbs = computed(() => thumbs.value.filter((t) => t.type !== 'video'))

// LLM jobs carry a prompt + a text response; we let the user expand them to
// read the full conversation (the node itself only has the truncated preview).
const llmJobs = computed(() => jobs.value.filter((j) => j.inference_type === 'LLM'))
const hasText = computed(() => llmJobs.value.length > 0)

// Click a thumbnail to open the full media (image/video/audio) in a lightbox
// with playback controls + a download link — teleported to <body> so it
// escapes the Vue Flow transformed canvas.
const lightbox = ref<Thumb | null>(null)
const canOpen = (th: Thumb) => !!th.url
const openThumb = (th: Thumb) => { if (canOpen(th)) lightbox.value = th }
const closeLightbox = () => { lightbox.value = null }

// Expand the full prompt & response. A job's id is its InferenceRequest id, so
// we lazily fetch the detail serializer (messages + response_text + reasoning)
// the first time the panel is opened, then cache it per job. Teleported to
// <body> like the media lightbox so it escapes the transformed canvas.
const { getInferenceRequest } = useInferenceRequest()
interface JobDetail { loading: boolean; error: string | null; req: InferenceRequest | null }
const detailOpen = ref(false)
const details = ref<Record<string, JobDetail>>({})
const loadDetail = async (j: AsyncJob) => {
  const key = String(j.id)
  if (details.value[key]?.req) return
  details.value = { ...details.value, [key]: { loading: true, error: null, req: null } }
  try {
    const req = await getInferenceRequest(key)
    details.value = { ...details.value, [key]: { loading: false, error: null, req } }
  } catch (e: unknown) {
    details.value = {
      ...details.value,
      [key]: { loading: false, error: (e as Error)?.message || 'Failed to load', req: null },
    }
  }
}
const openDetail = () => {
  detailOpen.value = true
  llmJobs.value.forEach((j) => void loadDetail(j))
}
const closeDetail = () => { detailOpen.value = false }

const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { closeLightbox(); closeDetail() } }
watch([lightbox, detailOpen], ([lb, dt]) => {
  if (typeof document === 'undefined') return
  if (lb || dt) document.addEventListener('keydown', onKey)
  else document.removeEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  if (typeof document !== 'undefined') document.removeEventListener('keydown', onKey)
})

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
  <div
class="w-[248px] rounded-xl border-2 bg-background text-foreground transition-shadow"
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
      <div class="flex shrink-0 items-center gap-1">
        <button
v-if="canRerun && data.onRerun"
                class="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-sky-500"
                title="Re-run this step" @click="data.onRerun(step.step_id)">
          <RotateCcw class="size-3.5" />
        </button>
        <span class="flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium" :class="st.pill">
          <component
:is="statusIcon(step.status)" class="size-3"
                     :class="step.status === 'RUNNING' ? 'animate-spin' : ''" />
          {{ st.label }}
        </span>
      </div>
    </div>

    <!-- meta row -->
    <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 px-3 pt-2 text-[10px] text-muted-foreground">
      <span class="rounded bg-muted px-1.5 py-0.5 font-medium uppercase">{{ KIND_LABEL[step.kind] }}</span>
      <span
v-if="modality" class="rounded px-1.5 py-0.5 font-medium uppercase text-white"
            :style="{ backgroundColor: accent }">{{ modality }}</span>
      <span v-if="jobs.length > 1">{{ doneCount }}/{{ jobs.length }} done</span>
      <span v-if="duration">· {{ duration }}</span>
    </div>

    <div v-if="model" class="truncate px-3 pt-1 text-[10px] text-muted-foreground" :title="model">
      model: {{ model }}
    </div>

    <!-- body: media / detail -->
    <div class="space-y-2 px-3 py-2">
      <template v-if="thumbs.length">
        <!-- Video results play inline (controls) so they're watchable right in
             the node; click to enlarge in the lightbox. -->
        <video
v-for="(v, i) in videoThumbs.slice(0, 3)" :key="'v' + i"
               :src="v.url" controls playsinline preload="metadata"
               class="nodrag nowheel w-full rounded-md border bg-black"
               @mousedown.stop @dblclick.stop="openThumb(v)" />
        <span v-if="videoThumbs.length > 3" class="text-xs text-muted-foreground">
          +{{ videoThumbs.length - 3 }} more clips
        </span>

        <div v-if="otherThumbs.length" class="flex gap-1.5 overflow-x-auto nowheel">
          <button
v-for="(th, i) in otherThumbs.slice(0, 6)" :key="i" type="button"
                  class="nodrag relative h-14 w-14 shrink-0 overflow-hidden rounded-md border bg-muted"
                  :class="canOpen(th) ? 'cursor-pointer hover:ring-2 hover:ring-sky-400' : 'cursor-default'"
                  :title="canOpen(th) ? 'Click to view' : undefined"
                  @click.stop="openThumb(th)" @mousedown.stop>
            <img v-if="th.type === 'image' && th.url" :src="th.url" class="h-full w-full object-cover" loading="lazy" alt="" >
            <div v-else-if="th.type === 'audio'" class="flex h-full items-center justify-center"><Music class="size-5 text-fuchsia-500" /></div>
          </button>
          <span v-if="otherThumbs.length > 6" class="self-center text-xs text-muted-foreground">+{{ otherThumbs.length - 6 }}</span>
        </div>
      </template>

      <div v-else-if="step.kind === 'gate' && step.status === 'AWAITING'" class="flex gap-2">
        <button
class="flex-1 rounded-md bg-emerald-500 px-2 py-1.5 text-xs font-medium text-white hover:bg-emerald-600"
                @click="data.onGate?.(step.step_id, 'approve')">Approve</button>
        <button
class="flex-1 rounded-md border px-2 py-1.5 text-xs font-medium hover:bg-muted"
                @click="data.onGate?.(step.step_id, 'reject')">Reject</button>
      </div>

      <p v-else-if="step.status === 'FAILED'" class="line-clamp-3 text-xs text-rose-500">
        {{ step.error?.message || 'Failed' }}
      </p>
      <p
v-else-if="step.status === 'RUNNING'"
         class="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 class="size-3 animate-spin" /> {{ runningHint }}
      </p>
      <p v-else class="line-clamp-2 text-xs text-muted-foreground">{{ detail }}</p>

      <!-- Expand the full prompt + response of this step's LLM job(s). -->
      <button
        v-if="hasText"
        type="button"
        class="nodrag flex w-full items-center justify-center gap-1 rounded-md border border-dashed px-2 py-1 text-[11px] font-medium text-muted-foreground hover:bg-muted hover:text-sky-500"
        title="View the full prompt & response"
        @click.stop="openDetail" @mousedown.stop>
        <Maximize2 class="size-3" /> Prompt &amp; response
      </button>
    </div>
  </div>

  <!-- Full-media lightbox: video/audio play with controls; everything is
       downloadable. Teleported to body so it sits above the canvas. -->
  <Teleport to="body">
    <div
v-if="lightbox"
         class="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4"
         @click.self="closeLightbox" @mousedown.stop>
      <div class="relative max-h-[90vh] max-w-[90vw]">
        <img
v-if="lightbox.type === 'image'" :src="lightbox.url"
             class="max-h-[90vh] max-w-[90vw] rounded-lg object-contain" alt="" >
        <video
v-else-if="lightbox.type === 'video'" :src="lightbox.url"
               class="max-h-[85vh] max-w-[90vw] rounded-lg bg-black" controls autoplay playsinline />
        <audio v-else-if="lightbox.type === 'audio'" :src="lightbox.url" class="w-[80vw] max-w-md" controls autoplay />
        <div class="absolute -right-3 -top-3 flex gap-2">
          <a
:href="lightbox.url" target="_blank" rel="noopener" download
             class="rounded-full bg-white/90 p-2 text-black shadow hover:bg-white"
             title="Open / download" @click.stop>
            <Download class="size-4" />
          </a>
          <button
type="button" title="Close (Esc)"
                  class="rounded-full bg-white/90 p-2 text-black shadow hover:bg-white"
                  @click="closeLightbox">
            <X class="size-4" />
          </button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- Full prompt & response panel for the step's LLM job(s). Lazily fetched
       detail (messages + response_text + reasoning), teleported to body. -->
  <Teleport to="body">
    <div
      v-if="detailOpen"
      class="fixed inset-0 z-[100] flex items-start justify-center overflow-y-auto bg-black/70 p-4 sm:p-8"
      @click.self="closeDetail" @mousedown.stop>
      <div class="my-auto w-full max-w-2xl rounded-xl border bg-background text-foreground shadow-xl">
        <div class="flex items-center justify-between gap-2 border-b px-4 py-3">
          <div class="flex min-w-0 items-center gap-2">
            <component :is="KIND_ICON[step.kind] || FileText" class="size-4 shrink-0 text-muted-foreground" />
            <span class="truncate text-sm font-semibold" :title="step.title">{{ step.title }}</span>
            <span v-if="model" class="truncate text-xs text-muted-foreground">· {{ model }}</span>
          </div>
          <button
            type="button" title="Close (Esc)"
            class="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            @click="closeDetail">
            <X class="size-4" />
          </button>
        </div>

        <div class="max-h-[75vh] space-y-5 overflow-y-auto px-4 py-4">
          <div v-for="(j, idx) in llmJobs" :key="String(j.id)" class="space-y-3">
            <div v-if="llmJobs.length > 1" class="text-xs font-semibold uppercase text-muted-foreground">
              Output {{ idx + 1 }}
            </div>

            <p v-if="details[String(j.id)]?.loading" class="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 class="size-4 animate-spin" /> Loading…
            </p>
            <p v-else-if="details[String(j.id)]?.error" class="text-sm text-rose-500">
              {{ details[String(j.id)]?.error }}
            </p>

            <template v-else-if="details[String(j.id)]?.req">
              <!-- Prompt -->
              <section class="space-y-2">
                <h4 class="text-sm font-semibold">Prompt</h4>
                <div
                  v-for="(m, i) in details[String(j.id)]!.req!.messages || []" :key="i"
                  class="rounded-lg border p-3">
                  <span
                    class="mb-2 inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium capitalize"
                    :class="roleClasses(m.role)">{{ m.role || 'message' }}</span>
                  <MarkdownRenderer :content="m.content" />
                </div>
                <p
                  v-if="!(details[String(j.id)]!.req!.messages || []).length"
                  class="whitespace-pre-wrap rounded-lg border p-3 text-sm text-muted-foreground">
                  {{ j.prompt_preview || 'No prompt recorded.' }}
                </p>
              </section>

              <!-- Reasoning -->
              <section v-if="details[String(j.id)]!.req!.reasoning" class="space-y-2">
                <h4 class="flex items-center gap-1.5 text-sm font-semibold">
                  <Brain class="size-4 text-amber-500" /> Reasoning
                </h4>
                <div class="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-sm text-muted-foreground">
                  <MarkdownRenderer :content="details[String(j.id)]!.req!.reasoning" />
                </div>
              </section>

              <!-- Response -->
              <section class="space-y-2">
                <h4 class="text-sm font-semibold">Response</h4>
                <div
                  v-if="details[String(j.id)]!.req!.response_text"
                  class="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
                  <MarkdownRenderer :content="details[String(j.id)]!.req!.response_text" />
                </div>
                <p v-else class="rounded-lg border p-3 text-sm text-muted-foreground">No response content stored.</p>
              </section>
            </template>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
