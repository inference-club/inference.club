// "A network that grows": one lit window, then a street, then a town.
//
// Each light is a household with a machine; the larger amber ones have serious
// hardware. They appear from the middle outwards. A link reaches out from an
// existing light, the new one pops on at its end with a ripple, and small
// lights with tails (requests and answers, in the colour of what they carry)
// start to travel it. Once the town is large enough, long arcs leap between
// distant parts of it. The view pulls back as the network fills, holds, then
// folds back to the first light and begins again; that first light never
// goes out.
//
// The scene reports how many lights are on (`emit('count', n)`) so the page
// can show the number beside it.

import type * as T from 'three'
import { easeBack, easeInOut, hash, ramp, seeded, smooth, sparks, type SceneFactory } from '../stage'
import { SIGNALS, signalColor } from '../theme'

export interface NetworkOptions {
  /** How many households the network grows to. */
  nodes?: number
}

const GROW = 14 // seconds to reach full size
const HOLD = 5
const FOLD = 2.4
const LOOP = GROW + HOLD + FOLD
const RADIUS = 13
const TAIL = 4
const ARC_STEPS = 28

const network: SceneFactory<NetworkOptions> = (ctx) => {
  const { THREE, palette: P, scene } = ctx
  const N = ctx.options?.nodes ?? 220
  const rnd = seeded(3)
  const blending = P.additive ? THREE.AdditiveBlending : THREE.NormalBlending
  const root = new THREE.Group()
  root.rotation.x = -0.86 // tilt the plane away from the viewer
  scene.add(root)
  const ground = new THREE.Color(P.ground)
  const tints = [P.ink, P.ink, P.ink, P.sky, P.teal, P.pink, P.violet].map((c) => new THREE.Color(c))
  const cBig = new THREE.Color(P.amber)
  const cLink = new THREE.Color(P.dim)
  const hues = SIGNALS.map((s) => new THREE.Color(signalColor(P, s)))
  const tmp = new THREE.Color()
  /** `base` at strength k: dimmer light at night, paler ink on paper. */
  const tone = (base: T.Color, k: number) => (P.additive ? tmp.copy(base).multiplyScalar(k) : tmp.copy(ground).lerp(base, k))

  // Sunflower layout: node i sits at radius ∝ √i, so "earlier" means "nearer
  // the middle" and growth reads as spreading outwards. The ground rolls a
  // little, so the town has some depth.
  const nodes = Array.from({ length: N }, (_, i) => {
    const r = RADIUS * Math.sqrt((i + 0.5) / N) * (0.94 + rnd() * 0.12)
    const a = i * 2.39996 + (rnd() - 0.5) * 0.5
    const x = Math.cos(a) * r
    const y = Math.sin(a) * r
    const big = i === 0 || rnd() < 0.15
    return {
      x, y, z: 0.55 * Math.sin(x * 0.33 + 1) * Math.cos(y * 0.29),
      born: i === 0 ? -5 : GROW * Math.pow(i / N, 0.62),
      big, tint: big ? cBig : tints[Math.floor(rnd() * tints.length)], on: 0,
    }
  })

  // Links: each node to its two nearest elders.
  const links: Array<[number, number]> = []
  for (let i = 1; i < N; i++) {
    const near = [] as Array<[number, number]>
    for (let j = 0; j < i; j++) near.push([(nodes[i].x - nodes[j].x) ** 2 + (nodes[i].y - nodes[j].y) ** 2, j])
    near.sort((a, b) => a[0] - b[0])
    near.slice(0, i < 4 ? 1 : 2).forEach(([, j]) => links.push([i, j]))
  }
  const linkPos = new Float32Array(links.length * 6)
  const linkCol = new Float32Array(links.length * 6)
  const linkGeo = ctx.keep(new THREE.BufferGeometry())
  linkGeo.setAttribute('position', new THREE.BufferAttribute(linkPos, 3))
  linkGeo.setAttribute('color', new THREE.BufferAttribute(linkCol, 3))
  const linkLines = new THREE.LineSegments(linkGeo, ctx.keep(new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: P.additive ? 0.8 : 0.75, depthWrite: false, blending })))
  linkLines.frustumCulled = false
  root.add(linkLines)

  // Long arcs between distant households, once the town is big enough.
  const ARCS = 14
  const arcs = Array.from({ length: ARCS }, (_, k) => {
    const a = Math.floor(N * (0.25 + 0.7 * rnd()))
    let b = Math.floor(N * (0.1 + 0.85 * rnd()))
    for (let tries = 0; tries < 20 && (nodes[a].x - nodes[b].x) ** 2 + (nodes[a].y - nodes[b].y) ** 2 < 90; tries++) b = Math.floor(N * rnd())
    const A = nodes[a]
    const B = nodes[b]
    const lift = 0.3 * Math.hypot(A.x - B.x, A.y - B.y)
    const pts = Array.from({ length: ARC_STEPS + 1 }, (_, s) => {
      const u = s / ARC_STEPS
      return new THREE.Vector3(A.x + (B.x - A.x) * u, A.y + (B.y - A.y) * u, A.z + (B.z - A.z) * u + Math.sin(u * Math.PI) * lift)
    })
    const hue = hues[k % hues.length]
    const mat = ctx.keep(new THREE.LineBasicMaterial({ color: hue, transparent: true, opacity: 0, depthWrite: false, blending }))
    const lineObj = new THREE.Line(ctx.keep(new THREE.BufferGeometry().setFromPoints(pts)), mat)
    lineObj.frustumCulled = false
    root.add(lineObj)
    return { pts, mat, line: lineObj, hue, born: Math.max(A.born, B.born) + 0.6 + rnd() * 2.5, speed: 0.22 + rnd() * 0.2, phase: rnd() }
  })

  // Lights. Halos behind, crisp cores in front, travellers on top.
  const DUST = 90
  const halos = sparks(ctx, N + DUST)
  const cores = sparks(ctx, N, { hard: 0.55 })
  const TRAVELLERS = 80
  const movers = sparks(ctx, (TRAVELLERS + ARCS) * (TAIL + 1), { hard: 0.3 })
  root.add(halos.object, cores.object, movers.object)
  const travellers = Array.from({ length: TRAVELLERS }, (_, k) => ({ phase: rnd(), speed: 0.3 + rnd() * 0.45, hue: hues[k % hues.length] }))
  const dust = Array.from({ length: DUST }, () => {
    const r = RADIUS * (0.2 + 1.5 * Math.sqrt(rnd()))
    const a = rnd() * Math.PI * 2
    return { x: Math.cos(a) * r, y: Math.sin(a) * r, z: -1.5 - rnd() * 5, s: 0.25 + rnd() * 0.5, hue: hues[Math.floor(rnd() * hues.length)] }
  })

  const cam = ctx.camera as T.PerspectiveCamera
  let lastCount = -1
  let pull = 1

  return {
    poster: GROW + 2,
    resize({ aspect }) {
      // Narrow screens need the camera further back to hold the full width.
      pull = Math.max(1, 1.38 / aspect)
    },
    update(t) {
      const time = ((t % LOOP) + LOOP) % LOOP
      const fold = ramp(time, GROW + HOLD, LOOP)
      // Lights go out from the edge inwards as the loop folds; the first stays.
      const off = (i: number) => (i === 0 ? 0 : smooth(ramp(fold, 0.75 * (1 - i / N), 0.75 * (1 - i / N) + 0.25)))
      let count = 0

      nodes.forEach((n, i) => {
        const age = time - n.born
        const pop = easeBack(ramp(age, 0, 0.7))
        const gone = off(i)
        n.on = smooth(ramp(age, 0, 0.5)) * (1 - gone)
        if (age >= 0 && gone < 0.5) count++
        const twinkle = 0.85 + 0.15 * Math.sin(t * 2.3 + i * 1.7)
        const size = (n.big ? 0.5 : 0.27) * pop * (1 - 0.6 * gone)
        cores.set(i, n.x, n.y, n.z, n.tint, size, n.on > 0.01 ? 0.95 * twinkle : 0)
        // A ripple as it switches on, then a steady soft halo.
        const ripple = age > 0 && age < 1.4 ? 1 - age / 1.4 : 0
        halos.set(i, n.x, n.y, n.z, n.tint, (n.big ? 2.2 : 1.1) * pop + 3.2 * (1 - ripple) * (ripple > 0 ? 1 : 0),
          n.on * ((P.additive ? 0.3 : 0.15) * (n.big ? 1.2 : 0.8) * twinkle + 0.5 * ripple * ripple))
      })
      cores.commit()

      // A link reaches out from the elder just before the new light comes on.
      links.forEach(([a, b], k) => {
        const A = nodes[a]
        const B = nodes[b]
        const reach = easeInOut(ramp(time, A.born - 0.55, A.born + 0.05))
        const v = reach > 0 ? Math.min(B.on, 1 - off(a)) * (0.55 + 0.45 * A.on) : 0
        const o = k * 6
        linkPos[o] = B.x; linkPos[o + 1] = B.y; linkPos[o + 2] = B.z
        linkPos[o + 3] = B.x + (A.x - B.x) * reach; linkPos[o + 4] = B.y + (A.y - B.y) * reach; linkPos[o + 5] = B.z + (A.z - B.z) * reach
        tone(cLink, v * (P.additive ? 0.8 : 0.7))
        for (let e = 0; e < 2; e++) { linkCol[o + e * 3] = tmp.r; linkCol[o + e * 3 + 1] = tmp.g; linkCol[o + e * 3 + 2] = tmp.b }
      })
      linkGeo.attributes.position.needsUpdate = true
      linkGeo.attributes.color.needsUpdate = true

      // Requests out and answers home along the links, each with a short tail.
      let m = 0
      travellers.forEach((tr, k) => {
        const round = Math.floor(tr.phase + t * tr.speed)
        const [a, b] = links[Math.floor(hash(k * 13.7 + round * 5.3) * links.length)]
        const A = nodes[a]
        const B = nodes[b]
        const u = (((tr.phase + t * tr.speed) % 1) + 1) % 1
        const on = Math.min(A.on, B.on) * Math.sin(u * Math.PI)
        for (let s = 0; s <= TAIL; s++) {
          const us = u - s * 0.05
          const w = us < 0.5 ? us * 2 : 2 - us * 2 // there and back
          if (on < 0.02 || us < 0 || (u >= 0.5) !== (us >= 0.5)) { movers.hide(m++); continue }
          movers.set(m++, B.x + (A.x - B.x) * w, B.y + (A.y - B.y) * w, B.z + (A.z - B.z) * w + 0.03, tr.hue, (s ? 0.26 : 0.36) * (1 - s / (TAIL + 1)), on * (1 - s / (TAIL + 1)))
        }
      })
      arcs.forEach((arc) => {
        const drawn = easeInOut(ramp(time, arc.born, arc.born + 1.2)) * (1 - smooth(ramp(fold, 0, 0.35)))
        arc.line.geometry.setDrawRange(0, Math.round(drawn * (ARC_STEPS + 1)))
        arc.mat.opacity = (P.additive ? 0.55 : 0.5) * drawn
        const u = (((arc.phase + t * arc.speed) % 1) + 1) % 1
        for (let s = 0; s <= TAIL; s++) {
          const us = u - s * 0.035
          if (drawn < 0.99 || us < 0) { movers.hide(m++); continue }
          const f = us * ARC_STEPS
          const i0 = Math.min(ARC_STEPS - 1, Math.floor(f))
          const p0 = arc.pts[i0]
          const p1 = arc.pts[i0 + 1]
          const w = f - i0
          movers.set(m++, p0.x + (p1.x - p0.x) * w, p0.y + (p1.y - p0.y) * w, p0.z + (p1.z - p0.z) * w, arc.hue, (s ? 0.34 : 0.5) * (1 - s / (TAIL + 1)), Math.sin(u * Math.PI) * (1 - s / (TAIL + 1)))
        }
      })
      movers.commit()

      // Far, slow dust under the town, for depth as the view turns.
      const grown = smooth(ramp(time, 0, GROW)) * (1 - easeInOut(fold))
      dust.forEach((d, i) => {
        halos.set(N + i, d.x, d.y, d.z, d.hue, d.s, (P.additive ? 0.3 : 0.14) * (0.25 + 0.75 * grown) * (0.7 + 0.3 * Math.sin(t * 0.7 + i)))
      })
      halos.commit()

      // Pull back as it grows, in again as it folds; turn slowly throughout.
      root.rotation.z = t * 0.045
      const reach = RADIUS * Math.pow(ramp(time, 0, GROW), 0.8) * (1 - easeInOut(fold))
      const dist = (4.6 + 2.25 * reach) * pull
      cam.position.set(Math.sin(t * 0.21) * 0.035 * dist, dist * (0.08 + 0.015 * Math.sin(t * 0.17)), dist)
      cam.lookAt(0, -0.045 * reach, 0)

      if (count !== lastCount) {
        lastCount = count
        ctx.emit('count', count)
      }
    },
  }
}

export default network
