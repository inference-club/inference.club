import { ref } from 'vue'

// --- response shapes (mirror apps/inference/staff_views.py) ------------------

export interface AdminActivity {
  generated_at: string
  users: {
    total: number
    new_24h: number
    new_7d: number
    new_30d: number
    active_24h: number
    staff: number
  }
  requests: {
    total: number
    last_24h: number
    last_7d: number
    by_type: { type: string; count: number }[]
  }
  tokens: { total: number; last_24h: number; last_7d: number }
  network: {
    providers_total: number
    providers_active: number
    providers_online: number
    services_active: number
    deployments_active: number
    models_distinct: number
  }
  moderation: { open: number; total: number; resolved: number; dismissed: number }
  daily: { date: string; requests: number; tokens: number }[]
  recent_signups: {
    owner: string
    github_login: string | null
    joined: string
    is_staff: boolean
  }[]
}

export type ReportStatus = 'OPEN' | 'REVIEWING' | 'RESOLVED' | 'DISMISSED'

export interface ContentReport {
  id: number
  request: {
    id: number
    inference_type: string
    model_name: string
    visibility: string
    status: string
    owner: string
    github_login: string | null
    prompt_preview: string
    created_on: string
  }
  reporter: string | null
  reason: string
  reason_display: string
  details: string
  status: ReportStatus
  status_display: string
  resolution_note: string
  resolved_by: string | null
  resolved_at: string | null
  created_on: string
}

interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// Staff-only admin API client (activity dashboard + moderation queue). Mirrors
// useContentSharing's cookie-session + CSRF conventions, but rooted at
// /api/admin. Every endpoint is gated server-side by IsStaff.
export function useAdmin() {
  const config = useRuntimeConfig()
  const loading = ref(false)
  const error = ref<string | null>(null)
  const base = `${config.public.apiBase}/api/admin`

  const getCsrfToken = (): string | null => {
    const name = 'csrftoken'
    if (typeof document === 'undefined' || !document.cookie) return null
    for (const raw of document.cookie.split(';')) {
      const cookie = raw.trim()
      if (cookie.startsWith(name + '=')) {
        return decodeURIComponent(cookie.substring(name.length + 1))
      }
    }
    return null
  }

  const api = async <T>(path: string, options: RequestInit = {}): Promise<T> => {
    const method = (options.method || 'GET').toUpperCase()
    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers as Record<string, string> | undefined),
    }
    if (method !== 'GET') {
      const csrf = getCsrfToken()
      if (csrf) headers['X-CSRFToken'] = csrf
    }
    const resp = await fetch(`${base}${path}`, {
      credentials: 'include',
      ...options,
      method,
      headers,
    })
    if (!resp.ok) throw new Error(`Request failed (${resp.status})`)
    if (resp.status === 204) return undefined as T
    return (await resp.json()) as T
  }

  const withState = async <T>(fn: () => Promise<T>): Promise<T> => {
    loading.value = true
    error.value = null
    try {
      return await fn()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'An error occurred'
      throw e
    } finally {
      loading.value = false
    }
  }

  const getActivity = () => withState(() => api<AdminActivity>('/activity/'))

  // status: 'open' (default, OPEN+REVIEWING), 'all', or a specific status.
  const listReports = (status = 'open') =>
    withState(() =>
      api<Paginated<ContentReport>>(
        `/reports/?status=${encodeURIComponent(status)}`,
      ),
    )

  const updateReport = (
    id: number,
    payload: { status?: ReportStatus; resolution_note?: string },
  ) =>
    withState(() =>
      api<ContentReport>(`/reports/${id}/`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    )

  const moderateRequest = (
    requestId: number,
    action: 'hide' | 'delete',
    resolutionNote?: string,
  ) =>
    withState(() =>
      api<{ action: string; visibility?: string; deleted?: boolean }>(
        `/requests/${requestId}/moderate/`,
        {
          method: 'POST',
          body: JSON.stringify({ action, resolution_note: resolutionNote }),
        },
      ),
    )

  return {
    loading,
    error,
    getActivity,
    listReports,
    updateReport,
    moderateRequest,
  }
}
