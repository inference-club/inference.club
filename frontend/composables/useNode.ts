// Client for the node (host) detail endpoint
// GET /api/inference/providers/<id>/hosts/<host_id>/ — specs, the GPUs on the
// node, the services running on it, generation stats, and recent generations.
// Live VRAM/utilization is overlaid separately via useClusterState.
import type { InferenceRequest } from '@/types'

export interface NodeGpu {
  index: number
  vendor?: string
  model?: string | null
  vram_gb?: number | null
  is_active?: boolean
}

export interface NodeService {
  id: number
  name: string
  engine?: string
  host_id?: string | null
  models?: string[]
  is_active?: boolean
}

export interface NodeStats {
  total: number
  avg_latency_ms?: number | null
  total_completion_tokens?: number
  by_modality: Record<string, number>
}

export interface NodeDetail {
  host_id: string
  hostname?: string
  address?: string
  notes?: string
  is_active?: boolean
  is_owner?: boolean
  provider: { id: number; name: string; owner_handle?: string | null; is_online?: boolean }
  gpus: NodeGpu[]
  services: NodeService[]
  stats: NodeStats
  recent: InferenceRequest[]
}

export function useNode() {
  const config = useRuntimeConfig()
  const apiBase =
    import.meta.server && config.apiBaseInternal
      ? (config.apiBaseInternal as string)
      : (config.public.apiBase as string)

  const nodeUrl = (providerId: number, hostId: string) =>
    `${apiBase}/api/inference/providers/${providerId}/hosts/${encodeURIComponent(hostId)}/`

  return { apiBase, nodeUrl }
}
