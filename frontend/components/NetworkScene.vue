<script setup lang="ts">
import { TresCanvas } from '@tresjs/core'
import { OrbitControls } from '@tresjs/cientos'
import { onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import * as THREE from 'three'
import { useScenePalette } from '@/composables/useScenePalette'

const { palette, isDark } = useScenePalette()

// ────────────────────────────────────────────────────────────
// Geometry helpers
// ────────────────────────────────────────────────────────────

function roundedRectShape(w: number, h: number, r: number) {
  const s = new THREE.Shape()
  const x = -w / 2
  const y = -h / 2
  s.moveTo(x + r, y)
  s.lineTo(x + w - r, y)
  s.quadraticCurveTo(x + w, y, x + w, y + r)
  s.lineTo(x + w, y + h - r)
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
  s.lineTo(x + r, y + h)
  s.quadraticCurveTo(x, y + h, x, y + h - r)
  s.lineTo(x, y + r)
  s.quadraticCurveTo(x, y, x + r, y)
  return s
}

function makePillGeometry(w: number, h: number, r: number, depth: number) {
  const geo = new THREE.ExtrudeGeometry(roundedRectShape(w, h, r), {
    depth,
    bevelEnabled: true,
    bevelThickness: 0.04,
    bevelSize: 0.04,
    bevelSegments: 2,
  })
  geo.rotateX(-Math.PI / 2)
  geo.translate(0, depth / 2, 0)
  return geo
}

const tailnetPillGeo = makePillGeometry(3.0, 1.2, 0.6, 0.2)
const apiPillGeo = makePillGeometry(3.6, 1.2, 0.6, 0.2)

// ────────────────────────────────────────────────────────────
// Connection paths (3D world coords)
// ────────────────────────────────────────────────────────────
//   Each path is a polyline of points.
//   - Home (bedroom) → Tailnet pill → Server  (tailscale tailnet)
//   - Remote (laptop) → API pill → Server     (api.inference.club/v1)

const HOME_ANCHOR = new THREE.Vector3(-6.0, 0.6, 2.0)
const SERVER_ANCHOR = new THREE.Vector3(0, 1.5, -1.4)
const REMOTE_ANCHOR = new THREE.Vector3(6.0, 0.9, 1.5)

const TAILNET_PILL_POS = new THREE.Vector3(-3.6, 0.05, 4.5)
const API_PILL_POS = new THREE.Vector3(3.6, 0.05, 4.5)

const tailscalePath = [HOME_ANCHOR, TAILNET_PILL_POS, SERVER_ANCHOR]
const apiPath = [REMOTE_ANCHOR, API_PILL_POS, SERVER_ANCHOR]

// ────────────────────────────────────────────────────────────
// Refs / runtime objects
// ────────────────────────────────────────────────────────────

const linksGroupRef = shallowRef<THREE.Group | null>(null)
const pulsesGroupRef = shallowRef<THREE.Group | null>(null)

// Materials we need to mutate when theme flips
let dashTailMaterial: THREE.LineDashedMaterial | null = null
let dashApiMaterial: THREE.LineDashedMaterial | null = null
const pulseMaterials: THREE.MeshBasicMaterial[] = []

let animFrame: number | null = null

// ────────────────────────────────────────────────────────────
// Camera + DOM-overlay refs (for billboard labels)
// ────────────────────────────────────────────────────────────

const cameraRef = shallowRef<THREE.PerspectiveCamera | null>(null)
const overlayRef = shallowRef<HTMLElement | null>(null)
const orbitWrapperRef = shallowRef<{ instance: { value: { target: THREE.Vector3; minDistance: number; maxDistance: number; update: () => void; domElement: HTMLElement } | null } } | null>(null)

const ZOOM_MIN = 8
const ZOOM_MAX = 60
let attachedCanvas: HTMLElement | null = null

function onCanvasWheel(e: WheelEvent) {
  const cam = cameraRef.value
  const ctrl = orbitWrapperRef.value?.instance?.value
  if (!cam || !ctrl) return

  const target = ctrl.target
  const offset = new THREE.Vector3().copy(cam.position).sub(target)
  const distance = offset.length()
  const minD = ctrl.minDistance ?? ZOOM_MIN
  const maxD = ctrl.maxDistance ?? ZOOM_MAX
  const eps = 0.01

  // wheel deltaY > 0 → page scrolls down → dolly OUT (away from target).
  // wheel deltaY < 0 → page scrolls up   → dolly IN  (toward target).
  // At a zoom limit *in the wheel direction*, do nothing — let the browser
  // scroll the page so the user isn't trapped on this section.
  if (e.deltaY > 0 && distance >= maxD - eps) return
  if (e.deltaY < 0 && distance <= minD + eps) return

  e.preventDefault()
  const factor = Math.exp(e.deltaY * 0.0015)
  const next = THREE.MathUtils.clamp(distance * factor, minD, maxD)
  offset.setLength(next)
  cam.position.copy(target).add(offset)
  ctrl.update()
}

const homeLabelRef = shallowRef<HTMLElement | null>(null)
const serverLabelRef = shallowRef<HTMLElement | null>(null)
const serverBulletsRef = shallowRef<HTMLElement | null>(null)
const remoteLabelRef = shallowRef<HTMLElement | null>(null)
const tailnetLabelRef = shallowRef<HTMLElement | null>(null)
const apiLabelRef = shallowRef<HTMLElement | null>(null)
const localMachineRef = shallowRef<HTMLElement | null>(null)
const userDeviceRef = shallowRef<HTMLElement | null>(null)

// World anchors — each label is glued to this 3D point and projected to screen
// pixel coords each frame, so it follows its scene part as the camera orbits.
const labelAnchors = (): Array<{ el: HTMLElement | null; pos: THREE.Vector3 }> => [
  { el: homeLabelRef.value, pos: new THREE.Vector3(-8.0, 4.6, 1.0) },
  { el: serverLabelRef.value, pos: new THREE.Vector3(0, 5.7, -2.5) },
  { el: serverBulletsRef.value, pos: new THREE.Vector3(0, 1.2, -0.8) },
  { el: remoteLabelRef.value, pos: new THREE.Vector3(8.0, 3.5, 1.0) },
  { el: tailnetLabelRef.value, pos: new THREE.Vector3(TAILNET_PILL_POS.x, 0.7, TAILNET_PILL_POS.z) },
  { el: apiLabelRef.value, pos: new THREE.Vector3(API_PILL_POS.x, 0.7, API_PILL_POS.z) },
  { el: localMachineRef.value, pos: new THREE.Vector3(-8.0, -0.6, 4.2) },
  { el: userDeviceRef.value, pos: new THREE.Vector3(8.0, -0.6, 4.2) },
]

const _projVec = new THREE.Vector3()

function updateLabelPositions() {
  const cam = cameraRef.value
  const overlay = overlayRef.value
  if (!cam || !overlay) return
  const w = overlay.clientWidth
  const h = overlay.clientHeight
  if (w === 0 || h === 0) return
  cam.updateMatrixWorld()
  for (const a of labelAnchors()) {
    if (!a.el) continue
    _projVec.copy(a.pos).project(cam)
    const x = (_projVec.x * 0.5 + 0.5) * w
    const y = (-_projVec.y * 0.5 + 0.5) * h
    const visible = _projVec.z > -1 && _projVec.z < 1
    a.el.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) translate(-50%, -50%)`
    a.el.style.opacity = visible ? '1' : '0'
  }
}

// ────────────────────────────────────────────────────────────
// Mount: build runtime objects (lines + pulses) + animate
// ────────────────────────────────────────────────────────────

onMounted(() => {
  if (!import.meta.client) return

  // Attach a custom wheel handler to the renderer canvas as soon as the
  // OrbitControls instance is available. Lets wheel events fall through to
  // page scroll when we're at a zoom limit instead of being trapped here.
  const stopOrbitWatch = watch(
    () => orbitWrapperRef.value?.instance?.value,
    (ctrl) => {
      if (!ctrl?.domElement || attachedCanvas) return
      attachedCanvas = ctrl.domElement
      attachedCanvas.addEventListener('wheel', onCanvasWheel, { passive: false })
      stopOrbitWatch()
    },
    { immediate: true },
  )

  // Build dashed lines (two polylines)
  if (linksGroupRef.value) {
    dashTailMaterial = new THREE.LineDashedMaterial({
      color: palette.value.linkTailscale,
      dashSize: 0.22,
      gapSize: 0.18,
      transparent: true,
      opacity: 0.95,
    })
    dashApiMaterial = new THREE.LineDashedMaterial({
      color: palette.value.linkApi,
      dashSize: 0.22,
      gapSize: 0.18,
      transparent: true,
      opacity: 0.95,
    })
    const tailGeo = new THREE.BufferGeometry().setFromPoints(tailscalePath)
    const tailLine = new THREE.Line(tailGeo, dashTailMaterial)
    tailLine.computeLineDistances()
    linksGroupRef.value.add(tailLine)

    const apiGeo = new THREE.BufferGeometry().setFromPoints(apiPath)
    const apiLine = new THREE.Line(apiGeo, dashApiMaterial)
    apiLine.computeLineDistances()
    linksGroupRef.value.add(apiLine)
  }

  // Build pulses (glowing spheres traveling along each polyline)
  type Pulse = {
    path: THREE.Vector3[]
    cumulative: number[]
    total: number
    speed: number
    offset: number
    direction: 1 | -1
    mesh: THREE.Mesh
  }
  const pulses: Pulse[] = []

  function buildCumulative(points: THREE.Vector3[]) {
    const cum = [0]
    for (let i = 1; i < points.length; i++) {
      cum.push(cum[i - 1] + points[i].distanceTo(points[i - 1]))
    }
    return { cumulative: cum, total: cum[cum.length - 1] }
  }

  function pointOnPath(points: THREE.Vector3[], cumulative: number[], total: number, t: number) {
    const dist = t * total
    for (let i = 1; i < points.length; i++) {
      if (dist <= cumulative[i]) {
        const segT = (dist - cumulative[i - 1]) / (cumulative[i] - cumulative[i - 1])
        return new THREE.Vector3().lerpVectors(points[i - 1], points[i], segT)
      }
    }
    return points[points.length - 1].clone()
  }

  if (pulsesGroupRef.value) {
    const tailMeta = buildCumulative(tailscalePath)
    const apiMeta = buildCumulative(apiPath)

    const configs: Array<{ path: THREE.Vector3[]; meta: { cumulative: number[]; total: number }; color: string; offset: number; direction: 1 | -1; speed: number }> = [
      { path: tailscalePath, meta: tailMeta, color: palette.value.pulseTail, offset: 0.0, direction: 1, speed: 0.32 },
      { path: tailscalePath, meta: tailMeta, color: palette.value.pulseTail, offset: 0.5, direction: 1, speed: 0.32 },
      { path: tailscalePath, meta: tailMeta, color: palette.value.pulseTail, offset: 0.25, direction: -1, speed: 0.28 },
      { path: apiPath, meta: apiMeta, color: palette.value.pulseApi, offset: 0.1, direction: 1, speed: 0.34 },
      { path: apiPath, meta: apiMeta, color: palette.value.pulseApi, offset: 0.6, direction: 1, speed: 0.34 },
      { path: apiPath, meta: apiMeta, color: palette.value.pulseApi, offset: 0.4, direction: -1, speed: 0.30 },
    ]

    for (const cfg of configs) {
      const mat = new THREE.MeshBasicMaterial({
        color: cfg.color,
        transparent: true,
        opacity: 0.95,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      })
      pulseMaterials.push(mat)
      const geo = new THREE.SphereGeometry(0.13, 16, 12)
      const mesh = new THREE.Mesh(geo, mat)
      pulsesGroupRef.value.add(mesh)
      pulses.push({
        path: cfg.path,
        cumulative: cfg.meta.cumulative,
        total: cfg.meta.total,
        speed: cfg.speed,
        offset: cfg.offset,
        direction: cfg.direction,
        mesh,
      })
    }

    let last = performance.now()
    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      for (const p of pulses) {
        p.offset = (p.offset + dt * p.speed * p.direction + 1) % 1
        const pos = pointOnPath(p.path, p.cumulative, p.total, p.offset)
        p.mesh.position.copy(pos)
      }
      updateLabelPositions()
      animFrame = requestAnimationFrame(tick)
    }
    animFrame = requestAnimationFrame(tick)
  } else {
    // Pulses group not present — still drive the label loop on its own.
    const tick = () => {
      updateLabelPositions()
      animFrame = requestAnimationFrame(tick)
    }
    animFrame = requestAnimationFrame(tick)
  }
})

onBeforeUnmount(() => {
  if (animFrame !== null) cancelAnimationFrame(animFrame)
  if (attachedCanvas) {
    attachedCanvas.removeEventListener('wheel', onCanvasWheel)
    attachedCanvas = null
  }
})

// React to theme changes — update line and pulse colors
// (per-component textures rebuild themselves via their own watchers).
watch(isDark, () => {
  if (!import.meta.client) return
  if (dashTailMaterial) dashTailMaterial.color.set(palette.value.linkTailscale)
  if (dashApiMaterial) dashApiMaterial.color.set(palette.value.linkApi)
  for (let i = 0; i < pulseMaterials.length; i++) {
    pulseMaterials[i].color.set(i < 3 ? palette.value.pulseTail : palette.value.pulseApi)
  }
})
</script>

<template>
  <ClientOnly>
    <TresCanvas :alpha="true" :clear-alpha="0">
      <TresPerspectiveCamera
        ref="cameraRef"
        :position="[18, 14, 18]"
        :look-at="[0, 1, 1]"
        :fov="26"
        :near="0.1"
        :far="200"
      />

      <OrbitControls
        ref="orbitWrapperRef"
        :target="[0, 1, 1]"
        :enable-damping="true"
        :damping-factor="0.08"
        :enable-pan="true"
        :enable-zoom="false"
        :enable-rotate="true"
        :min-distance="ZOOM_MIN"
        :max-distance="ZOOM_MAX"
      />

      <!-- Base lighting -->
      <TresAmbientLight :intensity="isDark ? 0.35 : 0.85" :color="isDark ? '#aab5d8' : '#ffffff'" />
      <TresDirectionalLight :position="[10, 14, 6]" :intensity="isDark ? 0.7 : 1.4" :color="isDark ? '#bcd0ff' : '#ffffff'" />
      <TresDirectionalLight :position="[-8, 6, -4]" :intensity="isDark ? 0.25 : 0.4" :color="isDark ? '#5a4cff' : '#ffe9c4'" />

      <!-- Dark-mode glow lights (no-op-ish in light mode via low intensity) -->
      <TresPointLight
        :position="[-7.5, 1.6, 1]"
        :intensity="isDark ? 14 : 0"
        :distance="8"
        :decay="2"
        color="#22d3ee"
      />
      <TresPointLight
        :position="[0, 2.6, -2.5]"
        :intensity="isDark ? 18 : 0"
        :distance="10"
        :decay="2"
        color="#a855f7"
      />
      <TresPointLight
        :position="[7.5, 1.4, 1]"
        :intensity="isDark ? 14 : 0"
        :distance="8"
        :decay="2"
        color="#c084fc"
      />
      <TresPointLight
        :position="[-3.6, 1.2, 4.5]"
        :intensity="isDark ? 6 : 0"
        :distance="6"
        :decay="2"
        color="#22d3ee"
      />
      <TresPointLight
        :position="[3.6, 1.2, 4.5]"
        :intensity="isDark ? 6 : 0"
        :distance="6"
        :decay="2"
        color="#a855f7"
      />

      <SceneHomeNetwork :position="[-7.5, 0, 1]" />

      <SceneCentralServer :position="[0, 2.4, -2.5]" />

      <SceneRemoteUser :position="[7.5, 0, 1]" />

      <!-- ============================================================ -->
      <!-- TAILNET pill (cyan)                                           -->
      <!-- ============================================================ -->
      <TresGroup :position="[TAILNET_PILL_POS.x, TAILNET_PILL_POS.y, TAILNET_PILL_POS.z]">
        <TresMesh :geometry="tailnetPillGeo">
          <TresMeshStandardMaterial
            :color="palette.pillFill"
            :roughness="0.55"
            :emissive="isDark ? '#0e3a4a' : '#000000'"
            :emissive-intensity="isDark ? 0.5 : 0"
          />
        </TresMesh>
      </TresGroup>

      <!-- ============================================================ -->
      <!-- API pill (purple)                                             -->
      <!-- ============================================================ -->
      <TresGroup :position="[API_PILL_POS.x, API_PILL_POS.y, API_PILL_POS.z]">
        <TresMesh :geometry="apiPillGeo">
          <TresMeshStandardMaterial
            :color="palette.pillFill"
            :roughness="0.55"
            :emissive="isDark ? '#3a1758' : '#000000'"
            :emissive-intensity="isDark ? 0.5 : 0"
          />
        </TresMesh>
      </TresGroup>

      <!-- Connection lines + travelling pulses (added at runtime) -->
      <TresGroup ref="linksGroupRef" />
      <TresGroup ref="pulsesGroupRef" />
    </TresCanvas>

    <!-- HTML LABEL OVERLAYS — anchored to 3D positions, projected each frame -->
    <div ref="overlayRef" class="absolute inset-0 pointer-events-none select-none">
      <!-- HOME NETWORK -->
      <div ref="homeLabelRef" class="absolute top-0 left-0 will-change-transform whitespace-nowrap text-center">
        <p class="text-[11px] font-bold tracking-widest text-slate-700 dark:text-slate-100">HOME NETWORK</p>
        <p class="text-[10px] tracking-wider text-slate-500 dark:text-slate-400">(BEDROOM)</p>
      </div>

      <!-- CENTRAL SERVER + inference.club -->
      <div ref="serverLabelRef" class="absolute top-0 left-0 will-change-transform whitespace-nowrap text-center">
        <h3 class="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-white">inference.club</h3>
        <p class="mt-1 text-[11px] font-bold tracking-widest text-indigo-500 dark:text-indigo-300">CENTRAL SERVER</p>
      </div>

      <!-- Server bullets -->
      <div ref="serverBulletsRef" class="absolute top-0 left-0 will-change-transform">
        <div class="rounded-xl bg-white/95 dark:bg-slate-900/80 border border-slate-200 dark:border-indigo-500/40 px-4 py-3 shadow-sm dark:shadow-indigo-500/20 whitespace-nowrap">
          <ul class="text-[12px] sm:text-sm text-slate-700 dark:text-slate-200 leading-6 space-y-0.5">
            <li>• Routing &amp; Discovery</li>
            <li>• Access Control</li>
            <li>• Coordination</li>
          </ul>
        </div>
      </div>

      <!-- REMOTE USER -->
      <div ref="remoteLabelRef" class="absolute top-0 left-0 will-change-transform whitespace-nowrap text-center">
        <p class="text-[11px] font-bold tracking-widest text-slate-700 dark:text-slate-100">REMOTE USER</p>
        <p class="text-[10px] tracking-wider text-slate-500 dark:text-slate-400">(ANYWHERE)</p>
      </div>

      <!-- TAILSCALE pill label -->
      <div ref="tailnetLabelRef" class="absolute top-0 left-0 will-change-transform">
        <div class="rounded-full bg-white/95 dark:bg-slate-900/80 border border-slate-200 dark:border-cyan-500/40 px-4 py-1.5 text-center shadow-sm dark:shadow-cyan-500/20 whitespace-nowrap">
          <p class="text-sm font-semibold text-slate-800 dark:text-cyan-200 leading-none">tailscale</p>
          <p class="mt-0.5 text-[10px] tracking-widest text-slate-500 dark:text-cyan-300/80">TAILNET</p>
        </div>
      </div>

      <!-- API pill label -->
      <div ref="apiLabelRef" class="absolute top-0 left-0 will-change-transform">
        <div class="rounded-full bg-white/95 dark:bg-slate-900/80 border border-slate-200 dark:border-fuchsia-500/40 px-4 py-1.5 text-center shadow-sm dark:shadow-fuchsia-500/20 whitespace-nowrap">
          <p class="text-sm font-semibold text-slate-800 dark:text-fuchsia-200 leading-none font-mono">api.inference.club/v1</p>
          <p class="mt-0.5 text-[10px] tracking-widest text-slate-500 dark:text-fuchsia-300/80">DATA PATH</p>
        </div>
      </div>

      <!-- LOCAL MACHINE info card -->
      <div ref="localMachineRef" class="absolute top-0 left-0 will-change-transform hidden md:block">
        <div class="rounded-xl bg-white/95 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-700 px-4 py-3 shadow-sm whitespace-nowrap">
          <p class="text-[11px] font-bold tracking-widest text-slate-700 dark:text-slate-200">LOCAL MACHINE</p>
          <ul class="mt-1.5 text-[12px] text-slate-600 dark:text-slate-300 leading-5">
            <li>• GPU (RTX 4090)</li>
            <li>• vLLM Inference Server</li>
          </ul>
        </div>
      </div>

      <!-- USER DEVICE info card -->
      <div ref="userDeviceRef" class="absolute top-0 left-0 will-change-transform hidden md:block">
        <div class="rounded-xl bg-white/95 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-700 px-4 py-3 shadow-sm whitespace-nowrap">
          <p class="text-[11px] font-bold tracking-widest text-slate-700 dark:text-slate-200">USER DEVICE</p>
          <ul class="mt-1.5 text-[12px] text-slate-600 dark:text-slate-300 leading-5">
            <li>• Browser / App</li>
            <li>• Connects via api.inference.club</li>
          </ul>
        </div>
      </div>

      <!-- Static hint (not anchored) -->
      <div class="absolute pointer-events-none" style="left: 50%; bottom: 1rem; transform: translateX(-50%);">
        <p class="text-[10px] font-mono tracking-wider text-slate-500 dark:text-slate-400/70">drag to rotate · scroll to zoom · right-drag to pan</p>
      </div>
    </div>
  </ClientOnly>
</template>
