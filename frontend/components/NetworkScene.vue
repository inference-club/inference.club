<script setup lang="ts">
import { TresCanvas } from '@tresjs/core'
import { OrbitControls } from '@tresjs/cientos'
import { computed, onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import * as THREE from 'three'
import { useTheme } from '@/composables/useTheme'

const { isDark } = useTheme()

// ────────────────────────────────────────────────────────────
// Palettes (reactive)
// ────────────────────────────────────────────────────────────

const palette = computed(() => isDark.value
  ? {
      floor: '#1c2238',
      floorBevel: '#161b2c',
      wall: '#232a45',
      roomAccent: '#2a324d',
      desk: '#5a4530',
      deskDark: '#3b2c1e',
      fabric: '#4a5468',
      fabricDark: '#2c3344',
      blanket: '#3a4054',
      pillow: '#cbd2e6',
      pc: '#0d1018',
      pcAccent: '#22d3ee',
      screenBezel: '#05060c',
      windowGlass: '#1e3a5f',
      pictureFrame: '#2a324d',
      pictureArt: '#4f6286',
      plantPot: '#3b2c1e',
      plantLeaves: '#4ea372',
      plantLeavesAlt: '#6ec79a',
      mug: '#2a3045',
      mugInside: '#1a1d2a',
      laptopBody: '#5a6478',
      serverBody: '#0d1018',
      serverSlot: '#181d28',
      serverAccent: '#22d3ee',
      logoWhite: '#f0f0fa',
      logoText: '#a5b4fc',
      pillFill: '#0f1525',
      pillBorder: '#3949a8',
      linkTailscale: '#22d3ee',
      linkApi: '#a855f7',
      pulseTail: '#67e8f9',
      pulseApi: '#c084fc',
      ground: '#0a0d18',
    }
  : {
      floor: '#e9e6df',
      floorBevel: '#cfcabf',
      wall: '#dcd8cf',
      roomAccent: '#cfcabf',
      desk: '#c9a079',
      deskDark: '#a07a55',
      fabric: '#94a3b8',
      fabricDark: '#475569',
      blanket: '#5b6677',
      pillow: '#e2e8f0',
      pc: '#1f2937',
      pcAccent: '#22d3ee',
      screenBezel: '#0b0b14',
      windowGlass: '#cfe7f1',
      pictureFrame: '#ffffff',
      pictureArt: '#94a3b8',
      plantPot: '#d4d0c5',
      plantLeaves: '#3f8f5f',
      plantLeavesAlt: '#4ea372',
      mug: '#ffffff',
      mugInside: '#3a2a1c',
      laptopBody: '#cbd0d6',
      serverBody: '#1f2329',
      serverSlot: '#3b424d',
      serverAccent: '#0ea5e9',
      logoWhite: '#fdfdfb',
      logoText: '#6366f1',
      pillFill: '#f6f4ee',
      pillBorder: '#cdc7b8',
      linkTailscale: '#06b6d4',
      linkApi: '#7c3aed',
      pulseTail: '#22d3ee',
      pulseApi: '#a855f7',
      ground: '#f5f3ec',
    })

const monitorScreenColor = computed(() => isDark.value ? '#000814' : '#0b0b14')
const monitorTextColor = computed(() => '#ffffff')
const monitorSubColor = computed(() => '#22c55e')
const laptopScreenColor = computed(() => isDark.value ? '#0b0218' : '#0b0b14')
const laptopTextColor = computed(() => isDark.value ? '#c084fc' : '#a855f7')
const laptopSubColor = computed(() => '#22d3ee')
const logoBgColor = computed(() => isDark.value ? '#0a0a16' : '#ffffff')
const logoFgColor = computed(() => isDark.value ? '#a5b4fc' : '#6366f1')

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

const HOME_ANCHOR = new THREE.Vector3(-7.5, 0.6, 2.0)
const SERVER_ANCHOR = new THREE.Vector3(0, 1.5, -1.4)
const REMOTE_ANCHOR = new THREE.Vector3(7.5, 0.9, 1.5)

const TAILNET_PILL_POS = new THREE.Vector3(-3.6, 0.05, 4.5)
const API_PILL_POS = new THREE.Vector3(3.6, 0.05, 4.5)

const tailscalePath = [HOME_ANCHOR, TAILNET_PILL_POS, SERVER_ANCHOR]
const apiPath = [REMOTE_ANCHOR, API_PILL_POS, SERVER_ANCHOR]

// ────────────────────────────────────────────────────────────
// Refs / runtime objects
// ────────────────────────────────────────────────────────────

const linksGroupRef = shallowRef<THREE.Group | null>(null)
const pulsesGroupRef = shallowRef<THREE.Group | null>(null)
const monitorTex = shallowRef<THREE.CanvasTexture | null>(null)
const laptopTex = shallowRef<THREE.CanvasTexture | null>(null)
const logoTex = shallowRef<THREE.CanvasTexture | null>(null)

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
  { el: homeLabelRef.value, pos: new THREE.Vector3(-9.5, 4.6, 1.0) },
  { el: serverLabelRef.value, pos: new THREE.Vector3(0, 5.7, -2.5) },
  { el: serverBulletsRef.value, pos: new THREE.Vector3(0, 1.2, -0.8) },
  { el: remoteLabelRef.value, pos: new THREE.Vector3(9.5, 3.5, 1.0) },
  { el: tailnetLabelRef.value, pos: new THREE.Vector3(TAILNET_PILL_POS.x, 0.7, TAILNET_PILL_POS.z) },
  { el: apiLabelRef.value, pos: new THREE.Vector3(API_PILL_POS.x, 0.7, API_PILL_POS.z) },
  { el: localMachineRef.value, pos: new THREE.Vector3(-9.5, -0.6, 4.2) },
  { el: userDeviceRef.value, pos: new THREE.Vector3(9.5, -0.6, 4.2) },
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
// Texture builders (client-only)
// ────────────────────────────────────────────────────────────

function makeScreenTexture(opts: { primary: string; secondary: string; bg: string; fg: string; sub: string }) {
  const c = document.createElement('canvas')
  c.width = 512
  c.height = 320
  const ctx = c.getContext('2d')!
  ctx.fillStyle = opts.bg
  ctx.fillRect(0, 0, c.width, c.height)
  ctx.fillStyle = opts.fg
  ctx.font = 'bold 92px Inter, system-ui, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(opts.primary, c.width / 2, c.height / 2 - 28)
  ctx.fillStyle = opts.sub
  ctx.font = 'bold 28px Inter, system-ui, sans-serif'
  ctx.fillText(opts.secondary, c.width / 2, c.height / 2 + 56)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 8
  return tex
}

function makeLogoTexture(bg: string, fg: string) {
  const c = document.createElement('canvas')
  c.width = 256
  c.height = 256
  const ctx = c.getContext('2d')!
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, c.width, c.height)
  ctx.fillStyle = fg
  ctx.font = 'bold 38px Inter, system-ui, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText('inference', c.width / 2, c.height / 2 - 18)
  ctx.fillText('.club', c.width / 2, c.height / 2 + 22)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

function rebuildTextures() {
  monitorTex.value?.dispose()
  laptopTex.value?.dispose()
  logoTex.value?.dispose()
  monitorTex.value = makeScreenTexture({
    primary: 'vLLM',
    secondary: 'MODEL LOADED',
    bg: monitorScreenColor.value,
    fg: monitorTextColor.value,
    sub: monitorSubColor.value,
  })
  laptopTex.value = makeScreenTexture({
    primary: 'inference.club',
    secondary: 'CONNECTING...',
    bg: laptopScreenColor.value,
    fg: laptopTextColor.value,
    sub: laptopSubColor.value,
  })
  logoTex.value = makeLogoTexture(logoBgColor.value, logoFgColor.value)
}

// ────────────────────────────────────────────────────────────
// Mount: build runtime objects (lines + pulses) + animate
// ────────────────────────────────────────────────────────────

onMounted(() => {
  if (!import.meta.client) return
  rebuildTextures()

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

// React to theme changes — update line/pulse colors, rebuild screen textures
watch(isDark, () => {
  if (!import.meta.client) return
  rebuildTextures()
  if (dashTailMaterial) dashTailMaterial.color.set(palette.value.linkTailscale)
  if (dashApiMaterial) dashApiMaterial.color.set(palette.value.linkApi)
  for (let i = 0; i < pulseMaterials.length; i++) {
    pulseMaterials[i].color.set(i < 3 ? palette.value.pulseTail : palette.value.pulseApi)
  }
})

const HALF_PI = Math.PI / 2
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
        :position="[-9, 1.6, 1]"
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
        :position="[9, 1.4, 1]"
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

      <!-- ============================================================ -->
      <!-- HOME NETWORK (BEDROOM) — left platform                        -->
      <!-- ============================================================ -->
      <TresGroup :position="[-9, 0, 1]">
        <TresMesh :position="[0, -0.15, 0]">
          <TresBoxGeometry :args="[6, 0.3, 5]" />
          <TresMeshStandardMaterial :color="palette.floor" :roughness="0.85" />
        </TresMesh>

        <!-- Walls -->
        <TresMesh :position="[0, 1.55, -2.45]">
          <TresBoxGeometry :args="[6, 3.4, 0.15]" />
          <TresMeshStandardMaterial :color="palette.wall" :roughness="0.9" />
        </TresMesh>
        <TresMesh :position="[-2.95, 1.55, 0]">
          <TresBoxGeometry :args="[0.15, 3.4, 5]" />
          <TresMeshStandardMaterial :color="palette.wall" :roughness="0.9" />
        </TresMesh>

        <!-- Window -->
        <TresMesh :position="[1.4, 2.0, -2.36]">
          <TresBoxGeometry :args="[1.6, 1.2, 0.05]" />
          <TresMeshStandardMaterial :color="palette.pictureFrame" :roughness="0.6" />
        </TresMesh>
        <TresMesh :position="[1.4, 2.0, -2.34]">
          <TresBoxGeometry :args="[1.4, 1.0, 0.02]" />
          <TresMeshStandardMaterial
            :color="palette.windowGlass"
            :emissive="isDark ? '#3b6ea8' : '#000000'"
            :emissive-intensity="isDark ? 0.6 : 0"
          />
        </TresMesh>
        <!-- Picture -->
        <TresMesh :position="[-2.86, 2.1, 1.0]" :rotation="[0, HALF_PI, 0]">
          <TresBoxGeometry :args="[0.7, 0.55, 0.03]" />
          <TresMeshStandardMaterial :color="palette.pictureFrame" :roughness="0.5" />
        </TresMesh>
        <TresMesh :position="[-2.84, 2.1, 1.0]" :rotation="[0, HALF_PI, 0]">
          <TresBoxGeometry :args="[0.6, 0.45, 0.02]" />
          <TresMeshBasicMaterial :color="palette.pictureArt" />
        </TresMesh>

        <!-- Bed -->
        <TresGroup :position="[-1.6, 0, 1.3]">
          <TresMesh :position="[0, 0.18, 0]">
            <TresBoxGeometry :args="[1.6, 0.36, 2.4]" />
            <TresMeshStandardMaterial :color="palette.roomAccent" :roughness="0.8" />
          </TresMesh>
          <TresMesh :position="[0, 0.46, 0.15]">
            <TresBoxGeometry :args="[1.45, 0.22, 2.0]" />
            <TresMeshStandardMaterial :color="palette.blanket" :roughness="0.9" />
          </TresMesh>
          <TresMesh :position="[0, 0.62, -0.78]">
            <TresBoxGeometry :args="[1.2, 0.18, 0.45]" />
            <TresMeshStandardMaterial :color="palette.pillow" :roughness="0.95" />
          </TresMesh>
        </TresGroup>

        <!-- Desk -->
        <TresGroup :position="[1.0, 0, -1.0]">
          <TresMesh :position="[0, 1.0, 0]">
            <TresBoxGeometry :args="[2.6, 0.08, 1.2]" />
            <TresMeshStandardMaterial :color="palette.desk" :roughness="0.7" />
          </TresMesh>
          <TresMesh :position="[-1.2, 0.5, -0.5]">
            <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
            <TresMeshStandardMaterial :color="palette.deskDark" />
          </TresMesh>
          <TresMesh :position="[1.2, 0.5, -0.5]">
            <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
            <TresMeshStandardMaterial :color="palette.deskDark" />
          </TresMesh>
          <TresMesh :position="[-1.2, 0.5, 0.5]">
            <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
            <TresMeshStandardMaterial :color="palette.deskDark" />
          </TresMesh>
          <TresMesh :position="[1.2, 0.5, 0.5]">
            <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
            <TresMeshStandardMaterial :color="palette.deskDark" />
          </TresMesh>

          <!-- Monitor -->
          <TresMesh :position="[-0.5, 1.18, -0.45]">
            <TresBoxGeometry :args="[0.5, 0.05, 0.3]" />
            <TresMeshStandardMaterial :color="palette.screenBezel" />
          </TresMesh>
          <TresMesh :position="[-0.5, 1.4, -0.42]">
            <TresBoxGeometry :args="[0.06, 0.4, 0.06]" />
            <TresMeshStandardMaterial :color="palette.screenBezel" />
          </TresMesh>
          <TresGroup :position="[-0.5, 1.85, -0.4]" :rotation="[0.05, 0, 0]">
            <TresMesh :position="[0, 0, 0]">
              <TresBoxGeometry :args="[1.4, 0.85, 0.06]" />
              <TresMeshStandardMaterial :color="palette.screenBezel" :roughness="0.5" />
            </TresMesh>
            <TresMesh :position="[0, 0, 0.04]">
              <TresPlaneGeometry :args="[1.28, 0.74]" />
              <TresMeshBasicMaterial :map="monitorTex" :color="monitorTex ? '#ffffff' : '#22c55e'" />
            </TresMesh>
            <!-- Glow halo behind monitor in dark mode -->
            <TresMesh v-if="isDark" :position="[0, 0, -0.05]">
              <TresPlaneGeometry :args="[1.7, 1.1]" />
              <TresMeshBasicMaterial
                color="#22c55e"
                :transparent="true"
                :opacity="0.15"
                :blending="2"
                :depth-write="false"
              />
            </TresMesh>
          </TresGroup>

          <!-- PC tower -->
          <TresGroup :position="[1.0, 1.55, -0.35]">
            <TresMesh :position="[0, 0, 0]">
              <TresBoxGeometry :args="[0.55, 1.0, 0.55]" />
              <TresMeshStandardMaterial :color="palette.pc" :roughness="0.55" :metalness="0.2" />
            </TresMesh>
            <TresMesh :position="[0, -0.1, 0.276]">
              <TresPlaneGeometry :args="[0.42, 0.22]" />
              <TresMeshBasicMaterial :color="palette.pcAccent" />
            </TresMesh>
            <TresMesh :position="[-0.18, 0.4, 0.276]">
              <TresBoxGeometry :args="[0.06, 0.06, 0.005]" />
              <TresMeshBasicMaterial color="#22c55e" />
            </TresMesh>
            <TresMesh :position="[0.0, 0.4, 0.276]">
              <TresBoxGeometry :args="[0.06, 0.06, 0.005]" />
              <TresMeshBasicMaterial color="#a855f7" />
            </TresMesh>
          </TresGroup>
        </TresGroup>

        <!-- Office chair -->
        <TresGroup :position="[1.2, 0, 0.6]">
          <TresMesh :position="[0, 0.55, 0]">
            <TresBoxGeometry :args="[0.7, 0.08, 0.7]" />
            <TresMeshStandardMaterial :color="palette.fabricDark" :roughness="0.7" />
          </TresMesh>
          <TresMesh :position="[0, 0.95, 0.32]">
            <TresBoxGeometry :args="[0.65, 0.7, 0.08]" />
            <TresMeshStandardMaterial :color="palette.fabricDark" :roughness="0.7" />
          </TresMesh>
          <TresMesh :position="[0, 0.27, 0]">
            <TresCylinderGeometry :args="[0.05, 0.05, 0.5, 12]" />
            <TresMeshStandardMaterial color="#1f2937" />
          </TresMesh>
          <TresMesh :position="[0, 0.04, 0]">
            <TresCylinderGeometry :args="[0.4, 0.4, 0.05, 16]" />
            <TresMeshStandardMaterial color="#1f2937" />
          </TresMesh>
        </TresGroup>
      </TresGroup>

      <!-- ============================================================ -->
      <!-- CENTRAL SERVER                                                -->
      <!-- ============================================================ -->
      <TresGroup :position="[0, 2.4, -2.5]">
        <TresMesh :position="[0, -0.15, 0]">
          <TresBoxGeometry :args="[3.6, 0.3, 3.0]" />
          <TresMeshStandardMaterial :color="palette.floor" :roughness="0.85" />
        </TresMesh>
        <TresMesh :position="[0, -0.32, 0]">
          <TresBoxGeometry :args="[3.4, 0.05, 2.8]" />
          <TresMeshStandardMaterial :color="palette.floorBevel" :roughness="0.85" />
        </TresMesh>

        <TresGroup :position="[-0.45, 0, -0.1]">
          <TresMesh :position="[0, 0.85, 0]">
            <TresBoxGeometry :args="[1.3, 1.7, 1.2]" />
            <TresMeshStandardMaterial :color="palette.serverBody" :roughness="0.4" :metalness="0.3" />
          </TresMesh>
          <TresMesh
            v-for="i in 4"
            :key="`slot-${i}`"
            :position="[0, 0.25 + i * 0.3, 0.61]"
          >
            <TresBoxGeometry :args="[1.1, 0.04, 0.02]" />
            <TresMeshStandardMaterial :color="palette.serverSlot" />
          </TresMesh>
          <TresMesh
            v-for="i in 4"
            :key="`led-${i}`"
            :position="[0.47, 0.25 + i * 0.3, 0.62]"
          >
            <TresBoxGeometry :args="[0.06, 0.06, 0.005]" />
            <TresMeshBasicMaterial :color="palette.serverAccent" />
          </TresMesh>
        </TresGroup>

        <TresGroup :position="[0.85, 0.55, 0.55]" :rotation="[0, -0.35, 0]">
          <TresMesh>
            <TresBoxGeometry :args="[0.95, 0.95, 0.95]" />
            <TresMeshStandardMaterial
              :color="palette.logoWhite"
              :roughness="0.55"
              :emissive="isDark ? '#6366f1' : '#000000'"
              :emissive-intensity="isDark ? 0.25 : 0"
            />
          </TresMesh>
          <TresMesh :position="[0, 0, 0.476]">
            <TresPlaneGeometry :args="[0.85, 0.85]" />
            <TresMeshBasicMaterial :map="logoTex" :color="logoTex ? '#ffffff' : palette.logoText" />
          </TresMesh>
        </TresGroup>
      </TresGroup>

      <!-- ============================================================ -->
      <!-- REMOTE USER                                                   -->
      <!-- ============================================================ -->
      <TresGroup :position="[9, 0, 1]">
        <TresMesh :position="[0, -0.15, 0]">
          <TresBoxGeometry :args="[5, 0.3, 4]" />
          <TresMeshStandardMaterial :color="palette.floor" :roughness="0.85" />
        </TresMesh>

        <TresGroup :position="[0, 0, 0]">
          <TresMesh :position="[0, 1.05, 0]">
            <TresBoxGeometry :args="[3.0, 0.1, 1.6]" />
            <TresMeshStandardMaterial :color="palette.desk" :roughness="0.7" />
          </TresMesh>
          <TresMesh :position="[-1.4, 0.55, -0.7]">
            <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
            <TresMeshStandardMaterial color="#1f2937" />
          </TresMesh>
          <TresMesh :position="[1.4, 0.55, -0.7]">
            <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
            <TresMeshStandardMaterial color="#1f2937" />
          </TresMesh>
          <TresMesh :position="[-1.4, 0.55, 0.7]">
            <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
            <TresMeshStandardMaterial color="#1f2937" />
          </TresMesh>
          <TresMesh :position="[1.4, 0.55, 0.7]">
            <TresBoxGeometry :args="[0.08, 1.0, 0.08]" />
            <TresMeshStandardMaterial color="#1f2937" />
          </TresMesh>

          <!-- Laptop -->
          <TresGroup :position="[-0.2, 1.12, -0.05]">
            <TresMesh :position="[0, 0, 0]">
              <TresBoxGeometry :args="[1.3, 0.05, 0.9]" />
              <TresMeshStandardMaterial :color="palette.laptopBody" :roughness="0.4" :metalness="0.4" />
            </TresMesh>
            <TresMesh :position="[0, 0.026, 0.05]" :rotation="[-HALF_PI, 0, 0]">
              <TresPlaneGeometry :args="[1.1, 0.6]" />
              <TresMeshBasicMaterial color="#1f2937" />
            </TresMesh>
            <TresGroup :position="[0, 0.02, -0.45]" :rotation="[-0.35, 0, 0]">
              <TresMesh :position="[0, 0.45, 0]">
                <TresBoxGeometry :args="[1.3, 0.9, 0.05]" />
                <TresMeshStandardMaterial :color="palette.laptopBody" :roughness="0.4" :metalness="0.4" />
              </TresMesh>
              <TresMesh :position="[0, 0.45, 0.026]">
                <TresPlaneGeometry :args="[1.18, 0.78]" />
                <TresMeshBasicMaterial :map="laptopTex" :color="laptopTex ? '#ffffff' : palette.logoText" />
              </TresMesh>
              <TresMesh v-if="isDark" :position="[0, 0.45, -0.05]">
                <TresPlaneGeometry :args="[1.6, 1.1]" />
                <TresMeshBasicMaterial
                  color="#a855f7"
                  :transparent="true"
                  :opacity="0.18"
                  :blending="2"
                  :depth-write="false"
                />
              </TresMesh>
            </TresGroup>
          </TresGroup>

          <!-- Plant -->
          <TresGroup :position="[1.15, 1.1, 0.0]">
            <TresMesh :position="[0, 0.15, 0]">
              <TresCylinderGeometry :args="[0.18, 0.14, 0.3, 16]" />
              <TresMeshStandardMaterial :color="palette.plantPot" :roughness="0.85" />
            </TresMesh>
            <TresMesh :position="[0, 0.45, 0]">
              <TresIcosahedronGeometry :args="[0.28, 0]" />
              <TresMeshStandardMaterial :color="palette.plantLeaves" :roughness="0.8" />
            </TresMesh>
            <TresMesh :position="[0.15, 0.6, 0.05]">
              <TresIcosahedronGeometry :args="[0.18, 0]" />
              <TresMeshStandardMaterial :color="palette.plantLeavesAlt" :roughness="0.8" />
            </TresMesh>
          </TresGroup>

          <!-- Coffee mug -->
          <TresGroup :position="[1.1, 1.1, 0.55]">
            <TresMesh :position="[0, 0.13, 0]">
              <TresCylinderGeometry :args="[0.13, 0.12, 0.26, 18]" />
              <TresMeshStandardMaterial :color="palette.mug" :roughness="0.5" />
            </TresMesh>
            <TresMesh :position="[0, 0.255, 0]">
              <TresCylinderGeometry :args="[0.115, 0.115, 0.01, 18]" />
              <TresMeshBasicMaterial :color="palette.mugInside" />
            </TresMesh>
          </TresGroup>
        </TresGroup>

        <!-- Chair -->
        <TresGroup :position="[-0.2, 0, 1.4]">
          <TresMesh :position="[0, 0.55, 0]">
            <TresBoxGeometry :args="[0.8, 0.08, 0.7]" />
            <TresMeshStandardMaterial :color="palette.fabric" :roughness="0.7" />
          </TresMesh>
          <TresMesh :position="[0, 1.0, 0.34]">
            <TresBoxGeometry :args="[0.8, 0.85, 0.08]" />
            <TresMeshStandardMaterial :color="palette.fabric" :roughness="0.7" />
          </TresMesh>
          <TresMesh :position="[-0.32, 0.27, -0.3]">
            <TresBoxGeometry :args="[0.06, 0.55, 0.06]" />
            <TresMeshStandardMaterial color="#1f2937" />
          </TresMesh>
          <TresMesh :position="[0.32, 0.27, -0.3]">
            <TresBoxGeometry :args="[0.06, 0.55, 0.06]" />
            <TresMeshStandardMaterial color="#1f2937" />
          </TresMesh>
          <TresMesh :position="[-0.32, 0.27, 0.3]">
            <TresBoxGeometry :args="[0.06, 0.55, 0.06]" />
            <TresMeshStandardMaterial color="#1f2937" />
          </TresMesh>
          <TresMesh :position="[0.32, 0.27, 0.3]">
            <TresBoxGeometry :args="[0.06, 0.55, 0.06]" />
            <TresMeshStandardMaterial color="#1f2937" />
          </TresMesh>
        </TresGroup>
      </TresGroup>

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
