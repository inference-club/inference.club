// "A network that grows": one lit window, then a street, then a town.
//
// Each light is a household with a machine. They appear from the middle
// outwards; every new one links to its nearest neighbours that were already
// there, and small lights (requests and answers) travel the links. The view
// pulls back as the network fills, holds, then fades and begins again.
//
// The scene reports how many lights are on (`emit('count', n)`) so the page
// can show the number beside it.

import type * as T from 'three'
import { ramp, seeded, smooth, softDot, type SceneFactory } from '../stage'

export interface NetworkOptions {
  /** How many households the network grows to. */
  nodes?: number
}

const GROW = 15 // seconds to reach full size
const HOLD = 6
const FADE = 2.5
const LOOP = GROW + HOLD + FADE

const network: SceneFactory<NetworkOptions> = (ctx) => {
  const { THREE, palette: P, scene } = ctx
  const N = ctx.options?.nodes ?? 240
  const rnd = seeded(3)
  const dot = softDot(THREE, ctx.keep)
  const blending = P.additive ? THREE.AdditiveBlending : THREE.NormalBlending
  const root = new THREE.Group()
  root.rotation.x = -0.82 // tilt the plane away from the viewer
  scene.add(root)
  const RADIUS = 13

  // Sunflower layout: node i sits at radius ∝ √i, so "earlier" means "nearer
  // the middle" and growth reads as spreading outwards.
  const nodes = Array.from({ length: N }, (_, i) => {
    const r = RADIUS * Math.sqrt((i + 0.5) / N) * (0.94 + rnd() * 0.12)
    const a = i * 2.39996 + (rnd() - 0.5) * 0.5
    return {
      x: Math.cos(a) * r, y: Math.sin(a) * r,
      born: i === 0 ? 0 : GROW * Math.pow(i / N, 0.62),
      big: rnd() < 0.16, // a few households have serious hardware
    }
  })

  // Links: each node to its two nearest elders.
  const links: Array<[number, number]> = []
  for (let i = 1; i < N; i++) {
    const near = [] as Array<[number, number]>
    for (let j = 0; j < i; j++) {
      const d = (nodes[i].x - nodes[j].x) ** 2 + (nodes[i].y - nodes[j].y) ** 2
      near.push([d, j])
    }
    near.sort((a, b) => a[0] - b[0])
    near.slice(0, i < 4 ? 1 : 2).forEach(([, j]) => links.push([i, j]))
  }

  // Lights: two point clouds (ordinary and big) with per-point brightness.
  const cloud = (big: boolean) => {
    const idx = nodes.map((n, i) => (n.big === big ? i : -1)).filter((i) => i >= 0)
    const geo = ctx.keep(new THREE.BufferGeometry())
    geo.setAttribute('position', new THREE.Float32BufferAttribute(idx.flatMap((i) => [nodes[i].x, nodes[i].y, 0]), 3))
    const colors = new Float32Array(idx.length * 3)
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    const mat = ctx.keep(new THREE.PointsMaterial({
      map: dot, size: big ? 1.15 : 0.6, vertexColors: true, transparent: true, depthWrite: false, blending, sizeAttenuation: true,
    }))
    root.add(new THREE.Points(geo, mat))
    return { idx, colors, geo, base: new THREE.Color(big ? P.amber : P.ink) }
  }
  const clouds = [cloud(false), cloud(true)]

  const linkGeo = ctx.keep(new THREE.BufferGeometry())
  linkGeo.setAttribute('position', new THREE.Float32BufferAttribute(links.flatMap(([a, b]) => [nodes[a].x, nodes[a].y, 0, nodes[b].x, nodes[b].y, 0]), 3))
  const linkColors = new Float32Array(links.length * 6)
  linkGeo.setAttribute('color', new THREE.BufferAttribute(linkColors, 3))
  root.add(new THREE.LineSegments(linkGeo, ctx.keep(new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: P.additive ? 0.75 : 0.9, depthWrite: false, blending }))))
  const linkBase = new THREE.Color(P.additive ? P.dim : P.line)
  const ground = new THREE.Color(P.ground)

  // Travellers along the links.
  const TRAVELLERS = 70
  const travPos = new Float32Array(TRAVELLERS * 3)
  const travCol = new Float32Array(TRAVELLERS * 3)
  const travGeo = ctx.keep(new THREE.BufferGeometry())
  travGeo.setAttribute('position', new THREE.BufferAttribute(travPos, 3))
  travGeo.setAttribute('color', new THREE.BufferAttribute(travCol, 3))
  root.add(new THREE.Points(travGeo, ctx.keep(new THREE.PointsMaterial({ map: dot, size: 0.34, vertexColors: true, transparent: true, depthWrite: false, blending }))))
  const hues = [P.amber, P.coral, P.teal, P.violet, P.sky, P.ink].map((c) => new THREE.Color(c))
  const travellers = Array.from({ length: TRAVELLERS }, (_, k) => ({ link: Math.floor(rnd() * links.length), phase: rnd(), speed: 0.35 + rnd() * 0.5, hue: hues[k % hues.length] }))

  const cam = ctx.camera as T.PerspectiveCamera
  const tmp = new THREE.Color()
  let lastCount = -1
  let pull = 1

  return {
    poster: GROW + 2,
    resize({ aspect }) {
      // Narrow screens need the camera further back to hold the full width.
      pull = Math.max(1, 1.38 / aspect)
    },
    update(t) {
      const time = t % LOOP
      const out = 1 - smooth(ramp(time, GROW + HOLD, LOOP)) // fade before the loop restarts
      const grown = smooth(ramp(time, 0, GROW))
      const lit = (i: number) => smooth(ramp(time, nodes[i].born, nodes[i].born + 0.9)) * out

      clouds.forEach((c) => {
        c.idx.forEach((i, k) => {
          const twinkle = 0.82 + 0.18 * Math.sin(t * 2.1 + i * 1.7)
          const a = lit(i) * twinkle
          // On paper a hidden point is the paper's colour; at night it is black.
          tmp.copy(c.base)
          if (P.additive) tmp.multiplyScalar(a)
          else tmp.lerp(ground, 1 - a)
          c.colors[k * 3] = tmp.r; c.colors[k * 3 + 1] = tmp.g; c.colors[k * 3 + 2] = tmp.b
        })
        c.geo.attributes.color.needsUpdate = true
      })

      links.forEach(([a], k) => {
        const v = lit(a) * 0.9
        tmp.copy(linkBase)
        if (P.additive) tmp.multiplyScalar(v)
        else tmp.lerp(ground, 1 - v)
        for (let e = 0; e < 2; e++) {
          linkColors[k * 6 + e * 3] = tmp.r; linkColors[k * 6 + e * 3 + 1] = tmp.g; linkColors[k * 6 + e * 3 + 2] = tmp.b
        }
      })
      linkGeo.attributes.color.needsUpdate = true

      travellers.forEach((tr, k) => {
        const [a, b] = links[tr.link]
        const u = (tr.phase + t * tr.speed) % 1
        // Back and forth: a request out, an answer home.
        const w = u < 0.5 ? u * 2 : 2 - u * 2
        const on = lit(a)
        travPos[k * 3] = nodes[a].x + (nodes[b].x - nodes[a].x) * w
        travPos[k * 3 + 1] = nodes[a].y + (nodes[b].y - nodes[a].y) * w
        travPos[k * 3 + 2] = 0.02
        tmp.copy(tr.hue)
        if (P.additive) tmp.multiplyScalar(on)
        else tmp.lerp(ground, 1 - on)
        travCol[k * 3] = tmp.r; travCol[k * 3 + 1] = tmp.g; travCol[k * 3 + 2] = tmp.b
      })
      travGeo.attributes.position.needsUpdate = true
      travGeo.attributes.color.needsUpdate = true

      // Pull back as it grows; turn slowly throughout.
      root.rotation.z = t * 0.035
      // Stay just far enough back to hold the lights that are on so far.
      const reach = RADIUS * Math.pow(ramp(time, 0, GROW), 0.8)
      const dist = (4 + 2.3 * reach) * pull
      cam.position.set(0, dist * 0.08, dist)
      cam.lookAt(0, -0.6 * grown, 0)

      const count = nodes.reduce((n, node) => n + (time >= node.born && out > 0.5 ? 1 : 0), 0)
      if (count !== lastCount) {
        lastCount = count
        ctx.emit('count', count)
      }
    },
  }
}

export default network
