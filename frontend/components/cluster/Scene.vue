<script setup lang="ts">
// Living Cluster scene (PRD 07) — a walkable 3D rendering of a provider's
// Kubernetes fleet. Machines (ClusterHostMachine) stand in an arc on a round
// platform, facing the agent hub at the front; external endpoints float as
// tethered satellites off the platform's edge. Live state (when present on
// the snapshot) drives memory pillars, pod health and degradation. Follows
// NetworkScene's TresJS patterns: declarative meshes, runtime-built
// polylines, HTML overlay labels projected per frame.
import { TresCanvas } from '@tresjs/core'
import { OrbitControls, Text3D } from '@tresjs/cientos'
import { computed, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import * as THREE from 'three'
import { HelpCircle } from 'lucide-vue-next'
import JackObjModel from '@/components/logo/JackObjModel.vue'
import { useClusterPalette } from '@/composables/useClusterPalette'
import { ENGINE_LABELS, VENDOR_LABELS } from '@/composables/useManifest'
import {
  formatBytes,
  modalityHex,
  type ClusterSelection,
  type ClusterSnapshot,
  type SnapshotHost,
  type SnapshotService,
} from '@/composables/useClusterState'
import { useClusterAssets } from '@/composables/useClusterAssets'
import { radialGlowTexture } from '@/utils/glow'
import type { InferenceType } from '@/types'

const props = defineProps<{
  snapshot: ClusterSnapshot
  // Owner view shows exact pod commands; public view redacts them
  // (commands can leak paths/flags — PRD 07 open question, default redact).
  showCommands?: boolean
}>()

const { palette, isDark } = useClusterPalette()

// Generated chassis assets (V2) — empty map until loaded; machines render
// procedurally in the meantime and swap in meshes when they arrive.
const clusterAssets = useClusterAssets()

// Dark-mode neon: shared glow sprite texture + additive blending constants.
const glowTex = import.meta.client ? radialGlowTexture() : null
const ADDITIVE = THREE.AdditiveBlending
const NORMAL = THREE.NormalBlending

// ── Layout ──────────────────────────────────────────────────────────────────
//
// Internal machines stand on an arc around the platform's center, all facing
// the agent hub at the front edge — the hub is where requests enter, so the
// whole fleet "looks at" its front door. Satellites (external endpoints)
// float off the platform's right edge: outside the cluster, tethered in.

interface PlacedHost {
  host: SnapshotHost
  position: [number, number, number]
  rotationY: number
}

const layout = computed(() => {
  const internals = props.snapshot.hosts.filter(h => !h.external)
  const externals = props.snapshot.hosts.filter(h => h.external)
  const n = Math.max(1, internals.length)

  // Arc radius grows gently with the fleet; spread caps so big fleets wrap
  // further around rather than stretching wide.
  const R = Math.max(4.6, 2.1 * Math.sqrt(n) + 2.2)
  const platformR = R + 2.7
  const hub: [number, number, number] = [0, 0, R * 0.78]

  const spread = n === 1 ? 0 : Math.min(2.1, 0.66 * (n - 1))
  const placed: PlacedHost[] = internals.map((host, i) => {
    const theta = n === 1 ? 0 : -spread / 2 + (spread * i) / (n - 1)
    const x = R * Math.sin(theta)
    const z = -R * Math.cos(theta) * 0.82
    return {
      host,
      position: [x, 0, z] as [number, number, number],
      rotationY: Math.atan2(hub[0] - x, hub[2] - z),
    }
  })

  // Satellites float above the platform's front-left airspace (the right is
  // where chip labels stack up) — visibly tethered in, but not standing with
  // the cluster machines.
  externals.forEach((host, j) => {
    const x = -R * (0.68 + 0.1 * (j % 2))
    const z = 2.6 + j * 2.2
    placed.push({
      host,
      position: [x, 0, z],
      rotationY: Math.atan2(hub[0] - x, hub[2] - z),
    })
  })

  return { placed, hub, R, platformR }
})

// ── Selection / hover ───────────────────────────────────────────────────────

const selection = ref<ClusterSelection | null>(null)
const selectedKey = computed(() => {
  const s = selection.value
  if (!s) return null
  return s.kind === 'host' ? `host:${s.host.id}` : `service:${s.service?.name}`
})

const onSelect = (sel: ClusterSelection) => {
  selection.value = sel
}
const clearSelection = () => {
  selection.value = null
}

// Hover state drives label density: a bare hostname tag by default, the full
// info chip only for the hovered or selected machine (the always-on chips
// read as clutter — design pass 2 feedback).
const hoveredHostId = ref<string | null>(null)
const onHostHover = (id: string, hovering: boolean) => {
  if (hovering) hoveredHostId.value = id
  else if (hoveredHostId.value === id) hoveredHostId.value = null
}
const chipVisible = (h: SnapshotHost) =>
  hoveredHostId.value === h.id || selection.value?.host.id === h.id

// Selection survives live-state refreshes by re-resolving against the new
// snapshot (object identity changes every poll).
watch(() => props.snapshot, (snap) => {
  const s = selection.value
  if (!s) return
  const host = snap.hosts.find(h => h.id === s.host.id)
  if (!host) {
    selection.value = null
    return
  }
  if (s.kind === 'host') {
    selection.value = { kind: 'host', host }
    return
  }
  const service = host.services.find(x => x.name === s.service?.name)
  selection.value = service ? { kind: 'service', host, service } : { kind: 'host', host }
})

const modalitiesPresent = computed(() => {
  const seen = new Set<string>()
  for (const h of props.snapshot.hosts) for (const s of h.services) seen.add(s.type)
  return [...seen].sort()
})

const liveAgeSeconds = ref<number | null>(null)

// Fleet roll-up for the status bar: the at-a-glance numbers a visitor needs
// before clicking anything.
const stats = computed(() => {
  const hosts = props.snapshot.hosts
  const gpus = hosts.reduce((a, h) => a + (h.gpu?.count ?? 0), 0)
  const services = hosts.reduce((a, h) => a + h.services.length, 0)
  const live = props.snapshot.live
  if (!live) return { gpus, services, nodesReady: null as number | null, nodesTotal: hosts.filter(h => !h.external).length, podsRunning: null as number | null, podsTotal: null as number | null, ram: null as { used: number; alloc: number } | null }
  return {
    gpus,
    services,
    nodesReady: live.nodes.filter(nd => nd.ready).length,
    nodesTotal: live.nodes.length,
    podsRunning: live.pods.filter(p => p.phase === 'Running' && p.ready).length,
    podsTotal: live.pods.length,
    ram: {
      used: live.nodes.reduce((a, nd) => a + nd.memory.usage_bytes, 0),
      alloc: live.nodes.reduce((a, nd) => a + nd.memory.allocatable_bytes, 0),
    },
  }
})

// ── Runtime objects: cables from the agent hub to every machine ────────────

const cablesGroupRef = shallowRef<THREE.Group | null>(null)
let cableMaterial: THREE.LineDashedMaterial | null = null

function rebuildCables() {
  const group = cablesGroupRef.value
  if (!group) return
  for (const child of group.children) (child as THREE.Line).geometry?.dispose()
  group.clear()
  cableMaterial?.dispose()
  // Additive dashes in the dark read as light running through fiber.
  cableMaterial = new THREE.LineDashedMaterial({
    color: palette.value.cable,
    dashSize: 0.18,
    gapSize: 0.14,
    transparent: true,
    opacity: isDark.value ? 0.95 : 0.85,
    blending: isDark.value ? THREE.AdditiveBlending : THREE.NormalBlending,
    depthWrite: !isDark.value,
  })
  const { placed, hub } = layout.value
  const hubTop = new THREE.Vector3(hub[0], 0.9, hub[2])
  for (const p of placed) {
    const end = new THREE.Vector3(
      p.position[0],
      p.host.formFactor === 'satellite' ? 1.35 : 0.35,
      p.position[2],
    )
    const mid = new THREE.Vector3((hubTop.x + end.x) / 2, 0.08, (hubTop.z + end.z) / 2)
    const geo = new THREE.BufferGeometry().setFromPoints([hubTop, mid, end])
    const line = new THREE.Line(geo, cableMaterial)
    line.computeLineDistances()
    group.add(line)
  }
}

// ── Request pulses (V1 "Flow"): per-service activity → pulses hub → machine ─
//
// The activity endpoint buckets the provider's served requests per service
// per minute; the freshest buckets set each service's pulse rate. No
// activity → no pulses: the flow animation only shows traffic that exists.

interface Pulse {
  id: number
  color: string
  position: [number, number, number]
  opacity: number
}

const PULSE_FLIGHT_SEC = 1.4
const MAX_PULSES = 48
const pulses = reactive<Pulse[]>([])
// Bookkeeping that doesn't need reactivity: flight paths + spawn clocks.
const pulseFlights = new Map<number, { start: number; points: THREE.Vector3[] }>()
const nextSpawnByService = new Map<string, number>()
let pulseSeq = 0

function pulseIntervalFor(s: SnapshotService): number | null {
  const buckets = s.activity?.buckets
  if (!buckets?.length) return null
  // Rate from the trailing 5 minutes, so a burst fades out within minutes.
  const recent = buckets.slice(-5).reduce((a, b) => a + b, 0)
  if (recent <= 0) return null
  return THREE.MathUtils.clamp(60 / (recent / 5), 2, 20)
}

const pulseSources = computed(() => {
  const { hub, placed } = layout.value
  const hubTop = new THREE.Vector3(hub[0], 0.9, hub[2])
  const out: { key: string; interval: number; color: string; points: THREE.Vector3[] }[] = []
  for (const p of placed) {
    for (const s of p.host.services) {
      const interval = pulseIntervalFor(s)
      if (!interval) continue
      const end = new THREE.Vector3(
        p.position[0],
        p.host.formFactor === 'satellite' ? 1.45 : 0.9,
        p.position[2],
      )
      const mid = new THREE.Vector3((hubTop.x + end.x) / 2, 0.12, (hubTop.z + end.z) / 2)
      out.push({ key: s.name, interval, color: modalityHex(s.type), points: [hubTop, mid, end] })
    }
  }
  return out
})

const _pulseVec = new THREE.Vector3()

function samplePolyline(points: THREE.Vector3[], t: number): THREE.Vector3 {
  const segA = points[1].clone().sub(points[0]).length()
  const segB = points[2].clone().sub(points[1]).length()
  const total = segA + segB || 1
  const dist = THREE.MathUtils.clamp(t, 0, 1) * total
  if (dist <= segA) return _pulseVec.lerpVectors(points[0], points[1], segA > 0 ? dist / segA : 0)
  return _pulseVec.lerpVectors(points[1], points[2], segB > 0 ? (dist - segA) / segB : 0)
}

function tickPulses(now: number) {
  for (const src of pulseSources.value) {
    let next = nextSpawnByService.get(src.key)
    if (next === undefined) {
      // Stagger first spawns so services don't fire in lockstep.
      next = now + Math.random() * src.interval
      nextSpawnByService.set(src.key, next)
    }
    while (now >= next) {
      if (pulses.length < MAX_PULSES) {
        const id = pulseSeq++
        pulses.push({ id, color: src.color, position: [src.points[0].x, src.points[0].y, src.points[0].z], opacity: 0 })
        pulseFlights.set(id, { start: next, points: src.points })
      }
      next += src.interval
    }
    nextSpawnByService.set(src.key, next)
  }
  for (let i = pulses.length - 1; i >= 0; i--) {
    const pulse = pulses[i]
    const flight = pulseFlights.get(pulse.id)
    const t = flight ? (now - flight.start) / PULSE_FLIGHT_SEC : 2
    if (!flight || t > 1) {
      pulseFlights.delete(pulse.id)
      pulses.splice(i, 1)
      continue
    }
    const pos = samplePolyline(flight.points, t)
    pulse.position = [pos.x, pos.y, pos.z]
    pulse.opacity = 0.9 * Math.min(1, Math.min(t, 1 - t) * 6)
  }
}

// ── Floor grid: radial rings + spokes on the round platform ─────────────────
// Cyan-additive in the dark (a landing pad at night); soft warm gray lines in
// the light so the platform reads as engineered, not blank.

const gridGroupRef = shallowRef<THREE.Group | null>(null)
let gridMaterial: THREE.LineBasicMaterial | null = null

function rebuildFloorGrid() {
  const group = gridGroupRef.value
  if (!group) return
  for (const child of group.children) (child as THREE.LineSegments).geometry?.dispose()
  group.clear()
  gridMaterial?.dispose()
  gridMaterial = new THREE.LineBasicMaterial({
    color: palette.value.grid,
    transparent: true,
    opacity: isDark.value ? 0.5 : 0.55,
    blending: isDark.value ? THREE.AdditiveBlending : THREE.NormalBlending,
    depthWrite: false,
  })
  const { platformR } = layout.value
  const pts: THREE.Vector3[] = []
  // Concentric rings (as line segments so one geometry holds everything).
  const SEGMENTS = 96
  for (let r = 1.6; r < platformR - 0.45; r += 1.6) {
    for (let i = 0; i < SEGMENTS; i++) {
      const a0 = (i / SEGMENTS) * Math.PI * 2
      const a1 = ((i + 1) / SEGMENTS) * Math.PI * 2
      pts.push(
        new THREE.Vector3(r * Math.cos(a0), 0, r * Math.sin(a0)),
        new THREE.Vector3(r * Math.cos(a1), 0, r * Math.sin(a1)),
      )
    }
  }
  // Spokes.
  for (let i = 0; i < 16; i++) {
    const a = (i / 16) * Math.PI * 2
    pts.push(
      new THREE.Vector3(1.6 * Math.cos(a), 0, 1.6 * Math.sin(a)),
      new THREE.Vector3((platformR - 0.45) * Math.cos(a), 0, (platformR - 0.45) * Math.sin(a)),
    )
  }
  const geo = new THREE.BufferGeometry().setFromPoints(pts)
  group.add(new THREE.LineSegments(geo, gridMaterial))
}

// ── Camera, labels, clock ───────────────────────────────────────────────────

const cameraRef = shallowRef<THREE.PerspectiveCamera | null>(null)
const overlayRef = shallowRef<HTMLElement | null>(null)
const labelEls = new Map<string, HTMLElement>()
const setLabelEl = (id: string, el: unknown) => {
  if (el instanceof HTMLElement) labelEls.set(id, el)
  else labelEls.delete(id)
}

const LABEL_Y: Record<string, number> = { tower: 2.1, slab: 1.5, box: 1.7, satellite: 2.15 }

const cameraPosition = computed<[number, number, number]>(() => {
  const { platformR } = layout.value
  return [platformR * 0.52, platformR * 0.52, platformR + 6.2]
})

// Drives the unhealthy-module flicker in ClusterHostMachine.
const clock = ref(0)
let animFrame: number | null = null
const _projVec = new THREE.Vector3()

function projectTo(el: HTMLElement, x: number, y: number, z: number, w: number, h: number, cam: THREE.PerspectiveCamera) {
  _projVec.set(x, y, z).project(cam)
  const px = (_projVec.x * 0.5 + 0.5) * w
  const py = (-_projVec.y * 0.5 + 0.5) * h
  const visible = _projVec.z > -1 && _projVec.z < 1
  el.style.transform = `translate3d(${px.toFixed(1)}px, ${py.toFixed(1)}px, 0) translate(-50%, -100%)`
  el.style.opacity = visible ? '1' : '0'
}

function updateLabels() {
  const cam = cameraRef.value
  const overlay = overlayRef.value
  if (!cam || !overlay) return
  const w = overlay.clientWidth
  const h = overlay.clientHeight
  if (w === 0 || h === 0) return
  cam.updateMatrixWorld()
  for (const p of layout.value.placed) {
    const el = labelEls.get(p.host.id)
    if (!el) continue
    projectTo(el, p.position[0], LABEL_Y[p.host.formFactor] ?? 2.0, p.position[2], w, h, cam)
  }
}

onMounted(() => {
  if (!import.meta.client) return
  rebuildCables()
  rebuildFloorGrid()
  const start = performance.now()
  const tick = (now: number) => {
    clock.value = (now - start) / 1000
    if (props.snapshot.live?.collected_at) {
      liveAgeSeconds.value = Math.max(
        0,
        Math.round((Date.now() - new Date(props.snapshot.live.collected_at).getTime()) / 1000),
      )
    }
    tickPulses(clock.value)
    updateLabels()
    animFrame = requestAnimationFrame(tick)
  }
  animFrame = requestAnimationFrame(tick)
})

onBeforeUnmount(() => {
  if (animFrame !== null) cancelAnimationFrame(animFrame)
  if (import.meta.client) document.body.style.cursor = ''
  cableMaterial?.dispose()
  gridMaterial?.dispose()
})

// The Tres group refs populate after ClientOnly mounts the canvas — often
// AFTER this component's onMounted — so watch the refs themselves too, or a
// scene whose snapshot never changes (e.g. agent offline) gets no cables.
watch([cablesGroupRef, gridGroupRef, () => layout.value, isDark], () => {
  if (!import.meta.client) return
  rebuildCables()
  rebuildFloorGrid()
})

// ── Card + chip helpers ─────────────────────────────────────────────────────

const asInferenceType = (t: string) => t.toUpperCase() as InferenceType
const engineLabel = (e: string) => ENGINE_LABELS[e] ?? e
const gpuLabel = (h: SnapshotHost) => {
  if (!h.gpu) return null
  const parts = [
    VENDOR_LABELS[h.gpu.vendor ?? ''] ?? h.gpu.vendor,
    h.gpu.model?.replace(/-/g, ' '),
  ].filter(Boolean)
  let label = parts.join(' ') || 'GPU'
  if ((h.gpu.count ?? 1) > 1) label = `${h.gpu.count}× ${label}`
  if (h.gpu.vram_gb) label += ` · ${Math.round(h.gpu.vram_gb)} GB VRAM`
  return label
}
const badConditions = (h: SnapshotHost) =>
  (h.live?.conditions ?? []).filter(c =>
    c.type === 'Ready' ? c.status !== 'True' : c.status !== 'False',
  )

// What kind of thing this box is — the chip's one-word answer to "what am I
// looking at?".
const roleFor = (h: SnapshotHost): string => {
  if (h.external) return 'external'
  if (h.formFactor === 'slab') return 'DGX Spark'
  if (h.formFactor === 'tower') return 'GPU node'
  return 'node'
}

const ramFor = (h: SnapshotHost) => {
  const live = h.live
  if (!live || live.memory.allocatable_bytes <= 0) return null
  const pct = Math.min(100, Math.round((live.memory.usage_bytes / live.memory.allocatable_bytes) * 100))
  return {
    pct,
    text: `${formatBytes(live.memory.usage_bytes)} / ${formatBytes(live.memory.allocatable_bytes)}`,
  }
}

const statusDotClass = (h: SnapshotHost): string => {
  if (!h.live) return 'bg-slate-400'
  return h.live.ready ? 'bg-emerald-500' : 'bg-red-500'
}

// V2 attribution: the scene credits its own generation requests — clicking a
// machine tells you which request made its chassis.
const assetCredit = (h: SnapshotHost) => clusterAssets.value.get(h.formFactor)?.entry ?? null

// Sparkline (V1): the service's last hour of request buckets as an SVG
// polyline, normalized into a 120×26 viewBox.
const sparklinePoints = (s: SnapshotService): string => {
  const buckets = s.activity?.buckets ?? []
  if (!buckets.length) return ''
  const max = Math.max(...buckets, 1)
  const w = 120
  const h = 26
  const step = w / Math.max(buckets.length - 1, 1)
  return buckets
    .map((v, i) => `${(i * step).toFixed(1)},${(h - 2 - (v / max) * (h - 4)).toFixed(1)}`)
    .join(' ')
}

// VRAM a service holds right now — summed from its pods' per-process totals
// (the vram-reporter breakdown). 0 when the reporter isn't deployed.
const serviceVramTotal = (s: SnapshotService): number =>
  (s.pods ?? []).reduce((sum, p) => sum + (p.gpu_vram_used_bytes ?? 0), 0)

const helpOpen = ref(false)
</script>

<template>
  <div class="relative h-full w-full overflow-hidden">
    <ClientOnly>
      <TresCanvas :alpha="true" :clear-alpha="0" @pointer-missed="clearSelection">
        <TresPerspectiveCamera
          ref="cameraRef"
          :position="cameraPosition"
          :look-at="[0, 0.6, 0]"
          :fov="33"
          :near="0.1"
          :far="300"
        />
        <OrbitControls
          :target="[0, 1.0, 0]"
          :enable-damping="true"
          :damping-factor="0.08"
          :min-distance="6"
          :max-distance="48"
          :max-polar-angle="1.45"
        />

        <!-- Renderer config + PMREM room environment (shadows, ACES, env map) -->
        <ClusterSceneEnvironment />

        <TresAmbientLight :intensity="isDark ? 0.22 : 0.4" :color="isDark ? '#aab5d8' : '#ffffff'" />
        <TresHemisphereLight v-if="isDark" :args="['#46598f', '#0b1020', 0.4]" />
        <TresHemisphereLight v-else :args="['#ffffff', '#c4c8d0', 0.35]" />
        <!-- Key light carries the shadows; ortho frustum hugs the platform -->
        <TresDirectionalLight
          :position="[10, 15, 7]"
          :intensity="isDark ? 1.0 : 1.6"
          :color="isDark ? '#bcd0ff' : '#ffffff'"
          cast-shadow
          :shadow-mapSize-width="2048"
          :shadow-mapSize-height="2048"
          :shadow-camera-left="-(layout.platformR + 3)"
          :shadow-camera-right="layout.platformR + 3"
          :shadow-camera-top="layout.platformR + 3"
          :shadow-camera-bottom="-(layout.platformR + 3)"
          :shadow-camera-near="1"
          :shadow-camera-far="45"
          :shadow-bias="-0.0006"
          :shadow-normal-bias="0.02"
        />
        <TresDirectionalLight :position="[-10, 8, -6]" :intensity="isDark ? 0.25 : 0.45" :color="isDark ? '#5a4cff' : '#dde6f2'" />
        <TresPointLight :position="[0, 6, 0]" :intensity="isDark ? 18 : 0" :distance="26" :decay="2" color="#38bdf8" />
        <!-- Dark-mode rim accents: cool cyan and violet washes from opposite corners -->
        <TresPointLight
          v-if="isDark"
          :position="[-layout.platformR - 1.5, 3.5, layout.platformR / 2]"
          :intensity="11"
          :distance="20"
          :decay="2"
          color="#22d3ee"
        />
        <TresPointLight
          v-if="isDark"
          :position="[layout.platformR + 1.5, 3.5, -layout.platformR / 2]"
          :intensity="11"
          :distance="20"
          :decay="2"
          color="#a855f7"
        />

        <!-- Round cluster platform: brushed deck + bevel skirt -->
        <TresMesh :position="[0, -0.15, 0]" receive-shadow>
          <TresCylinderGeometry :args="[layout.platformR, layout.platformR, 0.3, 96]" />
          <TresMeshStandardMaterial :color="palette.deck" :roughness="0.8" :metalness="0.25" :env-map-intensity="0.5" />
        </TresMesh>
        <TresMesh :position="[0, -0.34, 0]">
          <TresCylinderGeometry :args="[layout.platformR + 0.22, layout.platformR + 0.34, 0.14, 96]" />
          <TresMeshStandardMaterial :color="palette.deckBevel" :roughness="0.7" :metalness="0.35" />
        </TresMesh>

        <!-- Neon rims (dark): platform edge ring + a fainter inner halo -->
        <template v-if="isDark">
          <TresMesh :position="[0, 0.02, 0]" :rotation="[-Math.PI / 2, 0, 0]">
            <TresTorusGeometry :args="[layout.platformR - 0.06, 0.025, 8, 96]" />
            <TresMeshBasicMaterial color="#22d3ee" :transparent="true" :opacity="0.6" :blending="ADDITIVE" :depth-write="false" />
          </TresMesh>
          <TresMesh :position="[0, -0.31, 0]" :rotation="[-Math.PI / 2, 0, 0]">
            <TresTorusGeometry :args="[layout.platformR + 0.3, 0.02, 8, 96]" />
            <TresMeshBasicMaterial color="#7c3aed" :transparent="true" :opacity="0.35" :blending="ADDITIVE" :depth-write="false" />
          </TresMesh>
        </template>

        <!-- Soft ground shadow (light): grounds the platform on the page -->
        <TresMesh v-if="!isDark && glowTex" :position="[0, -0.42, 0]" :rotation="[-Math.PI / 2, 0, 0]">
          <TresPlaneGeometry :args="[layout.platformR * 3.1, layout.platformR * 3.1]" />
          <TresMeshBasicMaterial :map="glowTex" :color="palette.groundShadow" :transparent="true" :opacity="0.3" :depth-write="false" />
        </TresMesh>

        <!-- Radial floor grid (both modes, built at runtime) -->
        <TresGroup ref="gridGroupRef" :position="[0, 0.006, 0]" />

        <!-- Agent name in 3D relief, laid flat on the platform like a pad
             marking — between the hub and the fleet so it never occludes a
             machine from the default camera. -->
        <Suspense>
          <Text3D
            v-if="snapshot.agentName"
            font="/fonts/helvetiker_bold.typeface.json"
            :text="snapshot.agentName"
            :size="0.58"
            :height="0.05"
            :bevel-enabled="true"
            :bevel-thickness="0.01"
            :bevel-size="0.006"
            :bevel-segments="2"
            :curve-segments="6"
            center
            :position="[0, 0.04, -1.1]"
            :rotation="[-Math.PI / 2, 0, 0]"
          >
            <TresMeshStandardMaterial
              :color="palette.text3d"
              :emissive="isDark ? '#22d3ee' : '#000000'"
              :emissive-intensity="isDark ? 0.32 : 0"
              :metalness="0.45"
              :roughness="0.4"
            />
          </Text3D>
        </Suspense>

        <!-- Agent hub: the chrome toy jack — the inference.club mark — slowly
             spinning over a pedestal. Requests enter the cluster here. -->
        <TresGroup :position="layout.hub">
          <TresMesh :position="[0, 0.06, 0]" receive-shadow>
            <TresCylinderGeometry :args="[0.78, 0.92, 0.12, 36]" />
            <TresMeshStandardMaterial :color="palette.pedestal" :roughness="0.5" :metalness="0.5" />
          </TresMesh>
          <TresMesh :position="[0, 0.15, 0]">
            <TresCylinderGeometry :args="[0.55, 0.62, 0.07, 36]" />
            <TresMeshStandardMaterial
              :color="palette.pedestal"
              emissive="#22d3ee"
              :emissive-intensity="(isDark ? 0.45 : 0.22) + 0.15 * Math.sin(clock * 2.2)"
              :roughness="0.45"
              :metalness="0.4"
            />
          </TresMesh>
          <!-- Slow spin + a gentle bob: a toy mid-toss, frozen in play -->
          <TresGroup
            :position="[0, 0.95 + 0.05 * Math.sin(clock * 1.1), 0]"
            :rotation="[0, clock * 0.55, 0]"
            :scale="[0.62, 0.62, 0.62]"
          >
            <JackObjModel :rotation="[Math.PI / 2, 0, 0]" />
          </TresGroup>
          <!-- Precessing orbital ring: the hub is alive even when idle -->
          <TresMesh :position="[0, 0.95, 0]" :rotation="[Math.PI / 2 + 0.42, clock * 0.7, 0]">
            <TresTorusGeometry :args="[0.85, 0.018, 8, 64]" />
            <TresMeshBasicMaterial
              color="#22d3ee"
              :transparent="true"
              :opacity="isDark ? 0.8 : 0.55"
              :blending="isDark ? ADDITIVE : NORMAL"
              :depth-write="false"
            />
          </TresMesh>
          <TresSprite v-if="isDark && glowTex" :position="[0, 0.95, 0]" :scale="[2.2, 1.8, 1]">
            <TresSpriteMaterial
              :map="glowTex"
              color="#22d3ee"
              :transparent="true"
              :opacity="0.18 + 0.06 * Math.sin(clock * 2.2)"
              :blending="ADDITIVE"
              :depth-write="false"
            />
          </TresSprite>
        </TresGroup>

        <!-- Cables hub → machines (built at runtime) -->
        <TresGroup ref="cablesGroupRef" />

        <ClusterHostMachine
          v-for="p in layout.placed"
          :key="p.host.id"
          :host="p.host"
          :position="p.position"
          :rotation-y="p.rotationY"
          :clock="clock"
          :selected-key="selectedKey"
          :asset="clusterAssets.get(p.host.formFactor) ?? null"
          @select="onSelect"
          @hover="(h: boolean) => onHostHover(p.host.id, h)"
        />

        <!-- Request pulses: live traffic flowing hub → machine. Additive in
             the dark (would clamp to white over a light background). -->
        <TresMesh v-for="pulse in pulses" :key="pulse.id" :position="pulse.position">
          <TresSphereGeometry :args="[0.13, 12, 10]" />
          <TresMeshBasicMaterial
            :color="pulse.color"
            :transparent="true"
            :opacity="pulse.opacity"
            :blending="isDark ? ADDITIVE : NORMAL"
            :depth-write="false"
          />
        </TresMesh>
      </TresCanvas>

      <!-- Projected overlay: host info chips + hub tag, repositioned per frame -->
      <div ref="overlayRef" class="absolute inset-0 pointer-events-none select-none">
        <div
          v-for="p in layout.placed"
          :key="p.host.id"
          :ref="el => setLabelEl(p.host.id, el)"
          class="absolute top-0 left-0 will-change-transform"
          @mouseenter="onHostHover(p.host.id, true)"
          @mouseleave="onHostHover(p.host.id, false)"
        >
          <!-- Resting state: a bare nameplate. Full chip on hover/selection. -->
          <button
            v-if="!chipVisible(p.host)"
            class="pointer-events-auto flex items-center gap-1.5 whitespace-nowrap rounded-full bg-white/55 px-2 py-0.5 backdrop-blur-[2px] dark:bg-slate-950/45"
            @click="onSelect({ kind: 'host', host: p.host })"
          >
            <span class="inline-block size-1.5 rounded-full" :class="statusDotClass(p.host)" />
            <span class="font-mono text-[10.5px] font-semibold tracking-wide text-slate-700/90 dark:text-slate-200/90">
              {{ p.host.hostname || p.host.id }}
            </span>
            <span v-if="p.host.live && !p.host.live.ready" class="text-[8.5px] font-semibold uppercase tracking-widest text-red-500">
              down
            </span>
          </button>
          <button
            v-else
            class="pointer-events-auto block rounded-md border bg-white/85 border-slate-200/80 shadow-sm backdrop-blur-sm px-2 py-1 text-left transition-colors hover:border-slate-300 dark:bg-slate-950/70 dark:border-slate-700/60 dark:hover:border-slate-500"
            @click="onSelect({ kind: 'host', host: p.host })"
          >
            <span class="flex items-center gap-1.5 whitespace-nowrap leading-tight">
              <span class="inline-block size-1.5 rounded-full" :class="statusDotClass(p.host)" />
              <span class="font-mono text-[10.5px] font-bold tracking-wide text-slate-800 dark:text-slate-100">
                {{ p.host.hostname || p.host.id }}
              </span>
              <span
                class="text-[8.5px] font-medium uppercase tracking-widest"
                :class="p.host.live && !p.host.live.ready ? 'text-red-500' : 'text-slate-400 dark:text-slate-500'"
              >
                {{ p.host.live && !p.host.live.ready ? 'down' : roleFor(p.host) }}
              </span>
            </span>
            <span v-if="p.host.services.length" class="mt-0.5 flex max-w-40 flex-wrap items-center gap-x-1.5 gap-y-0 leading-tight">
              <span
                v-for="s in p.host.services"
                :key="s.name"
                class="inline-flex items-center gap-1 whitespace-nowrap font-mono text-[9px] text-slate-600 dark:text-slate-300"
              >
                <span class="inline-block size-1.5 rounded-sm" :style="{ backgroundColor: modalityHex(s.type) }" />
                {{ s.name }}
              </span>
            </span>
            <span v-if="ramFor(p.host)" class="mt-1 flex items-center gap-1.5 leading-none">
              <span class="h-[3px] w-14 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700/80">
                <span
                  class="block h-full rounded-full"
                  :class="ramFor(p.host)!.pct > 85 ? 'bg-amber-500' : 'bg-sky-500'"
                  :style="{ width: `${ramFor(p.host)!.pct}%` }"
                />
              </span>
              <span class="font-mono text-[8.5px] tabular-nums text-slate-500 dark:text-slate-400">
                {{ ramFor(p.host)!.text }}
              </span>
            </span>
          </button>
        </div>

        <!-- Status bar: agent + freshness + fleet roll-up -->
        <div class="absolute left-3 top-3 pointer-events-auto flex flex-wrap items-center gap-1.5">
          <div class="flex items-center gap-2 rounded-full bg-white/90 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-700 px-3 py-1.5 shadow-sm backdrop-blur-sm">
            <span
              class="inline-block size-2 rounded-full"
              :class="snapshot.live ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'"
            />
            <span class="text-xs font-mono text-slate-700 dark:text-slate-200">{{ snapshot.agentName }}</span>
            <span class="text-[10px] tracking-wider text-slate-500 dark:text-slate-400">
              <template v-if="snapshot.live">
                live{{ liveAgeSeconds != null ? ` · ${liveAgeSeconds}s ago` : '' }}{{ snapshot.live.metrics_available ? '' : ' · no metrics' }}
              </template>
              <template v-else>manifest only</template>
            </span>
          </div>
          <div class="flex items-center gap-2 rounded-full bg-white/90 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-700 px-3 py-1.5 shadow-sm backdrop-blur-sm text-[10px] font-mono tabular-nums text-slate-600 dark:text-slate-300">
            <template v-if="stats.nodesReady != null">
              <span :class="stats.nodesReady < stats.nodesTotal ? 'text-red-500 font-semibold' : ''">
                {{ stats.nodesReady }}/{{ stats.nodesTotal }} nodes
              </span>
              <span class="text-slate-300 dark:text-slate-600">·</span>
              <span :class="stats.podsRunning! < stats.podsTotal! ? 'text-amber-500 font-semibold' : ''">
                {{ stats.podsRunning }}/{{ stats.podsTotal }} pods
              </span>
              <span class="text-slate-300 dark:text-slate-600">·</span>
              <span>{{ formatBytes(stats.ram!.used) }} / {{ formatBytes(stats.ram!.alloc) }} RAM</span>
            </template>
            <template v-else>
              <span>{{ stats.nodesTotal }} hosts</span>
              <span class="text-slate-300 dark:text-slate-600">·</span>
              <span>{{ stats.services }} services</span>
            </template>
            <template v-if="stats.gpus">
              <span class="text-slate-300 dark:text-slate-600">·</span>
              <span>{{ stats.gpus }} GPU{{ stats.gpus > 1 ? 's' : '' }}</span>
            </template>
          </div>
        </div>

        <!-- Modality legend -->
        <div v-if="modalitiesPresent.length" class="absolute left-3 bottom-3 flex flex-wrap gap-1.5">
          <span
            v-for="m in modalitiesPresent"
            :key="m"
            class="inline-flex items-center gap-1.5 rounded-full bg-white/90 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-700 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-slate-600 dark:text-slate-300"
          >
            <span class="inline-block size-2 rounded-full" :style="{ backgroundColor: modalityHex(m) }" />
            {{ m }}
          </span>
        </div>

        <!-- How to read this -->
        <div class="absolute right-3 bottom-3 pointer-events-auto flex flex-col items-end gap-2">
          <div
            v-if="helpOpen"
            class="w-72 rounded-xl bg-white/95 dark:bg-slate-900/90 border border-slate-200 dark:border-slate-700 shadow-lg p-3.5 text-[12px] leading-relaxed text-slate-600 dark:text-slate-300"
          >
            <p class="font-semibold text-slate-800 dark:text-slate-100">How to read this</p>
            <ul class="mt-1.5 space-y-1">
              <li><span class="font-medium text-slate-800 dark:text-slate-200">The chrome jack</span> is the agent — the cluster's front door, where every request lands first.</li>
              <li><span class="font-medium text-slate-800 dark:text-slate-200">Boxes</span> are the machines: towers are GPU nodes, the gold slab is a DGX Spark, floating tiles are endpoints outside the cluster.</li>
              <li><span class="font-medium text-slate-800 dark:text-slate-200">Glowing cartridges</span> are services — color is the modality (see legend).</li>
              <li><span class="font-medium text-slate-800 dark:text-slate-200">Glass pillars</span> show node RAM; the bricks inside are pods, sized by memory.</li>
              <li><span class="font-medium text-slate-800 dark:text-slate-200">Dashed lines</span> tether every machine to the agent; moving dots are requests in flight.</li>
            </ul>
            <p class="mt-2 text-[11px] text-slate-400 dark:text-slate-500">drag to rotate · scroll to zoom · hover a machine for details, click to pin</p>
          </div>
          <button
            class="flex items-center gap-1.5 rounded-full bg-white/90 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-700 px-2.5 py-1.5 text-[11px] text-slate-500 dark:text-slate-400 shadow-sm hover:text-slate-800 dark:hover:text-slate-200"
            @click="helpOpen = !helpOpen"
          >
            <HelpCircle class="size-3.5" />
            {{ helpOpen ? 'close' : 'what am I looking at?' }}
          </button>
        </div>

        <!-- Selection card -->
        <div
          v-if="selection"
          class="absolute right-3 top-3 w-72 max-h-[calc(100%-1.5rem)] overflow-y-auto pointer-events-auto rounded-xl bg-white/95 dark:bg-slate-900/90 border border-slate-200 dark:border-slate-700 shadow-lg p-4 text-sm"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <p class="font-mono font-semibold text-slate-900 dark:text-white truncate">
                {{ selection.kind === 'host' ? (selection.host.hostname || selection.host.id) : selection.service?.name }}
              </p>
              <p class="text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400">
                {{ selection.kind === 'host' ? (selection.host.external ? 'external endpoint' : 'node') : 'service' }}
              </p>
            </div>
            <ModalityBadge v-if="selection.kind === 'service' && selection.service" :type="asInferenceType(selection.service.type)" />
            <button
              class="shrink-0 rounded-md px-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
              aria-label="Close"
              @click="clearSelection"
            >
              ✕
            </button>
          </div>

          <!-- Node card -->
          <dl v-if="selection.kind === 'host'" class="mt-3 space-y-1.5 text-[13px]">
            <div v-if="selection.host.address" class="flex justify-between gap-2">
              <dt class="text-slate-500 dark:text-slate-400">IP</dt>
              <dd class="font-mono text-slate-700 dark:text-slate-200">{{ selection.host.address }}</dd>
            </div>
            <div v-if="gpuLabel(selection.host)" class="flex justify-between gap-2">
              <dt class="text-slate-500 dark:text-slate-400">GPU</dt>
              <dd class="text-right text-slate-700 dark:text-slate-200">{{ gpuLabel(selection.host) }}</dd>
            </div>
            <template v-if="selection.host.live">
              <div v-if="selection.host.live.architecture" class="flex justify-between gap-2">
                <dt class="text-slate-500 dark:text-slate-400">Arch</dt>
                <dd class="font-mono text-slate-700 dark:text-slate-200">{{ selection.host.live.architecture }}</dd>
              </div>
              <div v-if="selection.host.live.kubelet_version" class="flex justify-between gap-2">
                <dt class="text-slate-500 dark:text-slate-400">Kubernetes</dt>
                <dd class="font-mono text-slate-700 dark:text-slate-200">{{ selection.host.live.kubelet_version }}</dd>
              </div>
              <div v-if="selection.host.live.os_image" class="flex justify-between gap-2">
                <dt class="text-slate-500 dark:text-slate-400">OS</dt>
                <dd class="text-right text-slate-700 dark:text-slate-200">{{ selection.host.live.os_image }}</dd>
              </div>
              <div class="flex justify-between gap-2">
                <dt class="text-slate-500 dark:text-slate-400">Memory</dt>
                <dd class="font-mono text-slate-700 dark:text-slate-200">
                  {{ formatBytes(selection.host.live.memory.usage_bytes) }} / {{ formatBytes(selection.host.live.memory.allocatable_bytes) }}
                </dd>
              </div>
              <div v-if="selection.host.live.gpu" class="flex justify-between gap-2">
                <dt class="text-slate-500 dark:text-slate-400">GPU memory</dt>
                <dd class="font-mono text-emerald-600 dark:text-emerald-400">
                  {{ formatBytes(selection.host.live.gpu.vram_used_bytes) }} / {{ formatBytes(selection.host.live.gpu.vram_total_bytes) }}
                  <span class="text-slate-400 dark:text-slate-500"> · {{ selection.host.live.gpu.util_percent }}% util</span>
                </dd>
              </div>
              <div v-if="badConditions(selection.host).length" class="pt-1">
                <dt class="text-red-500 font-medium">Conditions</dt>
                <dd>
                  <ul class="mt-0.5 space-y-0.5">
                    <li v-for="c in badConditions(selection.host)" :key="c.type" class="font-mono text-[12px] text-red-500">
                      {{ c.type }}={{ c.status }}<span v-if="c.reason" class="text-red-400"> ({{ c.reason }})</span>
                    </li>
                  </ul>
                </dd>
              </div>
            </template>
            <p v-if="selection.host.notes" class="pt-1 text-[12px] text-slate-500 dark:text-slate-400">
              {{ selection.host.notes }}
            </p>
            <div
              v-if="assetCredit(selection.host)"
              class="mt-2 border-t border-slate-200 dark:border-slate-700 pt-2 text-[11px] text-slate-500 dark:text-slate-400"
            >
              <p>
                Chassis{{ assetCredit(selection.host)?.label ? ` “${assetCredit(selection.host)?.label}”` : '' }}
                — generated by
                <span class="font-mono">{{ assetCredit(selection.host)?.model || 'inference.club' }}</span>
                <template v-if="assetCredit(selection.host)?.provider"> on {{ assetCredit(selection.host)?.provider }}</template>
                <template v-if="assetCredit(selection.host)?.seed != null">, seed {{ assetCredit(selection.host)?.seed }}</template>
              </p>
              <NuxtLink
                v-if="assetCredit(selection.host)?.href"
                :to="assetCredit(selection.host)!.href!"
                class="underline underline-offset-2 hover:text-slate-700 dark:hover:text-slate-200"
              >
                request #{{ assetCredit(selection.host)?.request_id }}
              </NuxtLink>
            </div>
          </dl>

          <!-- Service card -->
          <div v-else-if="selection.service" class="mt-3 space-y-2 text-[13px]">
            <div class="flex justify-between gap-2">
              <span class="text-slate-500 dark:text-slate-400">Engine</span>
              <span class="text-slate-700 dark:text-slate-200">{{ engineLabel(selection.service.engine) }}</span>
            </div>
            <div class="flex justify-between gap-2">
              <span class="text-slate-500 dark:text-slate-400">Node</span>
              <span class="font-mono text-slate-700 dark:text-slate-200">{{ selection.host.hostname || selection.host.id }}</span>
            </div>
            <div v-if="serviceVramTotal(selection.service)" class="flex justify-between gap-2">
              <span class="text-slate-500 dark:text-slate-400">GPU memory now</span>
              <span class="font-mono text-slate-700 dark:text-slate-200">{{ formatBytes(serviceVramTotal(selection.service)) }}</span>
            </div>
            <div v-if="selection.service.activity?.buckets?.length">
              <p class="text-slate-500 dark:text-slate-400">
                Requests · last hour
                <span class="font-mono text-slate-700 dark:text-slate-200">{{ selection.service.activity.total }}</span>
              </p>
              <svg viewBox="0 0 120 26" class="mt-1 h-7 w-full">
                <polyline
                  :points="sparklinePoints(selection.service)"
                  fill="none"
                  :stroke="modalityHex(selection.service.type)"
                  stroke-width="1.5"
                  stroke-linejoin="round"
                  stroke-linecap="round"
                />
              </svg>
            </div>
            <div v-if="selection.service.models.length">
              <p class="text-slate-500 dark:text-slate-400">Models</p>
              <ul class="mt-0.5 space-y-0.5">
                <li v-for="m in selection.service.models" :key="m" class="font-mono text-[12px] text-slate-700 dark:text-slate-200 break-all">
                  {{ m }}
                </li>
              </ul>
            </div>
            <div v-if="showCommands && selection.service.command">
              <p class="text-slate-500 dark:text-slate-400">Command</p>
              <pre class="mt-0.5 whitespace-pre-wrap break-all rounded-md bg-slate-100 dark:bg-slate-800 p-2 font-mono text-[11px] text-slate-700 dark:text-slate-200">{{ selection.service.command }}</pre>
            </div>
            <div v-if="selection.service.pods.length">
              <p class="text-slate-500 dark:text-slate-400">Pods</p>
              <ul class="mt-0.5 space-y-1">
                <li v-for="pod in selection.service.pods" :key="pod.name" class="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-1">
                  <p class="font-mono text-[11px] text-slate-700 dark:text-slate-200 break-all">{{ pod.name }}</p>
                  <p class="text-[11px]" :class="pod.phase === 'Running' && pod.ready ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500'">
                    {{ pod.phase }}<span v-if="pod.reason"> · {{ pod.reason }}</span>
                    <span v-if="pod.restarts" class="text-slate-500 dark:text-slate-400"> · {{ pod.restarts }} restarts</span>
                    <span v-if="pod.memory_usage_bytes" class="text-slate-500 dark:text-slate-400"> · {{ formatBytes(pod.memory_usage_bytes) }} RAM</span>
                    <span v-if="pod.gpu_vram_used_bytes" class="text-slate-500 dark:text-slate-400"> · {{ formatBytes(pod.gpu_vram_used_bytes) }} VRAM</span>
                  </p>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </ClientOnly>
  </div>
</template>
