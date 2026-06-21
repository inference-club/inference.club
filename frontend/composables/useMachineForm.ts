// Form-factor classification for a manifest host, shared by the 2D machine
// cards (mirrors formFactorFor in useClusterState.ts, which drives the 3D
// scene). Pure function of the declared GPU/notes — no live state needed.
import { Box, Cpu, MonitorSmartphone, Server } from 'lucide-vue-next'
import type { Component } from 'vue'
import type { ManifestHost } from '@/composables/useManifest'

export type MachineForm = 'slab' | 'tower' | 'box' | 'satellite'

export interface MachineFormInfo {
  form: MachineForm
  icon: Component
  // Unified memory (DGX Spark, Apple silicon) vs discrete VRAM.
  unified: boolean
  // Accent color for the memory bar + form chip.
  accent: string
}

const SPARK_GOLD = '#d4a13c'
const NVIDIA_GREEN = '#76b900'
const SLATE = '#64748b'

// GPU-feature-discovery reports models as label-safe strings like
// "NVIDIA-GeForce-RTX-4090" or "NVIDIA-GB10". Prettify for display: drop the
// vendor prefix (shown separately) and turn hyphens back into spaces.
export function prettyGpuModel(model?: string): string {
  if (!model) return 'GPU'
  return model
    .replace(/^NVIDIA[-_\s]?/i, '')
    .replace(/[-_]+/g, ' ')
    .trim() || model
}

export function machineForm(host: ManifestHost): MachineFormInfo {
  const gpuModel = host.gpu?.model ?? ''
  const vendor = host.gpu?.vendor ?? ''
  const isExternal =
    host.id.startsWith('external-') || /external/i.test(host.notes ?? '')
  if (isExternal) {
    return { form: 'satellite', icon: MonitorSmartphone, unified: false, accent: SLATE }
  }
  // DGX Spark: compact unified-memory slab (GB10 / Grace-Blackwell).
  if (/spark|gb10|gh200|grace/i.test(gpuModel)) {
    return { form: 'slab', icon: Cpu, unified: true, accent: SPARK_GOLD }
  }
  if (vendor === 'apple') {
    return { form: 'slab', icon: Cpu, unified: true, accent: SLATE }
  }
  if (host.gpu) {
    return { form: 'tower', icon: Server, unified: false, accent: NVIDIA_GREEN }
  }
  return { form: 'box', icon: Box, unified: false, accent: SLATE }
}
