<script setup lang="ts">
// The homepage's 3D explainer: a little neighbourhood of households, each
// with its own hardware and models, joined through one hub. It is driven by
// `step` (the parent's scroll position), not by a timeline of its own:
//
//   0  households bring the hardware
//   1  each machine serves some kinds of model
//   2  a request is routed to a machine that can do it, the result comes back
//   3  one household keeps its machine members-only; public results are shared
//   4  people, apps and agents all use the same address
//
// Plain three.js, loaded on demand (the parent mounts this only near the
// viewport). It renders only while on screen, caps the pixel ratio, uses no
// shadows or post-processing, and holds still for reduced-motion.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type * as T from 'three'
import { useTheme } from '@/composables/useTheme'

export type Modality = 'chat' | 'image' | 'music' | 'video' | 'speech' | 'listen'

const props = defineProps<{
  step: number
  labels: {
    hub: string
    gallery: string
    membersOnly: string
    households: [string, string, string, string]
    hardware: [string, string, string, string]
    requesters: [string, string, string]
    modalities: Record<Modality, string>
  }
  /** Real generated pictures shown in the scene (gallery wall, image results). */
  art?: string[]
}>()

const { isDark } = useTheme()
const host = ref<HTMLDivElement | null>(null)
const ready = ref(false)

// One hue per kind of model, matching the badges used across the app.
const HUE: Record<Modality, string> = {
  chat: '#38bdf8', image: '#fbbf24', music: '#e879f9', video: '#fb7185', speech: '#a78bfa', listen: '#2dd4bf',
}
// What each household's machine serves, and the model that does it today.
const SERVES: Array<Array<[Modality, string]>> = [
  [['image', 'FLUX'], ['video', 'LTX']],
  [['chat', 'Nemotron'], ['music', 'ACE-Step']],
  [['speech', 'Magpie'], ['listen', 'Nemotron ASR']],
  [['chat', 'Nemotron'], ['image', 'FLUX']],
]
const ISLANDS: Array<[number, number]> = [[-8.2, -2.6], [-2.8, -6.4], [2.8, -6.4], [8.2, -2.6]]
const REQUESTERS: Array<[number, number]> = [[-4.4, 6.2], [0, 7.4], [4.4, 6.2]]
const PRIVATE_ISLAND = 3

// Camera per step: [position, look-at].
const SHOTS: Array<[[number, number, number], [number, number, number]]> = [
  [[0, 15, 21], [0, 0.5, -2.4]],
  [[0, 9.5, 12.5], [0, 1.2, -4.4]],
  [[0, 16.5, 22.5], [0, 0.4, 0.6]],
  [[8.5, 9.5, 13.5], [3.4, 1.5, -3]],
  [[0, 12.5, 23], [0, 0.6, 2.6]],
]

let dispose: (() => void) | null = null

async function build() {
  const el = host.value
  if (!el) return
  const THREE: typeof T = await import('three')
  if (!host.value) return

  const dark = isDark.value
  const C = dark
    ? { slab: '#1b2136', slabEdge: '#2b3350', house: '#2f3857', roof: '#454f7a', tower: '#11141f', hub: '#f8fafc', text: '#e5e7eb', sub: '#94a3b8', chip: 'rgba(15,18,30,0.92)', line: '#3b4468', glow: 1 }
    : { slab: '#eceef6', slabEdge: '#cfd3e2', house: '#ffffff', roof: '#b9bfd4', tower: '#2a3042', hub: '#ffffff', text: '#0f172a', sub: '#64748b', chip: 'rgba(255,255,255,0.96)', line: '#c3c8d8', glow: 0.55 }

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, el.clientWidth < 640 ? 1.5 : 2))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  el.appendChild(renderer.domElement)
  renderer.domElement.style.cssText = 'display:block;width:100%;height:100%'

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 200)
  scene.add(new THREE.HemisphereLight('#ffffff', dark ? '#1a1f35' : '#cfd4e4', dark ? 1.5 : 2.2))
  const sun = new THREE.DirectionalLight('#ffffff', dark ? 1.3 : 1.6)
  sun.position.set(6, 12, 8)
  scene.add(sun)

  const trash: Array<{ dispose: () => void }> = []
  const keep = <X extends { dispose: () => void }>(x: X) => (trash.push(x), x)
  const mat = (color: string, extra: T.MeshStandardMaterialParameters = {}) =>
    keep(new THREE.MeshStandardMaterial({ color, roughness: 0.8, metalness: 0.05, transparent: true, ...extra }))

  // ── Drawing helpers: labels and chips are canvas textures on sprites ──────
  const glyph = (g: CanvasRenderingContext2D, m: Modality, x: number, y: number, s: number, color: string) => {
    g.save()
    g.translate(x, y)
    g.strokeStyle = g.fillStyle = color
    g.lineWidth = s * 0.12
    g.lineJoin = g.lineCap = 'round'
    const h = s / 2
    if (m === 'chat') {
      g.beginPath(); g.roundRect(-h, -h * 0.8, s, s * 0.7, s * 0.18); g.stroke()
      g.beginPath(); g.moveTo(-h * 0.4, h * 0.6); g.lineTo(-h * 0.7, h); g.lineTo(0, h * 0.6); g.fill()
    } else if (m === 'image') {
      g.beginPath(); g.roundRect(-h, -h * 0.8, s, s * 0.8, s * 0.12); g.stroke()
      g.beginPath(); g.moveTo(-h * 0.8, h * 0.6); g.lineTo(-h * 0.15, -h * 0.1); g.lineTo(h * 0.25, h * 0.35); g.lineTo(h * 0.5, h * 0.1); g.lineTo(h * 0.85, h * 0.6); g.stroke()
      g.beginPath(); g.arc(h * 0.45, -h * 0.35, s * 0.08, 0, 7); g.fill()
    } else if (m === 'music') {
      g.beginPath(); g.moveTo(-h * 0.3, h * 0.55); g.lineTo(-h * 0.3, -h * 0.7); g.lineTo(h * 0.6, -h * 0.9); g.lineTo(h * 0.6, h * 0.35); g.stroke()
      g.beginPath(); g.ellipse(-h * 0.55, h * 0.6, s * 0.16, s * 0.12, 0, 0, 7); g.fill()
      g.beginPath(); g.ellipse(h * 0.35, h * 0.4, s * 0.16, s * 0.12, 0, 0, 7); g.fill()
    } else if (m === 'video') {
      g.beginPath(); g.roundRect(-h, -h * 0.7, s, s * 0.7, s * 0.14); g.stroke()
      g.beginPath(); g.moveTo(-h * 0.25, -h * 0.4); g.lineTo(h * 0.4, 0); g.lineTo(-h * 0.25, h * 0.4); g.closePath(); g.fill()
    } else {
      // speech (out) and listen (in): a waveform, mirrored for listening.
      const bars = m === 'speech' ? [0.3, 0.7, 1, 0.55, 0.85, 0.35] : [0.35, 0.85, 0.55, 1, 0.7, 0.3]
      bars.forEach((b, i) => {
        const bx = -h + (i + 0.5) * (s / bars.length)
        g.beginPath(); g.moveTo(bx, -h * b * 0.85); g.lineTo(bx, h * b * 0.85); g.stroke()
      })
    }
    g.restore()
  }

  const sprite = (w: number, h: number, draw: (g: CanvasRenderingContext2D, W: number, H: number) => void, scale: number) => {
    const cv = document.createElement('canvas')
    const k = 2
    cv.width = w * k
    cv.height = h * k
    const g = cv.getContext('2d')!
    g.scale(k, k)
    draw(g, w, h)
    const tex = keep(new THREE.CanvasTexture(cv))
    tex.colorSpace = THREE.SRGBColorSpace
    tex.anisotropy = 4
    const sp = new THREE.Sprite(keep(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false })))
    sp.scale.set(scale, (scale * h) / w, 1)
    sp.renderOrder = 10
    return sp
  }
  const FONT = '"Inter", ui-sans-serif, system-ui, sans-serif'
  const fit = (g: CanvasRenderingContext2D, text: string, max: number, size: number, weight = 600) => {
    let s = size
    do { g.font = `${weight} ${s}px ${FONT}`; s -= 1 } while (g.measureText(text).width > max && s > 10)
  }
  const label = (title: string, sub = '', scale = 3.4) =>
    sprite(320, sub ? 84 : 52, (g, W, H) => {
      g.textAlign = 'center'
      g.textBaseline = 'middle'
      fit(g, title, W - 12, 30, 700)
      g.fillStyle = C.text
      g.fillText(title, W / 2, sub ? 26 : H / 2)
      if (sub) {
        fit(g, sub, W - 12, 21, 500)
        g.fillStyle = C.sub
        g.fillText(sub, W / 2, 62)
      }
    }, scale)
  const chip = (m: Modality, name: string) =>
    sprite(300, 76, (g, W, H) => {
      g.fillStyle = C.chip
      g.strokeStyle = HUE[m]
      g.lineWidth = 3
      g.beginPath(); g.roundRect(3, 3, W - 6, H - 6, 34); g.fill(); g.stroke()
      glyph(g, m, 44, H / 2, 34, HUE[m])
      g.textBaseline = 'middle'
      g.textAlign = 'left'
      fit(g, props.labels.modalities[m], W - 96, 25, 700)
      g.fillStyle = C.text
      g.fillText(props.labels.modalities[m], 76, 26)
      fit(g, name, W - 96, 19, 500)
      g.fillStyle = C.sub
      g.fillText(name, 76, 53)
    }, 2.5)
  const tile = (m: Modality) =>
    sprite(96, 96, (g, W, H) => {
      g.fillStyle = HUE[m]
      g.beginPath(); g.roundRect(4, 4, W - 8, H - 8, 22); g.fill()
      glyph(g, m, W / 2, H / 2, 46, '#0b1020')
    }, 0.8)

  const slabGeo = (w: number, d: number, r = 0.7, t = 0.32) => {
    const s = new THREE.Shape()
    const x = -w / 2
    const y = -d / 2
    s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r)
    s.lineTo(x + w, y + d - r); s.quadraticCurveTo(x + w, y + d, x + w - r, y + d)
    s.lineTo(x + r, y + d); s.quadraticCurveTo(x, y + d, x, y + d - r)
    s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y)
    const geo = keep(new THREE.ExtrudeGeometry(s, { depth: t, bevelEnabled: false, curveSegments: 6 }))
    geo.rotateX(-Math.PI / 2)
    return geo
  }
  const box = (w: number, h: number, d: number) => keep(new THREE.BoxGeometry(w, h, d))

  // ── Households ────────────────────────────────────────────────────────────
  type Island = { group: T.Group; chips: T.Sprite[]; strip: T.MeshStandardMaterial; tower: T.Vector3; dome?: T.Mesh; lock?: T.Sprite }
  const islands: Island[] = ISLANDS.map(([x, z], i) => {
    const group = new THREE.Group()
    group.position.set(x, 0, z)
    group.rotation.y = -x * 0.035
    const slab = new THREE.Mesh(slabGeo(4.6, 4.2), mat(C.slab))
    group.add(slab)
    const edge = new THREE.Mesh(slabGeo(4.8, 4.4, 0.8, 0.12), mat(C.slabEdge))
    edge.position.y = -0.13
    group.add(edge)

    // A house: body, pitched roof, one lit window.
    const tall = i === 2
    const body = new THREE.Mesh(box(tall ? 1.5 : 1.9, tall ? 2.3 : 1.2, 1.6), mat(C.house))
    body.position.set(-0.9, 0.32 + (tall ? 1.15 : 0.6), -0.5)
    group.add(body)
    if (!tall) {
      const roof = new THREE.Mesh(keep(new THREE.ConeGeometry(1.5, 0.8, 4)), mat(C.roof))
      roof.rotation.y = Math.PI / 4
      roof.scale.set(1, 1, 0.85)
      roof.position.set(-0.9, 0.32 + 1.6, -0.5)
      group.add(roof)
    }
    const win = new THREE.Mesh(box(0.42, 0.42, 0.04), mat('#fde68a', { emissive: '#fbbf24', emissiveIntensity: 1.4 * C.glow }))
    win.position.set(-0.9, 0.32 + (tall ? 1.5 : 0.65), 0.31)
    group.add(win)

    // Its hardware: one or two towers with a light strip that glows at work.
    const strip = mat('#22d3ee', { emissive: '#22d3ee', emissiveIntensity: 0.5 * C.glow })
    const count = i === 0 ? 2 : 1
    for (let n = 0; n < count; n++) {
      const tw = new THREE.Mesh(box(0.55, i === 1 ? 0.55 : 1.15, 0.95), mat(i === 1 ? '#c8a04a' : C.tower, { metalness: 0.3, roughness: 0.5 }))
      tw.position.set(0.9 + n * 0.75, 0.32 + (i === 1 ? 0.28 : 0.58), 0.55)
      group.add(tw)
      const st = new THREE.Mesh(box(0.08, i === 1 ? 0.3 : 0.8, 0.04), strip)
      st.position.set(tw.position.x, tw.position.y, 0.55 + 0.49)
      group.add(st)
    }

    const name = label(props.labels.households[i], props.labels.hardware[i], 3.3)
    name.position.set(0, 0.42, 2.9)
    group.add(name)

    const chips = SERVES[i].map(([m, model], n) => {
      const c = chip(m, model)
      c.position.set(0.2, 2.7 + n * 0.85 + (tall ? 0.7 : 0), 0.2)
      c.material.opacity = 0
      group.add(c)
      return c
    })
    scene.add(group)
    const tower = new THREE.Vector3(0.9, 1.4, 0.55).applyAxisAngle(new THREE.Vector3(0, 1, 0), group.rotation.y).add(group.position)
    const island: Island = { group, chips, strip, tower }

    if (i === PRIVATE_ISLAND) {
      // Members-only: a soft dome and a lock over the household.
      const dome = new THREE.Mesh(
        keep(new THREE.SphereGeometry(3.1, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2)),
        keep(new THREE.MeshBasicMaterial({ color: '#a78bfa', transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide })),
      )
      dome.position.y = 0.3
      group.add(dome)
      const lock = sprite(300, 64, (g, W, H) => {
        g.fillStyle = '#7c3aed'
        g.beginPath(); g.roundRect(2, 2, W - 4, H - 4, 30); g.fill()
        g.strokeStyle = g.fillStyle = '#ffffff'
        g.lineWidth = 4
        g.beginPath(); g.arc(38, 27, 9, Math.PI, 0); g.stroke()
        g.beginPath(); g.roundRect(25, 27, 26, 20, 5); g.fill()
        g.textBaseline = 'middle'
        fit(g, props.labels.membersOnly, W - 76, 24, 700)
        g.fillText(props.labels.membersOnly, 62, H / 2 + 1)
      }, 2.9)
      lock.position.set(0, 4.6, 0)
      lock.material.opacity = 0
      group.add(lock)
      island.dome = dome
      island.lock = lock
    }
    return island
  })

  // ── The hub: one address in front of everything ───────────────────────────
  const hub = new THREE.Group()
  const plinth = new THREE.Mesh(keep(new THREE.CylinderGeometry(1.5, 1.7, 0.36, 40)), mat(C.slab))
  plinth.position.y = 0.18
  hub.add(plinth)
  const coreMat = mat(dark ? '#a5b4fc' : '#6366f1', { emissive: '#6366f1', emissiveIntensity: 0.6 * C.glow, roughness: 0.35 })
  const core = new THREE.Mesh(keep(new THREE.IcosahedronGeometry(0.72, 0)), coreMat)
  core.position.y = 1.35
  hub.add(core)
  const ring = new THREE.Mesh(keep(new THREE.TorusGeometry(1.15, 0.035, 8, 60)), mat('#818cf8', { emissive: '#818cf8', emissiveIntensity: 0.9 * C.glow }))
  ring.rotation.x = Math.PI / 2
  ring.position.y = 1.35
  hub.add(ring)
  const hubLabel = label(props.labels.hub, '', 3.6)
  hubLabel.position.set(0, 0.5, 2.3)
  hub.add(hubLabel)
  scene.add(hub)
  const HUB = new THREE.Vector3(0, 1.35, 0)

  // Links from the hub to each household.
  const linkMat = keep(new THREE.LineBasicMaterial({ color: C.line, transparent: true, opacity: 0.9 }))
  const curve = (a: T.Vector3, b: T.Vector3, lift = 1.6) =>
    new THREE.QuadraticBezierCurve3(a, a.clone().lerp(b, 0.5).setY(Math.max(a.y, b.y) + lift), b)
  const links = islands.map((isl) => {
    const line = new THREE.Line(keep(new THREE.BufferGeometry().setFromPoints(curve(HUB, isl.tower, 1.2).getPoints(28))), linkMat)
    scene.add(line)
    return line
  })

  // ── Who asks: a person, an app, an agent ──────────────────────────────────
  const requesters = REQUESTERS.map(([x, z], i) => {
    const group = new THREE.Group()
    group.position.set(x, 0, z)
    const pad = new THREE.Mesh(slabGeo(2.2, 1.7, 0.5, 0.2), mat(C.slab))
    group.add(pad)
    const accent = ['#38bdf8', '#34d399', '#f472b6'][i]
    if (i === 0) {
      const phone = new THREE.Mesh(box(0.5, 0.9, 0.08), mat(C.tower))
      phone.position.set(0, 0.75, 0); phone.rotation.x = -0.35
      const scr = new THREE.Mesh(box(0.4, 0.76, 0.02), mat(accent, { emissive: accent, emissiveIntensity: 0.9 * C.glow }))
      scr.position.set(0, 0.76, 0.05); scr.rotation.x = -0.35
      group.add(phone, scr)
    } else if (i === 1) {
      const base = new THREE.Mesh(box(1.1, 0.06, 0.75), mat(C.tower))
      base.position.set(0, 0.26, 0.1)
      const lid = new THREE.Mesh(box(1.1, 0.72, 0.05), mat(C.tower))
      lid.position.set(0, 0.6, -0.3); lid.rotation.x = -0.25
      const scr = new THREE.Mesh(box(0.98, 0.6, 0.02), mat(accent, { emissive: accent, emissiveIntensity: 0.8 * C.glow }))
      scr.position.set(0, 0.6, -0.26); scr.rotation.x = -0.25
      group.add(base, lid, scr)
    } else {
      const bot = new THREE.Mesh(keep(new THREE.OctahedronGeometry(0.45, 0)), mat(accent, { emissive: accent, emissiveIntensity: 0.8 * C.glow, roughness: 0.3 }))
      bot.position.y = 0.95
      bot.userData.spin = true
      group.add(bot)
    }
    const l = label(props.labels.requesters[i], '', 3)
    l.position.set(0, 0.3, 1.5)
    group.add(l)
    scene.add(group)
    return { group, at: new THREE.Vector3(x, 0.9, z) }
  })

  // ── The gallery: public results, shown with real generated pictures ───────
  const gallery = new THREE.Group()
  gallery.position.set(0, 4.6, -3.2)
  const loader = new THREE.TextureLoader()
  const frames: T.MeshBasicMaterial[] = []
  ;(props.art ?? []).slice(0, 3).forEach((src, i) => {
    const m = keep(new THREE.MeshBasicMaterial({ color: '#ffffff', transparent: true, opacity: 0 }))
    loader.load(src, (tex) => { tex.colorSpace = THREE.SRGBColorSpace; m.map = keep(tex); m.needsUpdate = true })
    const p = new THREE.Mesh(keep(new THREE.PlaneGeometry(1.5, 1.5)), m)
    p.position.set((i - 1) * 1.7, 0, 0)
    gallery.add(p)
    frames.push(m)
  })
  const galleryLabel = label(props.labels.gallery, '', 3)
  galleryLabel.position.set(0, 1.25, 0)
  galleryLabel.material.opacity = 0
  gallery.add(galleryLabel)
  scene.add(gallery)

  // ── Requests in flight ────────────────────────────────────────────────────
  // Every (household, modality) pair is a possible job; the private household
  // only takes jobs from the first requester (its owner).
  const JOBS: Array<{ island: number; m: Modality; from: number }> = []
  SERVES.forEach((list, island) => list.forEach(([m], n) => {
    JOBS.push({ island, m, from: island === PRIVATE_ISLAND ? 0 : (island + n) % 3 })
  }))
  const dotGeo = keep(new THREE.SphereGeometry(0.17, 16, 12))
  const flights = JOBS.map((job, i) => {
    const color = HUE[job.m]
    const dot = new THREE.Mesh(dotGeo, keep(new THREE.MeshBasicMaterial({ color, transparent: true })))
    const result = tile(job.m)
    dot.visible = result.visible = false
    scene.add(dot, result)
    const a = requesters[job.from].at
    const b = islands[job.island].tower
    return {
      ...job, dot, result, offset: i * 0.83,
      out1: curve(a, HUB, 1.4), out2: curve(HUB, b, 1.2), back1: curve(b, HUB, 1.2), back2: curve(HUB, a, 1.4),
      share: curve(b, gallery.position.clone().setY(4.2), 2.2),
    }
  })
  const PERIOD = JOBS.length * 0.83

  // ── Frame loop ────────────────────────────────────────────────────────────
  const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const clock = new THREE.Clock()
  const camPos = new THREE.Vector3(...SHOTS[0][0])
  const camLook = new THREE.Vector3(...SHOTS[0][1])
  const tmpPos = new THREE.Vector3()
  const tmpLook = new THREE.Vector3()
  const pointer = { x: 0, y: 0 }
  const fade = { chips: 0, hub: 0, req: 0, flow: 0, priv: 0, gallery: 0, intro: 0 }
  const toward = (cur: number, target: number, rate: number) => cur + (target - cur) * rate
  let visible = true
  let raf = 0
  let aspect = 1

  const resize = () => {
    const w = el.clientWidth
    const h = el.clientHeight
    if (!w || !h) return
    aspect = w / h
    renderer.setSize(w, h, false)
    camera.aspect = aspect
    camera.updateProjectionMatrix()
  }

  const frame = () => {
    raf = 0
    if (!visible) return
    const dt = Math.min(clock.getDelta(), 0.05)
    const t = still ? 6 : clock.elapsedTime
    const step = Math.max(0, Math.min(SHOTS.length - 1, props.step))
    const k = still ? 1 : 1 - Math.exp(-dt * 3.2)

    fade.intro = toward(fade.intro, 1, still ? 1 : 1 - Math.exp(-dt * 1.6))
    fade.chips = toward(fade.chips, step >= 1 ? 1 : 0, k)
    fade.hub = toward(fade.hub, step >= 2 ? 1 : 0.35, k)
    fade.req = toward(fade.req, step >= 2 ? 1 : 0, k)
    fade.flow = toward(fade.flow, step >= 2 ? 1 : 0, k)
    fade.priv = toward(fade.priv, step >= 3 ? 1 : 0, k)
    fade.gallery = toward(fade.gallery, step >= 3 ? 1 : 0, k)

    // Camera: ease to the step's shot, pulled back on narrow screens so the
    // whole neighbourhood stays in frame.
    const [p, l] = SHOTS[step]
    const pull = Math.min(2.6, Math.max(0.92, 1.45 / aspect))
    tmpLook.set(l[0], l[1], l[2])
    tmpPos.set(p[0], p[1], p[2]).sub(tmpLook).multiplyScalar(pull).add(tmpLook)
    if (aspect < 0.9 && step === 3) tmpPos.x *= 0.7
    camPos.lerp(tmpPos, k)
    camLook.lerp(tmpLook, k)
    camera.position.copy(camPos)
    camera.position.x += pointer.x * 0.9 + (still ? 0 : Math.sin(t * 0.25) * 0.5)
    camera.position.y += pointer.y * 0.5
    camera.lookAt(camLook)

    islands.forEach((isl, i) => {
      // Rise in one after another on first view.
      const rise = Math.min(1, Math.max(0, fade.intro * 1.6 - i * 0.15))
      isl.group.position.y = (1 - rise) * -1.5
      isl.group.scale.setScalar(0.85 + rise * 0.15)
      isl.chips.forEach((c, n) => {
        c.material.opacity = fade.chips
        c.position.y += still ? 0 : Math.sin(t * 1.3 + i + n) * 0.0012
      })
      isl.strip.emissiveIntensity = toward(isl.strip.emissiveIntensity, 0.5 * C.glow, 0.08)
      if (isl.dome) {
        ;(isl.dome.material as T.MeshBasicMaterial).opacity = fade.priv * (dark ? 0.16 : 0.2)
        isl.lock!.material.opacity = fade.priv
      }
    })
    links.forEach((ln) => { ln.visible = fade.hub > 0.4 })
    linkMat.opacity = Math.max(0, (fade.hub - 0.35) / 0.65) * 0.9
    hub.scale.setScalar(0.8 + fade.hub * 0.2)
    coreMat.emissiveIntensity = (0.25 + fade.hub * 0.6) * C.glow
    hubLabel.material.opacity = Math.max(0.5, fade.hub)
    if (!still) { core.rotation.y = t * 0.6; core.rotation.x = t * 0.25; ring.rotation.z = t * 0.4 }
    requesters.forEach((r, i) => {
      r.group.position.y = (1 - fade.req) * -1.2
      r.group.visible = fade.req > 0.02
      const emphasis = step === 4 ? 1 + (still ? 0 : Math.sin(t * 2 + i * 2.1) * 0.04) + 0.12 : 1
      r.group.scale.setScalar(emphasis)
      r.group.children.forEach((c) => { if (c.userData.spin && !still) c.rotation.y = t * 0.9 })
    })
    frames.forEach((m, i) => { m.opacity = fade.gallery })
    galleryLabel.material.opacity = fade.gallery
    gallery.position.y = 4.6 + (still ? 0 : Math.sin(t * 0.7) * 0.08)

    // Each job: ask → hub → machine → (work) → hub → asker. From step 3 a
    // public result also floats up to the gallery.
    flights.forEach((f) => {
      const u = ((t + f.offset) % PERIOD) / 4.6
      const on = fade.flow > 0.5 && u < 1
      const isPrivate = f.island === PRIVATE_ISLAND && step >= 3
      f.dot.visible = on && u < 0.5
      f.result.visible = on && u >= 0.58
      if (!on) return
      ;(f.dot.material as T.MeshBasicMaterial).color.set(isPrivate ? '#c4b5fd' : HUE[f.m])
      if (u < 0.25) f.out1.getPoint(u / 0.25, f.dot.position)
      else if (u < 0.5) f.out2.getPoint((u - 0.25) / 0.25, f.dot.position)
      else if (u < 0.58) islands[f.island].strip.emissiveIntensity = 3 * C.glow
      else if (u < 0.79) f.back1.getPoint((u - 0.58) / 0.21, f.result.position)
      else f.back2.getPoint((u - 0.79) / 0.21, f.result.position)
      f.result.material.opacity = u > 0.94 ? (1 - u) / 0.06 : 1
    })

    renderer.render(scene, camera)
    if (!still) raf = requestAnimationFrame(frame)
  }
  const kick = () => { if (!raf && visible) raf = requestAnimationFrame(frame) }

  const ro = new ResizeObserver(() => { resize(); kick() })
  ro.observe(el)
  const io = new IntersectionObserver(([e]) => {
    visible = e.isIntersecting
    if (visible) { clock.getDelta(); kick() }
  }, { rootMargin: '100px' })
  io.observe(el)
  const onMove = (e: PointerEvent) => {
    if (e.pointerType !== 'mouse') return
    const r = el.getBoundingClientRect()
    pointer.x = ((e.clientX - r.left) / r.width - 0.5) * 2
    pointer.y = -((e.clientY - r.top) / r.height - 0.5) * 2
  }
  el.addEventListener('pointermove', onMove)
  const stopStep = watch(() => props.step, () => {
    // Reduced motion draws one frame per step instead of animating.
    if (still) { fade.intro = 1; for (let i = 0; i < 3; i++) frame() } else kick()
  })

  resize()
  if (still) { for (let i = 0; i < 3; i++) frame() } else kick()
  ready.value = true

  dispose = () => {
    cancelAnimationFrame(raf)
    stopStep()
    ro.disconnect()
    io.disconnect()
    el.removeEventListener('pointermove', onMove)
    trash.forEach((x) => x.dispose())
    renderer.dispose()
    renderer.domElement.remove()
  }
}

const rebuild = () => {
  dispose?.()
  dispose = null
  ready.value = false
  build()
}

onMounted(build)
// Colours and label text are baked into textures, so a theme or language
// change rebuilds the scene.
watch([isDark, () => props.labels], rebuild)
onBeforeUnmount(() => dispose?.())
</script>

<template>
  <div
    ref="host"
    class="size-full transition-opacity duration-700"
    :class="ready ? 'opacity-100' : 'opacity-0'"
    data-testid="club-scene"
    aria-hidden="true"
  />
</template>
