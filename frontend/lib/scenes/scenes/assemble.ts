// "From a picture to something you can turn": a real generated 3D model
// building itself out of the picture it was made from.
//
// On one side is the flat picture. Dots lift off it, lowest part of the model
// first, fly across and settle into place on a turntable while a ring rises
// with the build. The finished model turns for a while, then blows away as
// the next picture arrives. Every model shown is a real result from the
// club's 3D service, sampled down to points (see
// scripts/showcase/mesh_points.py).
//
// The scene reports which model is on show (`emit('model', index)`) so the
// page can caption it.

import type * as T from 'three'
import { easeBack, easeInOut, loadPoints, modelCloud, ramp, seeded, smooth, sparks, type SceneFactory } from '../stage'

export interface AssembleOptions {
  /** Each model's point file and the picture it was made from. */
  models: Array<{ src: string; image?: string | null }>
  /** Seconds each model is on show. */
  seconds?: number
}

const assemble: SceneFactory<AssembleOptions> = async (ctx) => {
  const { THREE, palette: P, scene } = ctx
  const T_EACH = ctx.options.seconds ?? 11
  const cam = ctx.camera as T.PerspectiveCamera
  const rnd = seeded(5)
  const pink = new THREE.Color(P.pink)
  const sky = new THREE.Color(P.sky)
  const amber = new THREE.Color(P.amber)

  const loaded = await Promise.all(ctx.options.models.map(async (m) => ({ points: await loadPoints(m.src), image: m.image })))
  const items = loaded.filter((m) => m.points).map((m, i) => {
    const pts = m.points!
    let lo = 1
    let hi = -1
    for (let k = 1; k < pts.count * 3; k += 3) {
      lo = Math.min(lo, pts.positions[k])
      hi = Math.max(hi, pts.positions[k])
    }
    const cloud = modelCloud(ctx, pts, { size: 0.027, tint: i % 2 ? P.pink : P.sky, seed: 60 + i })
    cloud.object.visible = false
    scene.add(cloud.object)
    // The picture it came from, on a card.
    const mat = ctx.keep(new THREE.MeshBasicMaterial({ color: P.line, transparent: true, opacity: 0, depthWrite: false }))
    const card = new THREE.Mesh(ctx.keep(new THREE.PlaneGeometry(1, 1)), mat)
    card.visible = false
    scene.add(card)
    const item = { cloud, card, mat, lo, hi, shape: 1 }
    if (m.image) {
      new THREE.TextureLoader().load(m.image, (tex) => {
        tex.colorSpace = THREE.SRGBColorSpace
        mat.map = ctx.keep(tex)
        mat.color.set('#ffffff')
        mat.needsUpdate = true
        item.shape = tex.image.width / tex.image.height
      })
    }
    return item
  })
  if (!items.length) throw new Error('no models to show')

  // Turntable: two rings under the model, and one that rises with the build.
  const ring = (r: number, color: string, opacity: number, dashed = false) => {
    const pts = Array.from({ length: 97 }, (_, i) => new THREE.Vector3(Math.cos((i / 96) * Math.PI * 2) * r, 0, Math.sin((i / 96) * Math.PI * 2) * r))
    const geo = ctx.keep(new THREE.BufferGeometry().setFromPoints(pts))
    const m = dashed
      ? ctx.keep(new THREE.LineDashedMaterial({ color, transparent: true, opacity, dashSize: 0.09, gapSize: 0.07 }))
      : ctx.keep(new THREE.LineBasicMaterial({ color, transparent: true, opacity }))
    const l = new THREE.Line(geo, m)
    if (dashed) l.computeLineDistances()
    return l
  }
  const table = new THREE.Group()
  scene.add(table)
  const base = ring(1.02, P.dim, 0.9)
  const outer = ring(1.3, P.line, 0.9, true)
  const scan = ring(1.08, P.pink, 0)
  table.add(base, outer, scan)
  const frame = new THREE.LineLoop(
    ctx.keep(new THREE.BufferGeometry().setFromPoints([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]].map(([x, y]) => new THREE.Vector3(x, y, 0)))),
    ctx.keep(new THREE.LineBasicMaterial({ color: P.amber, transparent: true, opacity: 0.9 })),
  )
  scene.add(frame)

  // Lights: dust for depth, markers circling the turntable, a glow under it.
  const DUST = 60
  const lights = sparks(ctx, DUST + 8)
  scene.add(lights.object)
  const dust = Array.from({ length: DUST }, () => ({ x: (rnd() - 0.5) * 14, y: (rnd() - 0.5) * 8, z: -2 - rnd() * 6, s: 0.1 + rnd() * 0.25, c: [pink, sky, amber][Math.floor(rnd() * 3)] }))

  // Where things sit. Wide: picture left, model right. Tall: picture above.
  const model = new THREE.Vector3()
  const cardAt = new THREE.Vector3()
  let scale = 1.25
  let cardSize = 1.9
  let dist = 8.6
  let lookDown = 0.05 // how far below the middle of the two the camera aims
  const layout = (aspect: number) => {
    if (aspect >= 1) {
      lookDown = 0.05
      model.set(1.5, -0.1, 0)
      cardAt.set(-2.75, 0.2, 0)
      scale = 1.7
      cardSize = 2.3
      dist = Math.max(8.6, 13.6 / aspect)
    } else {
      model.set(0, -0.35, 0)
      cardAt.set(0, 2.95, 0)
      lookDown = 0.75
      scale = 1.5
      cardSize = 1.75
      dist = Math.max(13.4, 6.6 / aspect)
    }
  }
  layout(ctx.aspect)
  let last = -1

  return {
    poster: T_EACH * 0.7,
    resize({ aspect }) {
      layout(aspect)
    },
    update(t) {
      const cycle = Math.floor(t / T_EACH)
      const u = (t - cycle * T_EACH) / T_EACH
      const now = ((cycle % items.length) + items.length) % items.length
      const before = (((cycle - 1) % items.length) + items.length) % items.length
      if (now !== last) {
        last = now
        ctx.emit('model', now)
      }
      const build = ramp(u, 0.1, 0.5)
      const angle = t * 0.55

      items.forEach((it, i) => {
        const isNow = i === now
        // With one model only, it is both the one arriving and the one leaving.
        const leaving = !isNow && i === before && cycle > 0 && u < 0.14
        it.cloud.object.visible = isNow || leaving
        it.card.visible = isNow
        if (!it.cloud.object.visible) return
        it.cloud.object.position.copy(model)
        it.cloud.object.scale.setScalar(scale)
        it.cloud.turn(angle)
        it.cloud.time(t)
        if (isNow) {
          const w = cardSize * Math.min(1, it.shape)
          const h = cardSize * Math.min(1, 1 / it.shape)
          it.cloud.sheet((cardAt.x - model.x) / scale, (cardAt.y - model.y) / scale, 0, w / scale, h / scale)
          it.cloud.build(build)
          it.cloud.dissolve(0)
          // The card pops in, then dims once its dots have left.
          const arrive = easeBack(ramp(u, 0, 0.09))
          const bob = Math.sin(t * 0.9) * 0.05
          it.card.position.set(cardAt.x, cardAt.y + bob, -0.02)
          it.card.scale.set(w * arrive, h * arrive, 1)
          it.mat.opacity = ramp(u, 0, 0.06) * (1 - 0.55 * smooth(ramp(u, 0.3, 0.55))) * (1 - ramp(u, 0.96, 1))
          frame.position.set(cardAt.x, cardAt.y + bob, 0)
          frame.scale.set((w + 0.12) * arrive, (h + 0.12) * arrive, 1)
          ;(frame.material as T.LineBasicMaterial).opacity = 0.9 * (1 - ramp(u, 0.96, 1))
        } else {
          it.cloud.build(1)
          it.cloud.dissolve(ramp(u, 0, 0.14))
        }
      })

      // Turntable under the current model; the scan ring rises with the build.
      const it = items[now]
      table.position.set(model.x, model.y + it.lo * scale - 0.03, model.z)
      table.scale.setScalar(scale)
      base.rotation.y = angle
      outer.rotation.y = -angle * 0.5
      const rising = build > 0 && build < 1
      scan.position.y = (it.hi - it.lo) * easeInOut(build) + 0.03
      ;(scan.material as T.LineBasicMaterial).opacity = rising ? 0.95 * Math.sin(build * Math.PI) ** 0.5 : 0
      scan.scale.setScalar(0.75 + 0.25 * Math.sin(build * Math.PI))

      let k = 0
      dust.forEach((d, i) => lights.set(k++, d.x + Math.sin(t * 0.2 + i) * 0.3, d.y + Math.cos(t * 0.17 + i * 2) * 0.2, d.z, d.c, d.s, P.additive ? 0.35 : 0.16))
      for (let i = 0; i < 6; i++) {
        const a = -angle * 0.5 + (i * Math.PI) / 3
        lights.set(k++, table.position.x + Math.cos(a) * 1.3 * scale, table.position.y, Math.sin(a) * 1.3 * scale, i % 2 ? sky : pink, 0.1, 0.95)
      }
      lights.set(k++, table.position.x, table.position.y, 0, pink, 4.2, (P.additive ? 0.16 : 0.07) + (rising ? 0.12 : 0))
      lights.hide(k++)
      lights.commit()

      // A slow sway, so near and far things slide past each other.
      cam.position.set(Math.sin(t * 0.25) * 0.5, 0.55 + Math.sin(t * 0.19) * 0.15, dist)
      cam.lookAt(0, (model.y + cardAt.y) / 2 - lookDown, 0)
    },
  }
}

export default assemble
