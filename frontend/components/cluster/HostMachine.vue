<script setup lang="ts">
// One machine of the Living Cluster (PRD 07): a host from the k8s-derived
// manifest rendered as a physical computer. Form factor keys off node class —
// tower with a visible GPU card for the 4090 boxes, compact gold slab for a
// DGX Spark, generic box for unknown, floating satellite for external
// endpoints (e.g. LM Studio on a host OS). Services slot in as glowing
// modules colored by modality; live state adds the translucent memory volume
// (pods stacked inside as cargo) and degradation: a NotReady node tips over,
// unhealthy pods make their module flicker. All geometry is procedural —
// generated TRELLIS/FLUX assets are V2's progressive enhancement.
import { computed } from 'vue'
import { useScenePalette } from '@/composables/useScenePalette'
import {
  modalityHex,
  type ClusterSelection,
  type LivePod,
  type SnapshotHost,
  type SnapshotService,
} from '@/composables/useClusterState'

const props = defineProps<{
  host: SnapshotHost
  position: [number, number, number]
  // Seconds since scene start — drives the unhealthy-module flicker.
  clock: number
  selectedKey?: string | null
}>()

const emit = defineEmits<{
  select: [selection: ClusterSelection]
  hover: [hovering: boolean]
}>()

const { palette, isDark } = useScenePalette()

const DIMS: Record<string, { w: number; h: number; d: number }> = {
  tower: { w: 1.5, h: 2.2, d: 1.3 },
  slab: { w: 1.7, h: 0.45, d: 1.3 },
  box: { w: 1.3, h: 1.3, d: 1.3 },
  satellite: { w: 0.9, h: 0.25, d: 0.7 },
}

const dims = computed(() => DIMS[props.host.formFactor] ?? DIMS.box)

// Satellites float — an external endpoint lives off the cluster floor,
// tethered by a cable (drawn by the parent scene).
const FLOAT_Y = 2.0
const baseY = computed(() => (props.host.formFactor === 'satellite' ? FLOAT_Y : 0))

// Degradation: only live state may declare a node unhealthy. Shape-only
// snapshots render upright — absence of data is not a failure.
const notReady = computed(() => props.host.live != null && !props.host.live.ready)

const bodyColor = computed(() => {
  switch (props.host.formFactor) {
    case 'slab':
      return '#c9a23c' // DGX Spark gold
    case 'satellite':
      return palette.value.laptopBody
    case 'tower':
      return palette.value.pc
    default:
      return palette.value.serverBody
  }
})

const isSelected = computed(() => props.selectedKey === `host:${props.host.id}`)

// Module slots per form factor: towers/boxes stack on the front face (two
// columns past four services), slabs/satellites line up on top.
function moduleTransform(i: number): { position: [number, number, number] } {
  const { w, h, d } = dims.value
  const ff = props.host.formFactor
  if (ff === 'slab' || ff === 'satellite') {
    const n = props.host.services.length
    const x = (i - (n - 1) / 2) * 0.62
    return { position: [x, h + 0.17, 0] }
  }
  const col = Math.floor(i / 4)
  const row = i % 4
  const x = col === 0 ? (props.host.services.length > 4 ? -0.36 : 0) : 0.36
  return { position: [x, Math.min(0.5 + row * 0.45, h - 0.25), d / 2 + 0.17] }
}

interface ModuleHealth {
  flicker: boolean
  smolder: boolean
}

// A service with live pods that aren't all Running+Ready flickers; a pod
// stuck waiting (ImagePullBackOff, CrashLoopBackOff — the TRELLIS incident)
// smolders dark red between flickers. No live pods → steady (shape-only).
const moduleHealth = (s: SnapshotService): ModuleHealth => {
  if (!props.host.live || s.pods.length === 0) return { flicker: false, smolder: false }
  const unhealthy = s.pods.some(p => p.phase !== 'Running' || !p.ready)
  const wedged = s.pods.some(p => !!p.reason)
  return { flicker: unhealthy, smolder: wedged }
}

const moduleEmissiveIntensity = (s: SnapshotService): number => {
  const base = isDark.value ? 1.6 : 0.9
  const { flicker } = moduleHealth(s)
  if (notReady.value) return 0.05
  if (!flicker) return base
  // Irregular flicker: two incommensurate sines so it doesn't read as a clean
  // blink — it reads as a struggling machine.
  const t = props.clock
  const wave = 0.5 + 0.5 * Math.sin(t * 9) * Math.sin(t * 2.3)
  return base * (0.15 + 0.85 * wave)
}

const moduleColor = (s: SnapshotService): string => {
  const { smolder } = moduleHealth(s)
  if (smolder) {
    // Smoldering: pulse between the modality color and ember red.
    const t = 0.5 + 0.5 * Math.sin(props.clock * 3)
    return t > 0.5 ? '#7f1d1d' : modalityHex(s.type)
  }
  return modalityHex(s.type)
}

// ── Memory volume (live only): allocatable shell, usage fill, pod cargo ────

const MEM_VOL_H = 1.9
const memVolume = computed(() => {
  const live = props.host.live
  if (!live || live.memory.allocatable_bytes <= 0) return null
  const frac = live.memory.usage_bytes > 0
    ? Math.min(1, live.memory.usage_bytes / live.memory.allocatable_bytes)
    : 0
  return { frac, fillH: Math.max(0.02, frac * MEM_VOL_H) }
})

interface PodBrick {
  pod: LivePod
  color: string
  h: number
  y: number
}

const podBricks = computed<PodBrick[]>(() => {
  const live = props.host.live
  if (!live || live.memory.allocatable_bytes <= 0) return []
  const typeByService = new Map(props.host.services.map(s => [s.name, s.type]))
  const bricks: PodBrick[] = []
  let y = 0.06
  for (const s of props.host.services) {
    for (const pod of s.pods) {
      if (pod.host_id !== props.host.id) continue
      const h = Math.max(0.12, (pod.memory_usage_bytes / live.memory.allocatable_bytes) * MEM_VOL_H)
      bricks.push({ pod, color: modalityHex(typeByService.get(pod.service)), h, y: y + h / 2 })
      y += h + 0.05
    }
  }
  return bricks
})

const gpuChips = computed(() =>
  props.host.gpu ? Array.from({ length: Math.max(1, props.host.gpu.count ?? 1) }, (_, i) => i) : [])

// ── Interaction ─────────────────────────────────────────────────────────────

type TresPointerEvent = { stopPropagation?: () => void }

const selectHost = (e?: TresPointerEvent) => {
  e?.stopPropagation?.()
  emit('select', { kind: 'host', host: props.host })
}
const selectService = (s: SnapshotService, e?: TresPointerEvent) => {
  e?.stopPropagation?.()
  emit('select', { kind: 'service', host: props.host, service: s })
}
const setHover = (h: boolean) => {
  emit('hover', h)
  if (import.meta.client) document.body.style.cursor = h ? 'pointer' : ''
}
</script>

<template>
  <TresGroup :position="position">
    <!--
      NotReady → the machine tips over (rotated about its floor edge) and its
      lights die. The viz must never show a healthier cluster than kubectl.
    -->
    <TresGroup
      :rotation="notReady ? [0, 0, -1.25] : [0, 0, 0]"
      :position="notReady ? [dims.h * 0.42, 0, 0] : [0, 0, 0]"
    >
      <!-- Pedestal (cluster machines sit on a low plinth; satellites float) -->
      <TresMesh v-if="host.formFactor !== 'satellite'" :position="[0, 0.06, 0]" receive-shadow>
        <TresBoxGeometry :args="[dims.w + 0.7, 0.12, dims.d + 0.7]" />
        <TresMeshStandardMaterial :color="palette.deskDark" :roughness="0.9" />
      </TresMesh>

      <!-- Body -->
      <TresMesh
        :position="[0, baseY + dims.h / 2 + 0.12, 0]"
        cast-shadow
        @click="selectHost"
        @pointer-enter="setHover(true)"
        @pointer-leave="setHover(false)"
      >
        <TresBoxGeometry :args="[dims.w, dims.h, dims.d]" />
        <TresMeshStandardMaterial
          :color="bodyColor"
          :metalness="host.formFactor === 'slab' ? 0.85 : 0.3"
          :roughness="host.formFactor === 'slab' ? 0.25 : 0.6"
          :emissive="isSelected ? '#6366f1' : '#000000'"
          :emissive-intensity="isSelected ? 0.35 : 0"
        />
      </TresMesh>

      <!-- Power LED: green alive, red down -->
      <TresMesh :position="[dims.w / 2 - 0.16, baseY + dims.h + 0.04, dims.d / 2 - 0.16]">
        <TresSphereGeometry :args="[0.05, 10, 8]" />
        <TresMeshBasicMaterial :color="notReady ? '#ef4444' : '#22c55e'" />
      </TresMesh>

      <!-- Visible GPU card (towers): dark PCB + one VRAM chip per GPU -->
      <template v-if="host.formFactor === 'tower' && host.gpu">
        <TresMesh :position="[0, baseY + 0.42, dims.d / 2 + 0.06]">
          <TresBoxGeometry :args="[dims.w * 0.78, 0.3, 0.1]" />
          <TresMeshStandardMaterial color="#10131c" :roughness="0.4" :metalness="0.5" />
        </TresMesh>
        <TresMesh
          v-for="i in gpuChips"
          :key="`chip-${i}`"
          :position="[-dims.w * 0.3 + i * 0.3, baseY + 0.42, dims.d / 2 + 0.12]"
        >
          <TresBoxGeometry :args="[0.2, 0.16, 0.04]" />
          <TresMeshStandardMaterial
            color="#76b900"
            :emissive="notReady ? '#000000' : '#76b900'"
            :emissive-intensity="notReady ? 0 : (isDark ? 0.8 : 0.3)"
          />
        </TresMesh>
      </template>

      <!-- Service modules: glowing cartridges, one hue per modality -->
      <TresMesh
        v-for="(s, i) in host.services"
        :key="s.name"
        :position="moduleTransform(i).position"
        @click="(e: any) => selectService(s, e)"
        @pointer-enter="setHover(true)"
        @pointer-leave="setHover(false)"
      >
        <TresBoxGeometry :args="[0.55, 0.32, 0.3]" />
        <TresMeshStandardMaterial
          :color="moduleColor(s)"
          :emissive="moduleColor(s)"
          :emissive-intensity="moduleEmissiveIntensity(s)"
          :roughness="0.35"
        />
      </TresMesh>
    </TresGroup>

    <!-- Memory volume: allocatable shell, usage fill, pods as stacked cargo -->
    <TresGroup v-if="memVolume" :position="[dims.w / 2 + 0.95, 0.12, 0]">
      <TresMesh :position="[0, MEM_VOL_H / 2, 0]">
        <TresBoxGeometry :args="[0.8, MEM_VOL_H, 0.8]" />
        <TresMeshStandardMaterial
          color="#38bdf8"
          :transparent="true"
          :opacity="0.12"
          :depth-write="false"
        />
      </TresMesh>
      <TresMesh v-if="memVolume.frac > 0" :position="[0, memVolume.fillH / 2, 0]">
        <TresBoxGeometry :args="[0.76, memVolume.fillH, 0.76]" />
        <TresMeshStandardMaterial
          color="#0ea5e9"
          :transparent="true"
          :opacity="0.3"
          :depth-write="false"
        />
      </TresMesh>
      <TresMesh
        v-for="brick in podBricks"
        :key="brick.pod.name"
        :position="[0, brick.y, 0]"
      >
        <TresBoxGeometry :args="[0.6, brick.h, 0.6]" />
        <TresMeshStandardMaterial
          :color="brick.color"
          :emissive="brick.color"
          :emissive-intensity="isDark ? 0.5 : 0.15"
          :transparent="true"
          :opacity="0.85"
        />
      </TresMesh>
    </TresGroup>
  </TresGroup>
</template>
