/**
 * Client for the async job / batch / workflow API (PRD 10).
 *
 * Jobs are queued InferenceRequests; workflow runs are DAGs of them. The DAG
 * viewer polls a run while it's live so media appears as each step completes.
 */
import { ref, onBeforeUnmount } from 'vue'

export type JobStatus =
  | 'QUEUED' | 'PROCESSING' | 'PROCESSED' | 'FAILED' | 'CANCELED' | 'REQUESTED'

export type WorkflowStatus =
  | 'PENDING' | 'RUNNING' | 'AWAITING' | 'DONE' | 'FAILED' | 'CANCELED' | 'SKIPPED'

export interface AsyncJob {
  id: string | number
  inference_type: string
  status: JobStatus
  model_name?: string
  attempts?: number
  max_attempts?: number
  priority?: number
  queued_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  error?: { message?: string; kind?: string } | null
  // media (from the shared list serializer)
  image_urls?: string[]
  output_audio_url?: string | null
  video_url?: string | null
  input_image_url?: string | null
  prompt_preview?: string
  created_on?: string
}

export interface WorkflowStep {
  id: number
  step_id: string
  kind: 'inference' | 'map' | 'transform' | 'collect' | 'gate'
  title: string
  depends_on: string[]
  status: WorkflowStatus
  output?: unknown
  error?: { message?: string } | null
  position: number
  jobs: AsyncJob[]
}

export interface WorkflowEdge { from: string; to: string }

export interface WorkflowRun {
  id: number
  name: string
  status: WorkflowStatus
  inputs?: Record<string, unknown>
  error?: { message?: string } | null
  created_on: string
  started_at?: string | null
  finished_at?: string | null
  steps: WorkflowStep[]
  edges: WorkflowEdge[]
}

export interface WorkflowRunSummary {
  id: number
  name: string
  status: WorkflowStatus
  created_on: string
  started_at?: string | null
  finished_at?: string | null
  step_count: number
}

const TERMINAL_RUN: WorkflowStatus[] = ['DONE', 'FAILED', 'CANCELED']

function csrf(): string {
  if (!import.meta.client) return ''
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

export function useAsyncJobs() {
  const config = useRuntimeConfig()
  const base = config.public.apiBase as string

  const get = <T>(path: string) =>
    $fetch<T>(`${base}${path}`, { credentials: 'include', headers: { Accept: 'application/json' } })

  const post = <T>(path: string, body?: unknown) =>
    $fetch<T>(`${base}${path}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(csrf() ? { 'X-CSRFToken': csrf() } : {}) },
      body: body ?? {},
    })

  // --- jobs ---
  const listJobs = (opts: { active?: boolean; status?: string; limit?: number } = {}) => {
    const q = new URLSearchParams()
    if (opts.active) q.set('active', '1')
    if (opts.status) q.set('status', opts.status)
    if (opts.limit) q.set('limit', String(opts.limit))
    const qs = q.toString()
    return get<{ data: AsyncJob[] }>(`/v1/jobs${qs ? `?${qs}` : ''}`).then((r) => r.data)
  }
  const getJob = (id: string | number) => get<AsyncJob>(`/v1/jobs/${id}`)
  const cancelJob = (id: string | number) => post(`/v1/jobs/${id}/cancel`)
  const retryJob = (id: string | number) => post(`/v1/jobs/${id}/retry`)

  // --- workflows ---
  const listRuns = () =>
    get<{ data: WorkflowRunSummary[] }>('/v1/workflows/runs').then((r) => r.data)
  const getRun = (id: number | string) => get<WorkflowRun>(`/v1/workflows/runs/${id}`)
  const startRun = (spec: unknown, inputs?: Record<string, unknown>, name?: string) =>
    post<WorkflowRun>('/v1/workflows/runs', { spec, inputs, name })
  const resolveGate = (runId: number | string, stepId: string, action: 'approve' | 'reject', edit?: unknown) =>
    post<WorkflowRun>(`/v1/workflows/runs/${runId}/steps/${stepId}/${action}`, edit ? { edit } : {})

  // --- queue summary ---
  const queueSummary = () =>
    get<{ jobs: Record<string, number>; active: number; runs: Record<string, number> }>(
      '/api/inference/queue/summary/',
    )

  return {
    listJobs, getJob, cancelJob, retryJob,
    listRuns, getRun, startRun, resolveGate,
    queueSummary,
  }
}

/**
 * Poll a single workflow run until it reaches a terminal state, exposing the
 * live run so the DAG viewer re-renders as steps complete. Stops itself on
 * completion and on unmount.
 */
export function useWorkflowRunPoller(runId: number | string, intervalMs = 2500) {
  const { getRun } = useAsyncJobs()
  const run = ref<WorkflowRun | null>(null)
  const error = ref<string | null>(null)
  const loading = ref(true)
  let timer: ReturnType<typeof setInterval> | null = null

  const tick = async () => {
    try {
      run.value = await getRun(runId)
      error.value = null
      if (run.value && TERMINAL_RUN.includes(run.value.status)) stop()
    } catch (e: unknown) {
      error.value = (e as Error)?.message || 'Failed to load run'
    } finally {
      loading.value = false
    }
  }

  const start = () => {
    if (!import.meta.client || timer) return
    void tick()
    timer = setInterval(tick, intervalMs)
  }
  const stop = () => {
    if (timer) { clearInterval(timer); timer = null }
  }
  // Resume polling after a gate action (run may go RUNNING again).
  const refresh = () => { void tick(); if (!timer) start() }

  onBeforeUnmount(stop)
  return { run, error, loading, start, stop, refresh }
}
