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
import { AdditiveBlending } from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import { useClusterPalette } from '@/composables/useClusterPalette'
import { radialGlowTexture } from '@/utils/glow'
import {
  modalityHex,
  type ClusterSelection,
  type LivePod,
  type SnapshotHost,
  type SnapshotService,
} from '@/composables/useClusterState'
import type { LoadedClusterAsset } from '@/composables/useClusterAssets'

const props = defineProps<{
  host: SnapshotHost
  position: [number, number, number]
  // Y rotation in radians — the arc layout turns each machine toward the hub.
  rotationY?: number
  // Seconds since scene start — drives the unhealthy-module flicker.
  clock: number
  selectedKey?: string | null
  // Generated chassis (PRD 07 V2): a TRELLIS-made GLB replacing the
  // procedural body. Absent → procedural boxes (progressive enhancement).
  asset?: LoadedClusterAsset | null
}>()

const emit = defineEmits<{
  select: [selection: ClusterSelection]
  hover: [hovering: boolean]
}>()

const { palette, isDark } = useClusterPalette()

// Dark-mode neon: a shared radial gradient, tinted per use and rendered
// additively — cheap glow without a bloom pass.
const glowTex = import.meta.client ? radialGlowTexture() : null

const DIMS: Record<string, { w: number; h: number; d: number }> = {
  tower: { w: 1.4, h: 1.65, d: 1.15 },
  slab: { w: 1.7, h: 0.45, d: 1.3 },
  box: { w: 1.2, h: 1.2, d: 1.2 },
  satellite: { w: 0.9, h: 0.25, d: 0.7 },
}

const dims = computed(() => DIMS[props.host.formFactor] ?? DIMS.box)

// Rounded chassis geometry, cached per form factor (chamfered edges catch
// the env-map light — square boxes read as cardboard, these read as metal).
const BODY_GEO_CACHE = new Map<string, RoundedBoxGeometry>()
const bodyGeometry = computed(() => {
  const { w, h, d } = dims.value
  const key = `${w}x${h}x${d}`
  let geo = BODY_GEO_CACHE.get(key)
  if (!geo) {
    geo = new RoundedBoxGeometry(w, h, d, 3, Math.min(w, h, d) * 0.07)
    BODY_GEO_CACHE.set(key, geo)
  }
  return geo
})

// Material finish per form factor: brushed gunmetal towers, polished gold
// slab, plastic satellite tile.
const bodyFinish = computed(() => {
  switch (props.host.formFactor) {
    case 'slab':
      return { metalness: 0.8, roughness: 0.28 }
    case 'satellite':
      return { metalness: 0.3, roughness: 0.5 }
    default:
      return { metalness: 0.5, roughness: 0.45 }
  }
})

// Satellites float — an external endpoint lives off the cluster floor,
// tethered by a cable (drawn by the parent scene).
const FLOAT_Y = 1.35
const baseY = computed(() => (props.host.formFactor === 'satellite' ? FLOAT_Y : 0))

// Degradation: only live state may declare a node unhealthy. Shape-only
// snapshots render upright — absence of data is not a failure.
const notReady = computed(() => props.host.live != null && !props.host.live.ready)

const bodyColor = computed(() => {
  switch (props.host.formFactor) {
    case 'slab':
      return palette.value.slab // DGX Spark gold
    case 'satellite':
      return palette.value.satellite
    case 'tower':
      return palette.value.tower
    default:
      return palette.value.box
  }
})

// The machine's neon accent: its first service's modality color, so the
// underglow says what the box does. Cyan for service-less nodes.
const accentColor = computed(() =>
  notReady.value ? '#ef4444' : (props.host.services[0] ? modalityHex(props.host.services[0].type) : '#22d3ee'))

const bodyEmissive = computed(() => {
  if (isSelected.value) return { color: '#6366f1', intensity: 0.35 }
  if (isDark.value && !notReady.value) {
    // The gold slab smolders warm; everything else self-illuminates a cool
    // slate-blue so silhouettes read against the dark floor. A dead node
    // gets none — it should look dead.
    if (props.host.formFactor === 'slab') return { color: '#8a6914', intensity: 0.35 }
    return { color: '#22335f', intensity: 0.65 }
  }
  return { color: '#000000', intensity: 0 }
})

const isSelected = computed(() => props.selectedKey === `host:${props.host.id}`)

// The generated chassis, cloned per host (one GLB instance per machine) and
// scaled from the loader's unit-normalized size up to this form factor.
const assetObject = computed(() => {
  if (!props.asset) return null
  const clone = props.asset.object.clone(true)
  const target = Math.max(dims.value.w, dims.value.h, dims.value.d)
  clone.scale.multiplyScalar(target)
  return clone
})

// Module slots per form factor: towers/boxes stack on the front face (two
// columns past three services), slabs/satellites line up on top.
function moduleTransform(i: number): { position: [number, number, number] } {
  const { h, d } = dims.value
  const ff = props.host.formFactor
  if (ff === 'slab' || ff === 'satellite') {
    const n = props.host.services.length
    const x = (i - (n - 1) / 2) * 0.62
    // baseY lifts satellite modules up to the floating device.
    return { position: [x, baseY.value + h + 0.29, 0] }
  }
  const col = Math.floor(i / 3)
  const row = i % 3
  const x = col === 0 ? (props.host.services.length > 3 ? -0.36 : 0) : 0.36
  return { position: [x, Math.min(0.46 + row * 0.42, h - 0.22), d / 2 + 0.17] }
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

// Glow halo behind each module (dark mode): sits just outside the module
// face and breathes with the same flicker as the emissive, so an unhealthy
// module's halo gutters too.
const moduleGlowPos = (i: number): [number, number, number] => {
  const [x, y, z] = moduleTransform(i).position
  const ff = props.host.formFactor
  if (ff === 'slab' || ff === 'satellite') return [x, y + 0.14, z]
  return [x, y, z + 0.18]
}

const moduleGlowOpacity = (s: SnapshotService): number => {
  const base = isDark.value ? 1.6 : 0.9
  return 0.18 + 0.3 * (moduleEmissiveIntensity(s) / base)
}

// ── Memory volume (live only): allocatable shell, usage fill, pod cargo ────

const MEM_VOL_H = 1.6
const memVolume = computed(() => {
  const live = props.host.live
  if (!live || live.memory.allocatable_bytes <= 0) return null
  const frac = live.memory.usage_bytes > 0
    ? Math.min(1, live.memory.usage_bytes / live.memory.allocatable_bytes)
    : 0
  return { frac, fillH: Math.max(0.02, frac * MEM_VOL_H) }
})

// GPU VRAM pillar (live dcgm only): the green twin of the RAM gauge. Fill =
// VRAM used / total; its glow tracks GPU utilization so a saturated 4090 reads
// as "hot" at a glance. nil when the node has no live dcgm data (a2/spark) — the
// pillar simply doesn't render there.
const gpuVolume = computed(() => {
  const gpu = props.host.live?.gpu
  if (!gpu || gpu.vram_total_bytes <= 0) return null
  const frac = gpu.vram_used_bytes > 0
    ? Math.min(1, gpu.vram_used_bytes / gpu.vram_total_bytes)
    : 0
  return {
    frac,
    fillH: Math.max(0.02, frac * MEM_VOL_H),
    util: Math.max(0, Math.min(100, gpu.util_percent)) / 100,
  }
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
  <TresGroup :position="position" :rotation="[0, rotationY ?? 0, 0]">
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
        <TresBoxGeometry :args="[dims.w + 0.55, 0.12, dims.d + 0.55]" />
        <TresMeshStandardMaterial :color="palette.pedestal" :roughness="0.55" :metalness="0.45" />
      </TresMesh>

      <!-- Body: generated chassis when an asset exists, procedural box else -->
      <primitive
        v-if="assetObject"
        :object="assetObject"
        :position="[0, baseY + 0.12, 0]"
        @click="selectHost"
        @pointer-enter="setHover(true)"
        @pointer-leave="setHover(false)"
      />
      <TresMesh
        v-else
        :position="[0, baseY + dims.h / 2 + 0.12, 0]"
        :geometry="bodyGeometry"
        cast-shadow
        receive-shadow
        @click="selectHost"
        @pointer-enter="setHover(true)"
        @pointer-leave="setHover(false)"
      >
        <TresMeshStandardMaterial
          :color="bodyColor"
          :metalness="bodyFinish.metalness"
          :roughness="bodyFinish.roughness"
          :emissive="bodyEmissive.color"
          :emissive-intensity="bodyEmissive.intensity"
        />
      </TresMesh>

      <!-- Brushed top plate: a slightly inset lighter cap so the silhouette
           reads as machined, not extruded -->
      <TresMesh
        v-if="!assetObject && host.formFactor !== 'satellite'"
        :position="[0, baseY + dims.h + 0.12, 0]"
      >
        <TresBoxGeometry :args="[dims.w * 0.86, 0.035, dims.d * 0.86]" />
        <TresMeshStandardMaterial :color="bodyColor" :metalness="0.75" :roughness="0.3" />
      </TresMesh>

      <!-- Front detailing (procedural towers/boxes only): vent slits up top
           and a thin accent strip along the bottom edge in the machine's
           modality color, so each box carries its service hue in both modes. -->
      <template v-if="!assetObject && (host.formFactor === 'tower' || host.formFactor === 'box')">
        <TresMesh
          v-for="k in 3"
          :key="`vent-${k}`"
          :position="[0, baseY + dims.h - 0.06 - k * 0.09, dims.d / 2 + 0.012]"
        >
          <TresBoxGeometry :args="[dims.w * 0.55, 0.028, 0.02]" />
          <TresMeshStandardMaterial :color="palette.vent" :roughness="0.45" :metalness="0.4" />
        </TresMesh>
        <!-- Neon corner bars (dark): vertical accent light on each front edge -->
        <template v-if="isDark && !notReady">
          <TresMesh
            v-for="side in [-1, 1]"
            :key="`edge-${side}`"
            :position="[side * (dims.w / 2 - 0.01), baseY + 0.12 + dims.h / 2, dims.d / 2 + 0.005]"
          >
            <TresBoxGeometry :args="[0.022, dims.h * 0.72, 0.018]" />
            <TresMeshStandardMaterial
              :color="accentColor"
              :emissive="accentColor"
              :emissive-intensity="0.9"
              :roughness="0.4"
            />
          </TresMesh>
        </template>
      </template>
      <TresMesh
        v-if="!assetObject && host.formFactor !== 'satellite'"
        :position="[0, baseY + 0.17, dims.d / 2 + 0.02]"
      >
        <TresBoxGeometry :args="[dims.w * 0.92, 0.05, 0.03]" />
        <TresMeshStandardMaterial
          :color="accentColor"
          :emissive="accentColor"
          :emissive-intensity="notReady ? 0 : (isDark ? 1.3 : 0.7)"
          :roughness="0.4"
        />
      </TresMesh>

      <!-- Selection ring: highlight that works for any chassis (generated
           materials can't be tinted the way the procedural box can) -->
      <TresMesh v-if="isSelected" :position="[0, 0.14, 0]" :rotation="[-Math.PI / 2, 0, 0]">
        <TresRingGeometry :args="[Math.max(dims.w, dims.d) * 0.72, Math.max(dims.w, dims.d) * 0.82, 32]" />
        <TresMeshBasicMaterial color="#6366f1" :transparent="true" :opacity="0.7" :depth-write="false" />
      </TresMesh>

      <!-- Power LED: green alive, red down -->
      <TresMesh :position="[dims.w / 2 - 0.16, baseY + dims.h + 0.04, dims.d / 2 - 0.16]">
        <TresSphereGeometry :args="[0.05, 10, 8]" />
        <TresMeshBasicMaterial :color="notReady ? '#ef4444' : '#22c55e'" />
      </TresMesh>
      <TresSprite
        v-if="isDark && glowTex"
        :position="[dims.w / 2 - 0.16, baseY + dims.h + 0.04, dims.d / 2 - 0.16]"
        :scale="[0.45, 0.45, 1]"
      >
        <TresSpriteMaterial
          :map="glowTex"
          :color="notReady ? '#ef4444' : '#22c55e'"
          :transparent="true"
          :opacity="0.55"
          :blending="AdditiveBlending"
          :depth-write="false"
        />
      </TresSprite>

      <!-- Visible GPU card (towers): dark PCB + one VRAM chip per GPU.
           Skipped under a generated chassis — it would clip into the mesh. -->
      <template v-if="host.formFactor === 'tower' && host.gpu && !assetObject">
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
        cast-shadow
        @click="(e: any) => selectService(s, e)"
        @pointer-enter="setHover(true)"
        @pointer-leave="setHover(false)"
      >
        <TresBoxGeometry :args="[0.55, 0.32, 0.3]" />
        <TresMeshStandardMaterial
          :color="moduleColor(s)"
          :emissive="moduleColor(s)"
          :emissive-intensity="moduleEmissiveIntensity(s)"
          :metalness="0.2"
          :roughness="0.3"
        />
      </TresMesh>

      <!-- Neon halos behind the modules (dark mode) -->
      <template v-if="isDark && glowTex && !notReady">
        <TresSprite
          v-for="(s, i) in host.services"
          :key="`halo-${s.name}`"
          :position="moduleGlowPos(i)"
          :scale="[1.15, 0.8, 1]"
        >
          <TresSpriteMaterial
            :map="glowTex"
            :color="moduleColor(s)"
            :transparent="true"
            :opacity="moduleGlowOpacity(s)"
            :blending="AdditiveBlending"
            :depth-write="false"
          />
        </TresSprite>
      </template>
    </TresGroup>

    <!-- Underglow pool (dark mode): the machine lights its patch of floor in
         its accent color — red when the node is down -->
    <TresMesh
      v-if="isDark && glowTex && host.formFactor !== 'satellite'"
      :position="[0, 0.14, 0]"
      :rotation="[-Math.PI / 2, 0, 0]"
    >
      <TresPlaneGeometry :args="[dims.w + 2.6, dims.d + 2.6]" />
      <TresMeshBasicMaterial
        :map="glowTex"
        :color="accentColor"
        :transparent="true"
        :opacity="notReady ? 0.24 : 0.4"
        :blending="AdditiveBlending"
        :depth-write="false"
      />
    </TresMesh>

    <!-- Memory pillar: allocatable shell, usage fill, pods as stacked cargo.
         Slim and flush against the machine's side so it reads as a gauge on
         the box, not a second building. -->
    <TresGroup v-if="memVolume" :position="[dims.w / 2 + 0.52, 0.12, 0]">
      <TresMesh :position="[0, MEM_VOL_H / 2, 0]">
        <TresBoxGeometry :args="[0.5, MEM_VOL_H, 0.5]" />
        <TresMeshStandardMaterial
          color="#38bdf8"
          :transparent="true"
          :opacity="isDark ? 0.1 : 0.08"
          :depth-write="false"
        />
      </TresMesh>
      <!-- Cap line marking 100% of allocatable -->
      <TresMesh :position="[0, MEM_VOL_H, 0]">
        <TresBoxGeometry :args="[0.54, 0.02, 0.54]" />
        <TresMeshBasicMaterial color="#38bdf8" :transparent="true" :opacity="isDark ? 0.5 : 0.35" />
      </TresMesh>
      <TresMesh v-if="memVolume.frac > 0" :position="[0, memVolume.fillH / 2, 0]">
        <TresBoxGeometry :args="[0.46, memVolume.fillH, 0.46]" />
        <TresMeshStandardMaterial
          color="#0ea5e9"
          :emissive="isDark ? '#0ea5e9' : '#000000'"
          :emissive-intensity="isDark ? 0.35 : 0"
          :transparent="true"
          :opacity="isDark ? 0.34 : 0.25"
          :depth-write="false"
        />
      </TresMesh>
      <TresMesh
        v-for="brick in podBricks"
        :key="brick.pod.name"
        :position="[0, brick.y, 0]"
      >
        <TresBoxGeometry :args="[0.36, brick.h, 0.36]" />
        <TresMeshStandardMaterial
          :color="brick.color"
          :emissive="brick.color"
          :emissive-intensity="isDark ? 0.8 : 0.15"
          :transparent="true"
          :opacity="0.85"
        />
      </TresMesh>
    </TresGroup>

    <!-- GPU VRAM pillar: green twin of the RAM gauge, one slot further out so
         "regular memory" and "GPU memory" sit side by side. Fill = VRAM
         used/total; the fill's glow tracks GPU utilization. No pod cargo —
         VRAM isn't attributed per pod. Live dcgm-exporter data only. -->
    <TresGroup v-if="gpuVolume" :position="[dims.w / 2 + 1.12, 0.12, 0]">
      <TresMesh :position="[0, MEM_VOL_H / 2, 0]">
        <TresBoxGeometry :args="[0.5, MEM_VOL_H, 0.5]" />
        <TresMeshStandardMaterial
          color="#22c55e"
          :transparent="true"
          :opacity="isDark ? 0.1 : 0.08"
          :depth-write="false"
        />
      </TresMesh>
      <!-- Cap line marking 100% of VRAM -->
      <TresMesh :position="[0, MEM_VOL_H, 0]">
        <TresBoxGeometry :args="[0.54, 0.02, 0.54]" />
        <TresMeshBasicMaterial color="#22c55e" :transparent="true" :opacity="isDark ? 0.5 : 0.35" />
      </TresMesh>
      <TresMesh v-if="gpuVolume.frac > 0" :position="[0, gpuVolume.fillH / 2, 0]">
        <TresBoxGeometry :args="[0.46, gpuVolume.fillH, 0.46]" />
        <TresMeshStandardMaterial
          color="#16a34a"
          :emissive="isDark ? '#22c55e' : '#000000'"
          :emissive-intensity="isDark ? 0.25 + gpuVolume.util * 0.9 : 0"
          :transparent="true"
          :opacity="isDark ? 0.34 : 0.25"
          :depth-write="false"
        />
      </TresMesh>
    </TresGroup>
  </TresGroup>
</template>
