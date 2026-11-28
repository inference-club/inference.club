// "Give and take": who asks, and whose machine answers.
//
// Seen from above. Around the outside are the callers: people (round) and
// agents (diamond). Nearer the middle are members' machines (squares, bigger
// for bigger GPUs). In the centre is the club, drawn as a ring, because every
// request passes through it. A request leaves a caller as a small light with
// a tail, in the colour of what was asked for; the club passes it to a
// machine, which lights up and spins while it works; and the answer travels
// back as a little picture of what it is (words, a picture, a voice, a tune,
// a film frame, a solid), landing with a ripple.
//
// One caller and one machine wear the same dashed halo: that member keeps
// their machine to themselves, and only their own requests go to it.

import type * as T from 'three'
import { easeBack, easeInOut, flatCamera, hash, ramp, seeded, sparks, type SceneFactory } from '../stage'
import { SIGNALS, roleColor, signalColor, type Signal } from '../theme'

export interface ExchangeOptions {
  callers?: number
  machines?: number
}

const R_CALLERS = 5.7
const R_MACHINES = 3.1
const R_HUB = 1
const FIT = 6.8 // world units from the centre that must stay in view
const JOBS = 14
const TRAIL = 16

// The stages of one request, as fractions of its life.
const OUT = 0.17
const ON = 0.34
const WORK = 0.56
const BACK = 0.73
const HOME = 0.9

/** Small white pictures of each kind of result, drawn once into one texture. */
function glyphs(THREE: typeof T, keep: <X extends { dispose(): void }>(x: X) => X): Record<Signal, T.Texture> {
  const S = 64
  const cv = document.createElement('canvas')
  cv.width = S * SIGNALS.length
  cv.height = S
  const g = cv.getContext('2d')!
  g.fillStyle = g.strokeStyle = '#fff'
  g.lineWidth = 5
  g.lineJoin = g.lineCap = 'round'
  const draw: Record<Signal, () => void> = {
    text: () => { [[14, 40], [28, 34], [42, 24]].forEach(([y, w]) => g.fillRect(12, y, w, 7)) },
    image: () => {
      g.strokeRect(11, 13, 42, 38)
      g.beginPath(); g.arc(24, 26, 4.5, 0, 7); g.fill()
      g.beginPath(); g.moveTo(14, 48); g.lineTo(30, 32); g.lineTo(38, 40); g.lineTo(44, 35); g.lineTo(50, 48); g.closePath(); g.fill()
    },
    speech: () => { [10, 22, 34, 20, 30, 12].forEach((h, i) => g.fillRect(11 + i * 7.6, 32 - h / 2, 4.5, h)) },
    music: () => {
      g.beginPath(); g.ellipse(22, 45, 8, 6, -0.4, 0, 7); g.fill()
      g.beginPath(); g.ellipse(44, 40, 8, 6, -0.4, 0, 7); g.fill()
      g.beginPath(); g.moveTo(29, 44); g.lineTo(29, 16); g.lineTo(51, 12); g.lineTo(51, 39); g.stroke()
    },
    video: () => {
      g.strokeRect(9, 15, 46, 34)
      g.beginPath(); g.moveTo(26, 23); g.lineTo(42, 32); g.lineTo(26, 41); g.closePath(); g.fill()
    },
    shape: () => {
      g.beginPath()
      g.moveTo(32, 9); g.lineTo(52, 20); g.lineTo(52, 44); g.lineTo(32, 55); g.lineTo(12, 44); g.lineTo(12, 20); g.closePath()
      g.moveTo(12, 20); g.lineTo(32, 31); g.lineTo(52, 20); g.moveTo(32, 31); g.lineTo(32, 55)
      g.stroke()
    },
  }
  const atlas = keep(new THREE.CanvasTexture(cv))
  const out = {} as Record<Signal, T.Texture>
  SIGNALS.forEach((s, i) => {
    g.save(); g.translate(i * S, 0); draw[s](); g.restore()
    const tex = keep(atlas.clone())
    tex.repeat.set(1 / SIGNALS.length, 1)
    tex.offset.set(i / SIGNALS.length, 0)
    out[s] = tex
  })
  atlas.needsUpdate = true
  SIGNALS.forEach((s) => { out[s].needsUpdate = true })
  return out
}

const exchange: SceneFactory<ExchangeOptions> = (ctx) => {
  const { THREE, palette: P, scene } = ctx
  const cam = flatCamera(ctx, FIT * 2)
  const rnd = seeded(21)
  const nCallers = ctx.options?.callers ?? 16
  const nMachines = ctx.options?.machines ?? 7
  const root = new THREE.Group()
  scene.add(root)
  const hue = Object.fromEntries(SIGNALS.map((s) => [s, new THREE.Color(signalColor(P, s))])) as Record<Signal, T.Color>
  const cPrivate = new THREE.Color(roleColor(P, 'private'))
  const cPerson = new THREE.Color(roleColor(P, 'person'))
  const cAgent = new THREE.Color(roleColor(P, 'agent'))
  const cMachine = new THREE.Color(roleColor(P, 'machine'))
  const cDim = new THREE.Color(P.dim)

  const line = (pts: T.Vector3[], color: string, opacity: number, dashed = false, parent: T.Object3D = root) => {
    const geo = ctx.keep(new THREE.BufferGeometry().setFromPoints(pts))
    const mat = dashed
      ? ctx.keep(new THREE.LineDashedMaterial({ color, transparent: true, opacity, dashSize: 0.16, gapSize: 0.13 }))
      : ctx.keep(new THREE.LineBasicMaterial({ color, transparent: true, opacity }))
    const l = new THREE.Line(geo, mat)
    if (dashed) l.computeLineDistances()
    parent.add(l)
    return l
  }
  const circle = (r: number, cx = 0, cy = 0, n = 96) =>
    Array.from({ length: n + 1 }, (_, i) => new THREE.Vector3(cx + Math.cos((i / n) * Math.PI * 2) * r, cy + Math.sin((i / n) * Math.PI * 2) * r, 0))

  // The club: a ring, a slowly turning dashed ring inside it, and guide rings.
  line(circle(R_HUB), P.ink, 0.95)
  const inner = line(circle(R_HUB * 0.72), P.dim, 0.9, true)
  const pulseRing = line(circle(R_HUB), P.amber, 0)
  line(circle(R_MACHINES), P.line, 0.7)
  line(circle(R_CALLERS), P.line, 0.5)
  const orbit = line(circle((R_MACHINES + R_CALLERS) / 2), P.line, 0.35, true)

  // Machines: an outlined square with fins, filled with light while working.
  const machines = Array.from({ length: nMachines }, (_, i) => {
    const a = (i / nMachines) * Math.PI * 2 + 0.4
    const size = 0.62 + rnd() * 0.55
    const x = Math.cos(a) * R_MACHINES
    const y = Math.sin(a) * R_MACHINES
    const h = size / 2
    const group = new THREE.Group()
    group.position.set(x, y, 0)
    root.add(group)
    line([[-h, -h], [h, -h], [h, h], [-h, h], [-h, -h]].map(([px, py]) => new THREE.Vector3(px, py, 0)), P.amber, 1, false, group)
    for (let f = -1; f <= 1; f++) {
      line([new THREE.Vector3(-h * 0.55, f * h * 0.42, 0), new THREE.Vector3(h * 0.55, f * h * 0.42, 0)], P.amber, 0.55, false, group)
    }
    const fill = new THREE.Mesh(ctx.keep(new THREE.PlaneGeometry(size, size)), ctx.glow(P.amber, 0))
    group.add(fill)
    return { x, y, size, group, fill: fill.material as T.MeshBasicMaterial, heat: 0, tint: cMachine }
  })

  // Callers: people are discs, agents are diamonds.
  const callers = Array.from({ length: nCallers }, (_, i) => {
    const a = (i / nCallers) * Math.PI * 2 + (rnd() - 0.5) * 0.14
    const r = R_CALLERS + (rnd() - 0.5) * 0.55
    const agent = i % 3 === 1
    const mesh = agent
      ? new THREE.Mesh(ctx.keep(new THREE.PlaneGeometry(0.34, 0.34)), ctx.glow(roleColor(P, 'agent'), 1))
      : new THREE.Mesh(ctx.keep(new THREE.CircleGeometry(0.2, 24)), ctx.glow(roleColor(P, 'person'), 1))
    if (agent) mesh.rotation.z = Math.PI / 4
    mesh.position.set(Math.cos(a) * r, Math.sin(a) * r, 0)
    root.add(mesh)
    return { x: mesh.position.x, y: mesh.position.y, agent, mesh, hit: 0 }
  })

  // The private pair: the same dashed halo on a caller and on their machine.
  const OWNER = 0
  const OWN_MACHINE = 0
  const haloA = line(circle(0.46, 0, 0, 40), roleColor(P, 'private'), 1, true)
  haloA.position.set(callers[OWNER].x, callers[OWNER].y, 0)
  const haloB = line(circle(machines[OWN_MACHINE].size * 0.98, 0, 0, 48), roleColor(P, 'private'), 1, true, machines[OWN_MACHINE].group)

  // Lights: one cloud for soft glows, one for crisp cores and tails.
  const PER = TRAIL + 6 // tail, head, 3 workers, ripple, spare
  const glow = sparks(ctx, JOBS * 3 + nCallers + nMachines + 8)
  const core = sparks(ctx, JOBS * PER + 8, { hard: 0.45 })
  root.add(glow.object, core.object)

  // The answers: one small picture per job.
  const icons = glyphs(THREE, ctx.keep)
  const jobs = Array.from({ length: JOBS }, (_, j) => {
    const mat = ctx.keep(new THREE.SpriteMaterial({ map: icons.text, transparent: true, depthWrite: false, depthTest: false }))
    const sprite = new THREE.Sprite(mat)
    sprite.visible = false
    sprite.renderOrder = 5
    root.add(sprite)
    return { sprite, mat, start: j * 0.53 - 2.5, length: 5.2 + rnd() * 1.6, shown: '' as Signal | '' }
  })

  // A request's position at fraction `u` of its life: caller → club → machine
  // (curving), wait, then the same way back.
  const at = { x: 0, y: 0 }
  const bezier = (ax: number, ay: number, bx: number, by: number, k: number, u: number) => {
    const cx = (ax + bx) / 2 - (by - ay) * k
    const cy = (ay + by) / 2 + (bx - ax) * k
    const v = 1 - u
    at.x = v * v * ax + 2 * v * u * cx + u * u * bx
    at.y = v * v * ay + 2 * v * u * cy + u * u * by
  }
  const where = (u: number, c: (typeof callers)[number], m: (typeof machines)[number], k: number) => {
    if (u < OUT) bezier(c.x, c.y, 0, 0, k, easeInOut(ramp(u, 0, OUT)))
    else if (u < ON) bezier(0, 0, m.x, m.y, -k, easeInOut(ramp(u, OUT, ON)))
    else if (u < WORK) { at.x = m.x; at.y = m.y }
    else if (u < BACK) bezier(m.x, m.y, 0, 0, k, easeInOut(ramp(u, WORK, BACK)))
    else bezier(0, 0, c.x, c.y, -k, easeInOut(ramp(u, BACK, HOME)))
  }
  const tmp = new THREE.Color()

  return {
    poster: 6.4,
    resize({ aspect }) {
      // Keep the whole ring in view on tall screens too.
      ;(cam.userData.fit as (a: number, h: number) => void)(aspect, aspect < 1 ? (FIT * 2) / aspect : FIT * 2)
    },
    update(t) {
      root.rotation.z = t * 0.025
      inner.rotation.z = -t * 0.35
      orbit.rotation.z = t * 0.05
      haloA.rotation.z = t * 0.4
      haloB.rotation.z = -t * 0.4
      machines.forEach((m) => { m.heat = 0 })
      callers.forEach((c) => { c.hit = 0 })
      let hub = 0
      let g = 0
      let k = 0

      jobs.forEach((job, j) => {
        const local = t - job.start
        const round = Math.floor(local / job.length)
        const u = (((local % job.length) + job.length) % job.length) / job.length
        // The owner's requests always go to their own machine; nobody else's do.
        const seed = j * 17.3 + round * 3.7
        const own = (((round + j) % 5) + 5) % 5 === 0
        const caller = callers[own ? OWNER : 1 + Math.floor(hash(seed) * (nCallers - 1))]
        const machine = machines[own ? OWN_MACHINE : 1 + Math.floor(hash(seed + 1) * (nMachines - 1))]
        const signal = SIGNALS[Math.floor(hash(seed + 2) * SIGNALS.length)]
        const colour = own ? cPrivate : hue[signal]
        const bend = (hash(seed + 3) - 0.5) * 0.6
        const returning = u >= WORK
        const working = u >= ON && u < WORK
        const moving = u < HOME && !working

        // Tail.
        for (let i = 0; i < TRAIL; i++) {
          const ui = u - (i + 1) * 0.004
          if (!moving || ui < 0 || (returning && ui < WORK) || (!returning && ui > ON)) { core.hide(k++); continue }
          where(ui, caller, machine, bend)
          const f = 1 - i / TRAIL
          core.set(k++, at.x, at.y, 0, colour, (returning ? 0.3 : 0.22) * f, 0.75 * f)
        }
        // Head.
        where(Math.min(u, HOME), caller, machine, bend)
        if (moving) {
          core.set(k++, at.x, at.y, 0, colour, returning ? 0.2 : 0.3, 1)
          glow.set(g++, at.x, at.y, 0, colour, returning ? 1.5 : 0.95, P.additive ? 0.4 : 0.22)
        } else {
          core.hide(k++)
          glow.hide(g++)
        }
        // The answer rides home as a picture of itself, growing as it goes.
        job.sprite.visible = returning && u < HOME + 0.04
        if (job.sprite.visible) {
          if (job.shown !== signal) {
            job.mat.map = icons[signal]
            job.shown = signal
          }
          job.mat.color.copy(colour)
          const grow = easeBack(ramp(u, WORK, WORK + 0.07))
          job.sprite.position.set(at.x, at.y, 0.1)
          job.sprite.scale.setScalar((0.55 + 0.35 * ramp(u, WORK, HOME)) * grow * (1 - ramp(u, HOME, HOME + 0.04)))
        }
        // Working: the machine fills with the job's colour and lights circle it.
        const w = ramp(u, ON, WORK)
        for (let i = 0; i < 3; i++) {
          if (!working) { core.hide(k++); continue }
          const a = w * Math.PI * 5 + (i * Math.PI * 2) / 3
          const r = machine.size * (0.82 - 0.25 * w)
          core.set(k++, machine.x + Math.cos(a) * r, machine.y + Math.sin(a) * r, 0, colour, 0.17, 0.95)
        }
        if (working) {
          const heat = Math.sin(Math.min(1, w * 1.15) * Math.PI) * 0.6 + 0.35 * w
          if (heat > machine.heat) { machine.heat = heat; machine.tint = colour }
        }
        // A burst as the answer leaves the machine, a ripple as it lands.
        const burst = ramp(u, WORK, WORK + 0.06)
        if (returning && burst < 1) glow.set(g++, machine.x, machine.y, 0, colour, machine.size * (1.4 + 2.2 * burst), (P.additive ? 0.5 : 0.3) * (1 - burst))
        else glow.hide(g++)
        const land = ramp(u, HOME - 0.01, 1)
        if (u >= HOME - 0.01) {
          glow.set(g++, caller.x, caller.y, 0, colour, 0.6 + 2 * land, (P.additive ? 0.55 : 0.32) * (1 - land))
          caller.hit = Math.max(caller.hit, 1 - land)
        } else glow.hide(g++)
        core.hide(k++); core.hide(k++)
        if (Math.abs(u - OUT) < 0.035 || Math.abs(u - BACK) < 0.035) hub = Math.max(hub, 1 - Math.min(Math.abs(u - OUT), Math.abs(u - BACK)) / 0.035)
      })

      machines.forEach((m) => {
        m.fill.color.copy(m.tint)
        m.fill.opacity = Math.min(0.9, m.heat) * (P.additive ? 0.85 : 0.6)
        m.group.scale.setScalar(1 + 0.07 * m.heat)
        glow.set(g++, m.x, m.y, 0, m.heat > 0.02 ? m.tint : cMachine, m.size * 2.6, (P.additive ? 0.14 : 0.07) + m.heat * (P.additive ? 0.3 : 0.16))
      })
      callers.forEach((c, i) => {
        const breathe = 0.5 + 0.5 * Math.sin(t * 1.3 + i * 2.1)
        c.mesh.scale.setScalar(1 + 0.1 * breathe + 0.5 * c.hit)
        glow.set(g++, c.x, c.y, 0, c.agent ? cAgent : cPerson, 0.85 + 0.2 * breathe, (P.additive ? 0.2 : 0.1) + 0.2 * c.hit)
      })
      // The club's own glow, and six small lights circling inside it.
      glow.set(g++, 0, 0, 0, tmp.copy(cDim).lerp(cMachine, hub), 3.4, (P.additive ? 0.22 : 0.1) + 0.25 * hub)
      while (g < glow.count) glow.hide(g++)
      SIGNALS.forEach((s, i) => {
        const a = t * 0.9 + (i * Math.PI * 2) / SIGNALS.length
        core.set(k++, Math.cos(a) * R_HUB * 0.42, Math.sin(a) * R_HUB * 0.42, 0, hue[s], 0.17, 0.95)
      })
      while (k < core.count) core.hide(k++)
      glow.commit()
      core.commit()

      const ring = pulseRing.material as T.LineBasicMaterial
      ring.opacity = hub * 0.95
      pulseRing.scale.setScalar(1 + 0.16 * hub)
    },
  }
}

export default exchange
