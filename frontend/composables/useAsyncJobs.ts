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

export interface TemplateInput {
  name: string
  label: string
  type: 'text' | 'textarea' | 'number' | 'select'
  default?: string | number
  placeholder?: string
  required?: boolean
  min?: number
  max?: number
  options?: { value: string; label: string }[]
}

export interface WorkflowTemplate {
  key: string
  title: string
  description: string
  icon: string
  inputs: TemplateInput[]
  step_count: number
}

// --- saved workflows / authoring (PRD 11) ---

export type StepKind = 'inference' | 'map' | 'transform' | 'collect' | 'gate' | 'prompt'

/** One node in an editable workflow spec. A superset of every kind's fields;
 * the builder only writes the ones relevant to the chosen kind. */
export interface StepSpec {
  id: string
  kind: StepKind
  title?: string
  // inference / map
  type?: 'chat' | 'image' | 'video' | 'music' | 'tts'
  model?: string
  body?: Record<string, unknown>
  over?: string
  response_schema?: Record<string, unknown>
  // prompt (meta-prompting)
  target?: 'image' | 'video' | 'music' | 'tts' | 'text'
  input?: unknown
  instructions?: string
  count?: number
  // transform / collect
  op?: 'passthrough' | 'pluck' | 'split_lines' | 'join' | 'zip'
  field?: string
  sep?: string
  from?: string
  inputs?: unknown
  // common
  depends_on?: string[]
  extract?: string
  [k: string]: unknown
}

export interface WorkflowInputField {
  name: string
  label: string
  type: 'text' | 'textarea' | 'number' | 'select'
  default?: string | number
  placeholder?: string
  required?: boolean
  min?: number
  max?: number
  options?: { value: string; label: string }[]
}

export interface WorkflowSpec {
  name?: string
  steps: StepSpec[]
  layout?: Record<string, { x: number; y: number }>
  inputs?: WorkflowInputField[]
}

export interface SavedWorkflowSummary {
  id: number
  name: string
  description: string
  step_count: number
  run_count: number
  created_on: string
  modified_on: string
}

export interface SavedWorkflow extends SavedWorkflowSummary {
  spec: WorkflowSpec
}

export interface QueueSummary {
  jobs: Record<string, number>
  active: number
  runs: Record<string, number>
  async_enabled: boolean
  last_dispatch: string | null
  worker_stalled: boolean
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

  const send = <T>(method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown) =>
    $fetch<T>(`${base}${path}`, {
      method,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(csrf() ? { 'X-CSRFToken': csrf() } : {}) },
      body: body ?? {},
    })
  const post = <T>(path: string, body?: unknown) => send<T>('POST', path, body)

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
  const listTemplates = () =>
    get<{ data: WorkflowTemplate[] }>('/v1/workflows/templates').then((r) => r.data)
  const startFromTemplate = (template: string, inputs: Record<string, unknown>) =>
    post<WorkflowRun>('/v1/workflows/runs', { template, inputs })
  const resolveGate = (runId: number | string, stepId: string, action: 'approve' | 'reject', edit?: unknown) =>
    post<WorkflowRun>(`/v1/workflows/runs/${runId}/steps/${stepId}/${action}`, edit ? { edit } : {})
  const fetchSuggestions = (templateKey: string, n = 5) =>
    get<{ data: string[] }>(`/v1/workflows/suggestions?template=${encodeURIComponent(templateKey)}&n=${n}`)
      .then((r) => r.data)
      .catch(() => [] as string[])

  const rerunStep = (runId: number | string, stepId: string) =>
    post<WorkflowRun>(`/v1/workflows/runs/${runId}/steps/${stepId}/rerun`)

  // --- saved workflows / authoring (PRD 11) ---
  const listWorkflows = () =>
    get<{ data: SavedWorkflowSummary[] }>('/v1/workflows').then((r) => r.data)
  const getWorkflow = (id: number | string) => get<SavedWorkflow>(`/v1/workflows/${id}`)
  const createWorkflow = (payload: { name: string; description?: string; spec?: WorkflowSpec }) =>
    post<SavedWorkflow>('/v1/workflows', payload)
  const updateWorkflow = (
    id: number | string,
    payload: { name?: string; description?: string; spec?: WorkflowSpec },
  ) => send<SavedWorkflow>('PATCH', `/v1/workflows/${id}`, payload)
  const deleteWorkflow = (id: number | string) => send<unknown>('DELETE', `/v1/workflows/${id}`)
  const runSavedWorkflow = (id: number | string, inputs?: Record<string, unknown>, name?: string) =>
    post<WorkflowRun>(`/v1/workflows/${id}/runs`, { inputs, name })
  const forkTemplate = (key: string, name?: string) =>
    post<SavedWorkflow>(`/v1/workflows/from-template/${encodeURIComponent(key)}`, name ? { name } : {})
  const forkRun = (runId: number | string, name?: string) =>
    post<SavedWorkflow>(`/v1/workflows/from-run/${runId}`, name ? { name } : {})

  // --- queue summary ---
  const queueSummary = () => get<QueueSummary>('/api/inference/queue/summary/')

  return {
    listJobs, getJob, cancelJob, retryJob,
    listRuns, getRun, startRun, resolveGate, listTemplates, startFromTemplate,
    fetchSuggestions, queueSummary, rerunStep,
    listWorkflows, getWorkflow, createWorkflow, updateWorkflow, deleteWorkflow,
    runSavedWorkflow, forkTemplate, forkRun,
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
