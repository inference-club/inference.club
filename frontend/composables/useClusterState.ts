// Living Cluster (PRD 07) — types + data plumbing for the 3D cluster page.
//
// The scene is driven by a single ClusterSnapshot built from two sources:
//   shape — the provider's kubernetes-derived manifest (hosts, GPUs, services)
//   live  — GET /api/inference/providers/<id>/cluster/, the backend's proxy of
//           the agent's /cluster/state (node conditions, memory, pod phases)
// Live state is progressive enhancement: the snapshot renders fully from the
// manifest alone, and the poll layers health/usage on top when available.
//
// The live types mirror the agent's ClusterState JSON
// (inference-club-agent internal/discovery/clusterstate.go) — keep in sync.

import type { ManifestGPU, ManifestService, ParsedManifest } from '@/composables/useManifest'

export interface LiveNodeCondition {
  type: string
  status: string
  reason?: string
}

export interface LiveNode {
  name: string
  host_id: string
  ready: boolean
  conditions?: LiveNodeCondition[]
  architecture?: string
  kubelet_version?: string
  os_image?: string
  memory: { allocatable_bytes: number; capacity_bytes: number; usage_bytes: number }
  gpu_allocatable: number
}

export interface LivePod {
  name: string
  service: string
  node: string
  host_id: string
  phase: string
  ready: boolean
  restarts: number
  reason?: string
  memory_usage_bytes: number
}

export interface ClusterStatePayload {
  discovery: string
  collected_at: string
  metrics_available: boolean
  nodes: LiveNode[]
  pods: LivePod[]
}

// ── Snapshot — the one structure the scene graph reads ─────────────────────

export type HostFormFactor = 'tower' | 'slab' | 'box' | 'satellite'

export interface SnapshotService {
  name: string
  type: string // llm | stt | tts | image | mesh | music | video
  engine: string
  command?: string
  models: string[]
  pods: LivePod[]
}

export interface SnapshotHost {
  id: string
  hostname?: string
  address?: string
  notes?: string
  gpu?: ManifestGPU
  external: boolean
  formFactor: HostFormFactor
  services: SnapshotService[]
  live?: LiveNode
}

export interface ClusterSnapshot {
  agentName: string
  discovery?: string
  hosts: SnapshotHost[]
  live?: ClusterStatePayload | null
}

// What the user clicked in the scene — a machine or one of its service
// modules. Lives here (not in the SFC) so both scene components can type it.
export interface ClusterSelection {
  kind: 'host' | 'service'
  host: SnapshotHost
  service?: SnapshotService
}

// Modality → hex, matching ModalityBadge's Tailwind 500-shades so the scene
// and the rest of the app speak the same color language (PRD 05).
export const MODALITY_HEX: Record<string, string> = {
  llm: '#0ea5e9', // sky-500
  stt: '#14b8a6', // teal-500
  tts: '#8b5cf6', // violet-500
  music: '#d946ef', // fuchsia-500
  image: '#f59e0b', // amber-500
  mesh: '#10b981', // emerald-500
  video: '#f43f5e', // rose-500
}

export const modalityHex = (type?: string) => MODALITY_HEX[type || 'llm'] ?? MODALITY_HEX.llm

const serviceModels = (s: ManifestService): string[] =>
  (s.models ?? [])
    .map(m => m.hf || m.id || '')
    .filter(Boolean)

function formFactorFor(host: { id: string; gpu?: ManifestGPU; notes?: string }, live?: LiveNode): HostFormFactor {
  if (host.id.startsWith('external-') || /external/i.test(host.notes ?? '')) return 'satellite'
  const gpuModel = host.gpu?.model ?? ''
  // DGX Spark: the compact gold slab. Identified by GPU product (GB10) or the
  // node's arm64 architecture once live state names it.
  if (/spark|gb10/i.test(gpuModel) || (live?.architecture === 'arm64' && host.gpu)) return 'slab'
  if (host.gpu) return 'tower'
  return 'box'
}

export function buildClusterSnapshot(
  manifest: ParsedManifest | null | undefined,
  live?: ClusterStatePayload | null,
): ClusterSnapshot | null {
  if (!manifest) return null
  const liveByHostId = new Map<string, LiveNode>()
  const podsByService = new Map<string, LivePod[]>()
  for (const n of live?.nodes ?? []) liveByHostId.set(n.host_id, n)
  for (const p of live?.pods ?? []) {
    const list = podsByService.get(p.service) ?? []
    list.push(p)
    podsByService.set(p.service, list)
  }

  const hosts: SnapshotHost[] = (manifest.hosts ?? []).map((h) => {
    const liveNode = liveByHostId.get(h.id)
    return {
      id: h.id,
      hostname: h.hostname,
      address: h.address,
      notes: h.notes,
      gpu: h.gpu,
      external: h.id.startsWith('external-') || /external/i.test(h.notes ?? ''),
      formFactor: formFactorFor(h, liveNode),
      services: (h.services ?? []).map(s => ({
        name: s.name,
        type: s.type || 'llm',
        engine: s.engine,
        command: s.command,
        models: serviceModels(s),
        pods: podsByService.get(s.name) ?? [],
      })),
      live: liveNode,
    }
  })

  // Nodes the manifest doesn't mention (e.g. a NotReady node whose services
  // all fell out of the manifest) still belong in the scene — honesty first:
  // the viz must never show a healthier cluster than kubectl does.
  for (const n of live?.nodes ?? []) {
    if (hosts.some(h => h.id === n.host_id)) continue
    hosts.push({
      id: n.host_id,
      hostname: n.name,
      external: false,
      formFactor: n.gpu_allocatable > 0
        ? (n.architecture === 'arm64' ? 'slab' : 'tower')
        : 'box',
      services: [],
      live: n,
    })
  }

  return {
    agentName: manifest.agent?.name ?? '',
    discovery: manifest.discovery,
    hosts,
    live,
  }
}

export const formatBytes = (bytes: number): string => {
  if (!bytes || bytes <= 0) return '—'
  const gib = bytes / 2 ** 30
  if (gib >= 1) return `${gib >= 10 ? Math.round(gib) : gib.toFixed(1)} GiB`
  return `${Math.round(bytes / 2 ** 20)} MiB`
}

// ── Polling ─────────────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 45_000 // PRD: live-ish, 30–60s

export const useClusterState = (providerId: () => number | null | undefined) => {
  const config = useRuntimeConfig()

  const state = ref<ClusterStatePayload | null>(null)
  // null = not yet determined; false = provider has no k8s cluster (404)
  const available = ref<boolean | null>(null)
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setInterval> | null = null

  const fetchState = async () => {
    const id = providerId()
    if (!id) return
    try {
      state.value = await $fetch<ClusterStatePayload>(
        `${config.public.apiBase}/api/inference/providers/${id}/cluster/`,
        { credentials: 'include' },
      )
      available.value = true
      error.value = null
    } catch (err: unknown) {
      const status = (err as { statusCode?: number; response?: { status?: number } })
      const code = status.statusCode ?? status.response?.status
      if (code === 404) {
        // Not a kubernetes-derived manifest — stop polling, the scene runs
        // on manifest shape alone.
        available.value = false
        stop()
      } else {
        // Agent unreachable (502 etc.): keep the last snapshot and keep
        // polling — the cluster may come back.
        available.value = available.value ?? null
        error.value = err instanceof Error ? err.message : 'cluster state unavailable'
      }
    }
  }

  const start = () => {
    if (!import.meta.client || timer) return
    void fetchState()
    timer = setInterval(fetchState, POLL_INTERVAL_MS)
  }

  const stop = () => {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  onBeforeUnmount(stop)

  return { state, available, error, start, stop, refresh: fetchState }
}
