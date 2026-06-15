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
    guests_total: number
    guests_active: number
    guests_new_24h: number
    guests_new_7d: number
    passcode_accounts: number
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
    account_type: 'GITHUB' | 'GUEST' | 'PASSCODE'
  }[]
}

// --- roadmap (PRD 12) -------------------------------------------------------

export type RoadmapStatus = 'planned' | 'in_progress' | 'blocked' | 'done'

export interface RoadmapTask {
  id: string
  title: string
  status: RoadmapStatus
  note: string
}

export interface RoadmapPhase {
  id: string
  phase: string
  title: string
  track: string
  status: RoadmapStatus
  gate: string
  progress: { total: number; done: number; in_progress: number }
  tasks: RoadmapTask[]
}

export interface Roadmap {
  meta: {
    title: string
    prd: string
    updated: string
    summary: string
    tracks: Record<string, string>
  }
  totals: {
    tasks: number
    done: number
    in_progress: number
    phases: number
    phases_done: number
  }
  phases: RoadmapPhase[]
  progress_log?: { date: string; note: string }[]
}

// --- anonymous access management (PRD 08) -----------------------------------

export interface AccessCode {
  id: number
  code: string
  label: string
  handle: string
  user_id: number
  user_is_active: boolean
  is_active: boolean
  expires_at: string | null
  created_at: string
  last_used_at: string | null
  use_count: number
  request_count: number
}

export interface GuestAccount {
  id: number
  handle: string
  is_active: boolean
  date_joined: string
  last_login: string | null
  request_count: number
}

export interface AnonAccessPolicy {
  guest_signin_enabled: boolean
  passcode_signin_enabled: boolean
  max_active_guests: number
  guest_creation_rate: string
  passcode_attempt_rate: string
  anon_inference_rate: string
  anon_models_rate: string
  guest_message: string
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

  const getRoadmap = () => withState(() => api<Roadmap>('/roadmap/'))

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

  // --- anonymous access management (PRD 08) --------------------------------

  const getAccessPolicy = () => withState(() => api<AnonAccessPolicy>('/access-policy/'))

  const updateAccessPolicy = (payload: Partial<AnonAccessPolicy>) =>
    withState(() =>
      api<AnonAccessPolicy>('/access-policy/', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    )

  const listAccessCodes = () =>
    withState(() => api<{ codes: AccessCode[] }>('/access-codes/'))

  const createAccessCode = (payload: {
    code?: string
    label?: string
    expires_at?: string | null
  }) =>
    withState(() =>
      api<AccessCode>('/access-codes/', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    )

  const updateAccessCode = (
    id: number,
    payload: { label?: string; expires_at?: string | null; is_active?: boolean },
  ) =>
    withState(() =>
      api<AccessCode>(`/access-codes/${id}/`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    )

  const listGuests = () => withState(() => api<{ guests: GuestAccount[] }>('/guests/'))

  const revokeGuest = (id: number) =>
    withState(() => api<GuestAccount>(`/guests/${id}/revoke/`, { method: 'POST' }))

  const purgeGuest = (id: number) =>
    withState(() => api<{ detail: string }>(`/guests/${id}/purge/`, { method: 'POST' }))

  return {
    loading,
    error,
    getActivity,
    getRoadmap,
    listReports,
    updateReport,
    moderateRequest,
    getAccessPolicy,
    updateAccessPolicy,
    listAccessCodes,
    createAccessCode,
    updateAccessCode,
    listGuests,
    revokeGuest,
    purgeGuest,
  }
}
