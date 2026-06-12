<script setup lang="ts">
// Living Cluster scene (PRD 07) — a walkable 3D rendering of a provider's
// Kubernetes fleet. Machines (ClusterHostMachine) stand on a floor, cabled to
// the agent hub; external endpoints float as tethered satellites. Live state
// (when present on the snapshot) drives memory volumes, pod health and
// degradation. Follows NetworkScene's TresJS patterns: declarative meshes,
// runtime-built polylines, HTML overlay labels projected per frame.
import { TresCanvas } from '@tresjs/core'
import { OrbitControls } from '@tresjs/cientos'
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as THREE from 'three'
import { useScenePalette } from '@/composables/useScenePalette'
import { ENGINE_LABELS, VENDOR_LABELS } from '@/composables/useManifest'
import {
  formatBytes,
  modalityHex,
  type ClusterSelection,
  type ClusterSnapshot,
  type SnapshotHost,
} from '@/composables/useClusterState'
import type { InferenceType } from '@/types'

const props = defineProps<{
  snapshot: ClusterSnapshot
  // Owner view shows exact pod commands; public view redacts them
  // (commands can leak paths/flags — PRD 07 open question, default redact).
  showCommands?: boolean
}>()

const { palette, isDark } = useScenePalette()

// ── Layout ──────────────────────────────────────────────────────────────────

const COL_SPACING = 5.5
const ROW_SPACING = 6.5
const MAX_COLS = 4

interface PlacedHost {
  host: SnapshotHost
  position: [number, number, number]
}

const layout = computed(() => {
  const internals = props.snapshot.hosts.filter(h => !h.external)
  const externals = props.snapshot.hosts.filter(h => h.external)
  const cols = Math.max(1, Math.min(MAX_COLS, internals.length))
  const rows = Math.max(1, Math.ceil(internals.length / MAX_COLS))

  const placed: PlacedHost[] = internals.map((host, i) => {
    const row = Math.floor(i / MAX_COLS)
    const inRow = row === rows - 1 ? internals.length - row * MAX_COLS : MAX_COLS
    const col = i % MAX_COLS
    return {
      host,
      position: [
        (col - (inRow - 1) / 2) * COL_SPACING,
        0,
        (row - (rows - 1) / 2) * ROW_SPACING,
      ] as [number, number, number],
    }
  })

  const floorW = cols * COL_SPACING + 4
  const floorD = rows * ROW_SPACING + 4
  // Satellites hover off the right edge of the cluster floor.
  externals.forEach((host, j) => {
    placed.push({ host, position: [floorW / 2 + 2.6 + (j % 2) * 1.2, 0, -2.5 + j * 3.2] })
  })

  const hub: [number, number, number] = [0, 0, floorD / 2 + 1.6]
  return { placed, floorW, floorD, hub }
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

// ── Runtime objects: cables from the agent hub to every machine ────────────

const cablesGroupRef = shallowRef<THREE.Group | null>(null)
let cableMaterial: THREE.LineDashedMaterial | null = null

function rebuildCables() {
  const group = cablesGroupRef.value
  if (!group) return
  for (const child of group.children) (child as THREE.Line).geometry?.dispose()
  group.clear()
  cableMaterial?.dispose()
  cableMaterial = new THREE.LineDashedMaterial({
    color: palette.value.linkTailscale,
    dashSize: 0.18,
    gapSize: 0.14,
    transparent: true,
    opacity: 0.65,
  })
  const { placed, hub } = layout.value
  const hubTop = new THREE.Vector3(hub[0], 0.7, hub[2])
  for (const p of placed) {
    const end = new THREE.Vector3(
      p.position[0],
      p.host.formFactor === 'satellite' ? 2.0 : 0.4,
      p.position[2],
    )
    const mid = new THREE.Vector3((hubTop.x + end.x) / 2, 0.1, (hubTop.z + end.z) / 2)
    const geo = new THREE.BufferGeometry().setFromPoints([hubTop, mid, end])
    const line = new THREE.Line(geo, cableMaterial)
    line.computeLineDistances()
    group.add(line)
  }
}

// ── Camera, labels, clock ───────────────────────────────────────────────────

const cameraRef = shallowRef<THREE.PerspectiveCamera | null>(null)
const overlayRef = shallowRef<HTMLElement | null>(null)
const labelEls = new Map<string, HTMLElement>()
const setLabelEl = (id: string, el: unknown) => {
  if (el instanceof HTMLElement) labelEls.set(id, el)
  else labelEls.delete(id)
}

const LABEL_Y: Record<string, number> = { tower: 3.1, slab: 1.7, box: 2.3, satellite: 3.0 }

// Drives the unhealthy-module flicker in ClusterHostMachine.
const clock = ref(0)
let animFrame: number | null = null
const _projVec = new THREE.Vector3()

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
    _projVec.set(p.position[0], LABEL_Y[p.host.formFactor] ?? 2.4, p.position[2]).project(cam)
    const x = (_projVec.x * 0.5 + 0.5) * w
    const y = (-_projVec.y * 0.5 + 0.5) * h
    const visible = _projVec.z > -1 && _projVec.z < 1
    el.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) translate(-50%, -100%)`
    el.style.opacity = visible ? '1' : '0'
  }
}

onMounted(() => {
  if (!import.meta.client) return
  rebuildCables()
  const start = performance.now()
  const tick = (now: number) => {
    clock.value = (now - start) / 1000
    if (props.snapshot.live?.collected_at) {
      liveAgeSeconds.value = Math.max(
        0,
        Math.round((Date.now() - new Date(props.snapshot.live.collected_at).getTime()) / 1000),
      )
    }
    updateLabels()
    animFrame = requestAnimationFrame(tick)
  }
  animFrame = requestAnimationFrame(tick)
})

onBeforeUnmount(() => {
  if (animFrame !== null) cancelAnimationFrame(animFrame)
  if (import.meta.client) document.body.style.cursor = ''
  cableMaterial?.dispose()
})

watch([() => layout.value, isDark], () => {
  if (import.meta.client) rebuildCables()
})

// ── Card helpers ────────────────────────────────────────────────────────────

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
</script>

<template>
  <div class="relative h-full w-full overflow-hidden">
    <ClientOnly>
      <TresCanvas :alpha="true" :clear-alpha="0" @pointer-missed="clearSelection">
        <TresPerspectiveCamera
          ref="cameraRef"
          :position="[13, 9, 17]"
          :look-at="[0, 1, 0]"
          :fov="32"
          :near="0.1"
          :far="300"
        />
        <OrbitControls
          :target="[0, 0.8, 0]"
          :enable-damping="true"
          :damping-factor="0.08"
          :min-distance="6"
          :max-distance="55"
          :max-polar-angle="1.45"
        />

        <TresAmbientLight :intensity="isDark ? 0.4 : 0.9" :color="isDark ? '#aab5d8' : '#ffffff'" />
        <TresDirectionalLight :position="[12, 16, 8]" :intensity="isDark ? 0.8 : 1.4" :color="isDark ? '#bcd0ff' : '#ffffff'" />
        <TresDirectionalLight :position="[-10, 8, -6]" :intensity="isDark ? 0.25 : 0.45" :color="isDark ? '#5a4cff' : '#ffe9c4'" />
        <TresPointLight :position="[0, 6, 0]" :intensity="isDark ? 16 : 0" :distance="24" :decay="2" color="#38bdf8" />

        <!-- Cluster floor -->
        <TresMesh :position="[0, -0.16, 0]" receive-shadow>
          <TresBoxGeometry :args="[layout.floorW, 0.3, layout.floorD]" />
          <TresMeshStandardMaterial :color="palette.floor" :roughness="0.95" />
        </TresMesh>

        <!-- Agent hub: where requests enter the cluster -->
        <TresGroup :position="layout.hub">
          <TresMesh :position="[0, 0.05, 0]">
            <TresCylinderGeometry :args="[0.9, 1.05, 0.1, 24]" />
            <TresMeshStandardMaterial :color="palette.floorBevel" :roughness="0.9" />
          </TresMesh>
          <TresMesh :position="[0, 0.45, 0]">
            <TresCylinderGeometry :args="[0.32, 0.4, 0.8, 18]" />
            <TresMeshStandardMaterial
              :color="palette.serverBody"
              emissive="#22d3ee"
              :emissive-intensity="isDark ? 0.9 + 0.35 * Math.sin(clock * 2.2) : 0.25 + 0.15 * Math.sin(clock * 2.2)"
              :roughness="0.4"
            />
          </TresMesh>
        </TresGroup>

        <!-- Cables hub → machines (built at runtime) -->
        <TresGroup ref="cablesGroupRef" />

        <ClusterHostMachine
          v-for="p in layout.placed"
          :key="p.host.id"
          :host="p.host"
          :position="p.position"
          :clock="clock"
          :selected-key="selectedKey"
          @select="onSelect"
        />
      </TresCanvas>

      <!-- Hostname labels, projected to screen space each frame -->
      <div ref="overlayRef" class="absolute inset-0 pointer-events-none select-none">
        <div
          v-for="p in layout.placed"
          :key="p.host.id"
          :ref="el => setLabelEl(p.host.id, el)"
          class="absolute top-0 left-0 will-change-transform whitespace-nowrap text-center"
        >
          <p class="text-[11px] font-bold tracking-widest font-mono text-slate-700 dark:text-slate-200">
            {{ p.host.hostname || p.host.id }}
          </p>
          <p v-if="p.host.live && !p.host.live.ready" class="text-[10px] font-semibold tracking-wider text-red-500">
            NOT READY
          </p>
          <p v-else-if="p.host.external" class="text-[10px] tracking-wider text-slate-500 dark:text-slate-400">
            EXTERNAL
          </p>
        </div>

        <!-- Status chip -->
        <div class="absolute left-3 top-3 pointer-events-auto">
          <div class="flex items-center gap-2 rounded-full bg-white/90 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-700 px-3 py-1.5 shadow-sm">
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

        <!-- Hint -->
        <div class="absolute pointer-events-none" style="left: 50%; bottom: 0.5rem; transform: translateX(-50%);">
          <p class="text-[10px] font-mono tracking-wider text-slate-500 dark:text-slate-400/70">
            drag to rotate · scroll to zoom · click a machine or module
          </p>
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
                    <span v-if="pod.memory_usage_bytes" class="text-slate-500 dark:text-slate-400"> · {{ formatBytes(pod.memory_usage_bytes) }}</span>
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
