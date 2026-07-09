// Cluster control center (PRD 21) — client for the owner-only board that lets
// you see your GPU boxes (utilization + free VRAM), what's running on each, and
// (V1) park/unpark inference services. Talks to the session-authenticated
// GET /api/inference/control/ (mirrors ControlCenterView in views.py).

export type ServiceState = 'running' | 'starting' | 'stopping' | 'parked' | 'failed'

export interface ControlService {
  name: string
  type: string // llm | stt | tts | image | mesh | music | video | …
  engine: string
  logo_url: string | null
  state: ServiceState
  live_vram_gb: number | null
  expected_vram_gb: number | null
  home_box: string
  box: string
  candidate_boxes: string[]
  // Only present on `startable` entries: does its expected VRAM fit the box's
  // free VRAM? null = unknown (no expected_vram_gb yet, or no live free VRAM).
  fits?: boolean | null
}

export interface ControlBoxGpu {
  model: string
  count: number
  vram_total_gb: number | null
  vram_used_gb: number | null
  vram_free_gb: number | null
  utilization_pct: number | null
  unified: boolean
}

export interface ControlBox {
  box: string
  hostname: string
  arch: string
  online: boolean
  schedulable: boolean
  unschedulable_reason: string | null
  gpu: ControlBoxGpu
  services: ControlService[] // running / starting on this box
  startable: ControlService[] // parked services that could be started here
}

export interface ControlProviderBoard {
  provider: {
    id: number
    name: string
    online: boolean
    cluster_control_enabled: boolean
    has_live_state: boolean
  }
  boxes: ControlBox[]
  parked_elsewhere: ControlService[]
}

export interface ControlBoardPayload {
  generated_at: string
  providers: ControlProviderBoard[]
}

export function useControlCenter() {
  const config = useRuntimeConfig()
  const base = `${config.public.apiBase}/api/inference/control`

  const loadBoard = async (): Promise<ControlBoardPayload> => {
    const res = await fetch(`${base}/`, { credentials: 'include' })
    if (res.status === 401 || res.status === 403) {
      throw new Error('unauthorized')
    }
    if (!res.ok) throw new Error('Failed to load control board')
    return res.json()
  }

  return { loadBoard }
}
