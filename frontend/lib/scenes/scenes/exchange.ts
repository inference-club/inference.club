// "Give and take": who asks, and whose machine answers.
//
// Seen from above. Around the outside are the callers: people (round) and
// agents (diamond). Nearer the middle are members' machines (squares, bigger
// for bigger GPUs). In the centre is the club, drawn as a ring, because every
// request passes through it. A request leaves a caller as a small light in the
// colour of what was asked for, reaches the club, is sent to a machine that
// glows while it works, and the result travels back larger than it left.
//
// One caller and one machine wear the same dashed halo: that member keeps
// their machine to themselves, and only their own requests go to it.

import type * as T from 'three'
import { flatCamera, ramp, seeded, smooth, softDot, type SceneFactory } from '../stage'
import { SIGNALS, signalColor, type Signal } from '../theme'

export interface ExchangeOptions {
  callers?: number
  machines?: number
}

const R_CALLERS = 5.7
const R_MACHINES = 3.05
const FIT = 6.7 // world units from the centre that must stay in view

const exchange: SceneFactory<ExchangeOptions> = (ctx) => {
  const { THREE, palette: P, scene } = ctx
  const cam = flatCamera(ctx, FIT * 2)
  const rnd = seeded(21)
  const nCallers = ctx.options?.callers ?? 18
  const nMachines = ctx.options?.machines ?? 7
  const dot = softDot(THREE, ctx.keep)
  const root = new THREE.Group()
  scene.add(root)

  const line = (pts: T.Vector3[], color: string, opacity: number, dashed = false) => {
    const geo = ctx.keep(new THREE.BufferGeometry().setFromPoints(pts))
    const mat = dashed
      ? ctx.keep(new THREE.LineDashedMaterial({ color, transparent: true, opacity, dashSize: 0.16, gapSize: 0.13 }))
      : ctx.keep(new THREE.LineBasicMaterial({ color, transparent: true, opacity }))
    const l = new THREE.Line(geo, mat)
    if (dashed) l.computeLineDistances()
    root.add(l)
    return l
  }
  const circle = (r: number, cx = 0, cy = 0, n = 72) =>
    Array.from({ length: n + 1 }, (_, i) => new THREE.Vector3(cx + Math.cos((i / n) * Math.PI * 2) * r, cy + Math.sin((i / n) * Math.PI * 2) * r, 0))

  // The club.
  line(circle(0.95), P.ink, 0.9)
  const pulseRing = line(circle(1), P.amber, 0)
  line(circle(R_MACHINES), P.line, 0.5)
  line(circle(R_CALLERS), P.line, 0.35)

  // Machines: outlined squares, filled with light while working.
  const machines = Array.from({ length: nMachines }, (_, i) => {
    const a = (i / nMachines) * Math.PI * 2 + 0.4
    const size = 0.55 + rnd() * 0.55
    const pos = new THREE.Vector3(Math.cos(a) * R_MACHINES, Math.sin(a) * R_MACHINES, 0)
    const h = size / 2
    const outline = line(
      [[-h, -h], [h, -h], [h, h], [-h, h], [-h, -h]].map(([x, y]) => new THREE.Vector3(pos.x + x, pos.y + y, 0)),
      P.amber, 0.95,
    )
    const fill = new THREE.Mesh(ctx.keep(new THREE.PlaneGeometry(size * 0.82, size * 0.82)), ctx.glow(P.amber, 0))
    fill.position.copy(pos)
    root.add(fill)
    return { pos, size, fill, outline, heat: 0 }
  })

  // Callers: people are discs, agents are diamonds.
  const callers = Array.from({ length: nCallers }, (_, i) => {
    const a = (i / nCallers) * Math.PI * 2 + (rnd() - 0.5) * 0.12
    const r = R_CALLERS + (rnd() - 0.5) * 0.5
    const pos = new THREE.Vector3(Math.cos(a) * r, Math.sin(a) * r, 0)
    const agent = i % 3 === 1
    const mesh = agent
      ? new THREE.Mesh(ctx.keep(new THREE.PlaneGeometry(0.3, 0.3)), ctx.glow(P.coral, 0.95))
      : new THREE.Mesh(ctx.keep(new THREE.CircleGeometry(0.17, 20)), ctx.glow(P.ink, 0.95))
    if (agent) mesh.rotation.z = Math.PI / 4
    mesh.position.copy(pos)
    root.add(mesh)
    return { pos, agent, mesh }
  })

  // The private pair: the same dashed halo on a caller and on their machine.
  const OWNER = 0
  const OWN_MACHINE = 0
  line(circle(0.42, callers[OWNER].pos.x, callers[OWNER].pos.y, 40), P.violet, 0.95, true)
  line(circle(machines[OWN_MACHINE].size * 0.95, machines[OWN_MACHINE].pos.x, machines[OWN_MACHINE].pos.y, 48), P.violet, 0.95, true)

  // Jobs in flight. Each one owns a moving light and the faint path it follows.
  const JOBS = 9
  const ORIGIN = new THREE.Vector3()
  const bend = (a: T.Vector3, b: T.Vector3, k: number) => {
    const mid = a.clone().lerp(b, 0.5)
    const n = new THREE.Vector3(-(b.y - a.y), b.x - a.x, 0).multiplyScalar(k)
    return new THREE.QuadraticBezierCurve3(a, mid.add(n), b)
  }
  const jobs = Array.from({ length: JOBS }, (_, j) => {
    const sprite = new THREE.Sprite(ctx.keep(new THREE.SpriteMaterial({
      map: dot, transparent: true, depthWrite: false,
      blending: P.additive ? THREE.AdditiveBlending : THREE.NormalBlending,
    })))
    sprite.visible = false
    root.add(sprite)
    const pathGeo = ctx.keep(new THREE.BufferGeometry())
    const pathMat = ctx.keep(new THREE.LineBasicMaterial({ color: P.ink, transparent: true, opacity: 0 }))
    const path = new THREE.Line(pathGeo, pathMat)
    root.add(path)
    return {
      sprite, path, pathGeo, pathMat, start: j * 0.9 - 2, length: 4.4 + rnd() * 1.2,
      caller: 0, machine: 0, signal: 'text' as Signal, round: -1,
      a: null as T.QuadraticBezierCurve3 | null, b: null as T.QuadraticBezierCurve3 | null,
    }
  })
  const assign = (job: (typeof jobs)[number], round: number) => {
    job.round = round
    // The owner's requests always go to their own machine; nobody else's do.
    const own = (round + jobs.indexOf(job)) % 5 === 0
    job.caller = own ? OWNER : 1 + Math.floor(rnd() * (nCallers - 1))
    job.machine = own ? OWN_MACHINE : 1 + Math.floor(rnd() * (nMachines - 1))
    job.signal = SIGNALS[Math.floor(rnd() * SIGNALS.length)]
    const k = (rnd() - 0.5) * 0.5
    job.a = bend(callers[job.caller].pos, ORIGIN, k)
    job.b = bend(ORIGIN, machines[job.machine].pos, -k)
    job.pathGeo.setFromPoints([...job.a.getPoints(20), ...job.b.getPoints(20)])
    const c = own ? P.violet : signalColor(P, job.signal)
    job.sprite.material.color.set(c)
    job.pathMat.color.set(c)
  }

  const p = new THREE.Vector3()
  return {
    poster: 5.2,
    resize({ aspect }) {
      // Keep the whole ring in view on tall screens too.
      ;(cam.userData.fit as (a: number, h: number) => void)(aspect, aspect < 1 ? (FIT * 2) / aspect : FIT * 2)
    },
    update(t, dt) {
      root.rotation.z = t * 0.02
      machines.forEach((m) => {
        m.heat = Math.max(0, m.heat - dt * 1.4)
        ;(m.fill.material as T.MeshBasicMaterial).opacity = Math.min(0.85, m.heat) * (P.additive ? 0.9 : 0.7)
      })
      let hub = 0
      jobs.forEach((job) => {
        const local = t - job.start
        if (local < 0) return
        const round = Math.floor(local / job.length)
        if (round !== job.round) assign(job, round)
        const u = (local % job.length) / job.length
        // Out to the club, on to the machine, work, then all the way back.
        const out = ramp(u, 0, 0.2)
        const on = ramp(u, 0.2, 0.4)
        const work = u >= 0.4 && u < 0.52
        const back = ramp(u, 0.52, 0.9)
        job.sprite.visible = u < 0.94
        if (u < 0.2) job.a!.getPoint(smooth(out), p)
        else if (u < 0.4) job.b!.getPoint(smooth(on), p)
        else if (work) p.copy(machines[job.machine].pos)
        else if (back < 0.5) job.b!.getPoint(1 - smooth(back * 2), p)
        else job.a!.getPoint(1 - smooth(back * 2 - 1), p)
        job.sprite.position.copy(p)
        // The answer is bigger than the question.
        const size = u < 0.4 ? 0.42 : work ? 0.42 + 0.5 * Math.sin(((u - 0.4) / 0.12) * Math.PI) : 0.8
        job.sprite.scale.setScalar(size * (1 - ramp(u, 0.88, 0.94)))
        if (work) machines[job.machine].heat = 1
        if (Math.abs(u - 0.2) < 0.03 || Math.abs(u - 0.71) < 0.03) hub = 1
        job.pathMat.opacity = 0.34 * Math.sin(Math.min(1, u / 0.94) * Math.PI)
      })
      ;(pulseRing.material as T.LineBasicMaterial).opacity += ((hub ? 0.9 : 0) - (pulseRing.material as T.LineBasicMaterial).opacity) * 0.15
      pulseRing.scale.setScalar(1 + 0.12 * (pulseRing.material as T.LineBasicMaterial).opacity)
    },
  }
}

export default exchange
