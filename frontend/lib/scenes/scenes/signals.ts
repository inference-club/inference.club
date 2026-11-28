// "Every kind of signal": six lanes flowing left to right, one per thing the
// club makes. A third of the way across is a bright vertical line: the
// machine. Left of it each lane is raw material; as it crosses the line it
// becomes the thing itself.
//
//   text    loose tokens become words; where the model was unsure, the word
//           it did not pick falls away
//   image   noise settles into a real generated picture
//   speech  a flat line of dots becomes a voice's waveform
//   music   a quiet pulse becomes bars moving on a beat
//   video   blank film becomes consecutive frames of a real picture
//   shape   a loose cloud of points becomes a real generated 3D model
//
// The view is flat (orthographic) and LANES world units tall with the lanes
// evenly spaced, so HTML labels placed at (i + 0.5) / 6 of the height line up.

import type * as T from 'three'
import {
  easeBack, hash, loadPoints, modelCloud, ramp, sampleImage, seeded, smooth, sparks, flatCamera,
  type ModelCloud, type SceneFactory,
} from '../stage'
import { SIGNALS, signalColor } from '../theme'

export interface SignalsOptions {
  /** Real generated pictures: used for the image lane and the film strip. */
  art: string[]
  /** Real generated 3D models as point files (see scripts/showcase/mesh_points.py). */
  models?: string[]
}

const LANE = 2 // world units between lanes
const HEIGHT = SIGNALS.length * LANE
const SPEED = 1.05 // world units a second, left to right

const GRID = 12 // picture tiles per side
const CARD = 1.5
const CARD_PITCH = 3.3
const CARDS = 10

const FRAME_W = 1.5
const FRAME_H = 0.9
const FRAME_PITCH = FRAME_W + 0.14
const FRAMES = 20

const SHAPE_PITCH = 3.6
const SHAPES = 9

const signals: SceneFactory<SignalsOptions> = async (ctx) => {
  const { THREE, palette: P, scene } = ctx
  const cam = flatCamera(ctx, HEIGHT)
  const rnd = seeded(7)
  const laneY = (i: number) => HEIGHT / 2 - LANE / 2 - i * LANE
  const hue = (s: (typeof SIGNALS)[number]) => new THREE.Color(signalColor(P, s))
  const ground = new THREE.Color(P.ground)
  const ink = new THREE.Color(P.ink)
  const tmp = new THREE.Color()
  const tmp2 = new THREE.Color()
  const white = new THREE.Color('#ffffff')
  const hues = Object.fromEntries(SIGNALS.map((s) => [s, hue(s)])) as Record<(typeof SIGNALS)[number], T.Color>
  /** `base` at strength k: dimmer light at night, paler ink on paper. */
  const tone = (base: T.Color, k: number) => (P.additive ? tmp.copy(base).multiplyScalar(k) : tmp.copy(ground).lerp(base, k))

  let half = (HEIGHT / 2) * ctx.aspect // half the visible width
  let gate = -half * 0.38 // where raw becomes made
  const span = () => half * 2 + 3
  /** Position on a strip of length `period` that slides right for ever. */
  const slide = (offset: number, t: number, period: number) => ((((offset + t * SPEED) % period) + period) % period) - period / 2

  const flat = (color: string | T.Color, opacity = 1) =>
    ctx.keep(new THREE.MeshBasicMaterial({ color, transparent: true, opacity, depthTest: false, depthWrite: false }))
  const quad = ctx.keep(new THREE.PlaneGeometry(1, 1))
  const dummy = new THREE.Object3D()
  const place = (mesh: T.InstancedMesh, i: number, x: number, y: number, w: number, h: number, rot = 0) => {
    dummy.position.set(x, y, 0)
    dummy.rotation.set(0, 0, rot)
    dummy.scale.set(w, h, 1)
    dummy.updateMatrix()
    mesh.setMatrixAt(i, dummy.matrix)
  }
  const instanced = (count: number, material: T.Material, order: number) => {
    const mesh = new THREE.InstancedMesh(quad, material, count)
    mesh.renderOrder = order
    mesh.frustumCulled = false
    for (let i = 0; i < count; i++) {
      place(mesh, i, 0, 0, 0, 0)
      mesh.setColorAt(i, ink)
    }
    scene.add(mesh)
    return mesh
  }

  // ── backdrop: slow dust behind everything, and the lane rules ─────────────
  const DUST = 70
  const dust = sparks(ctx, DUST)
  dust.object.renderOrder = 0
  scene.add(dust.object)
  const dustData = Array.from({ length: DUST }, () => ({ x: rnd() * 40, y: (rnd() - 0.5) * HEIGHT, v: 0.15 + rnd() * 0.3, s: 0.08 + rnd() * 0.2, c: SIGNALS[Math.floor(rnd() * 6)] }))

  const rules = new THREE.LineSegments(
    ctx.keep(new THREE.BufferGeometry()),
    ctx.keep(new THREE.LineBasicMaterial({ color: P.line, transparent: true, opacity: 0.6, depthTest: false })),
  )
  rules.renderOrder = 1
  scene.add(rules)
  const gateLine = new THREE.Mesh(quad, flat(P.ink, P.additive ? 0.5 : 0.35))
  gateLine.renderOrder = 30
  scene.add(gateLine)
  const gateGlow = sparks(ctx, SIGNALS.length * 2)
  gateGlow.object.renderOrder = 31
  scene.add(gateGlow.object)

  const layout = () => {
    gate = -half * 0.38
    const pts: number[] = []
    SIGNALS.forEach((_, i) => pts.push(-half - 2, laneY(i) - LANE / 2, 0, half + 2, laneY(i) - LANE / 2, 0))
    rules.geometry.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
    gateLine.position.set(gate, 0, 0)
    gateLine.scale.set(0.035, HEIGHT, 1)
  }

  // ── text: tokens become words ─────────────────────────────────────────────
  const WORDS = 40
  const wordData = Array.from({ length: WORDS }, () => ({ w: 0.3 + rnd() * 0.8, sure: rnd(), tokens: 1 + Math.floor(rnd() * 3) }))
  let cursor = 0
  const wordX = wordData.map((d) => { const x = cursor; cursor += d.w + 0.2; return x })
  const wordSpan = cursor
  const words = instanced(WORDS * 2, ctx.glow('#ffffff'), 10)
  const ghosts = instanced(WORDS * 2, ctx.glow('#ffffff'), 10)
  const tokens = sparks(ctx, WORDS * 2 * 3, { hard: 0.5 })
  tokens.object.renderOrder = 9
  scene.add(tokens.object)
  const cText = hue('text')
  const cDoubt = new THREE.Color(P.coral)

  // ── image: noise settles into a picture ───────────────────────────────────
  const TILES = GRID * GRID
  const tiles = instanced(CARDS * TILES, flat('#ffffff'), 10)
  const tileData = Array.from({ length: TILES }, () => ({ d: rnd() * 0.4, jx: rnd() - 0.5, jy: rnd() - 0.5, h: rnd() }))
  const pictures: T.Color[][] = []
  const cImage = hue('image')
  const fallback = Array.from({ length: TILES }, (_, k) => cImage.clone().multiplyScalar(0.4 + 0.6 * ((k % GRID) / GRID)))
  const loader = new THREE.TextureLoader()
  const textures: Array<T.Texture | null> = ctx.options.art.map(() => null)
  ctx.options.art.forEach((src, i) => {
    loader.load(src, (tex) => {
      tex.colorSpace = THREE.SRGBColorSpace
      textures[i] = ctx.keep(tex)
    })
  })
  const cardGeo = ctx.keep(new THREE.PlaneGeometry(CARD, CARD))
  const cards = Array.from({ length: CARDS }, () => {
    const mesh = new THREE.Mesh(cardGeo, flat('#ffffff', 0))
    mesh.renderOrder = 11
    mesh.visible = false
    scene.add(mesh)
    return { mesh, shown: -1 }
  })

  // ── speech: dots become a waveform ────────────────────────────────────────
  const TICKS = 280
  const TICK_STEP = 0.105
  const ticks = instanced(TICKS, ctx.glow('#ffffff'), 10)
  const cSpeech = hue('speech')

  // ── music: bars on a beat ─────────────────────────────────────────────────
  const BARS = 90
  const BAR_STEP = 0.32
  const bars = instanced(BARS, ctx.glow('#ffffff'), 10)
  const caps = instanced(BARS, ctx.glow('#ffffff'), 11)
  const barSeed = Array.from({ length: BARS }, () => rnd())
  const cMusic = hue('music')
  const cMusic2 = new THREE.Color(P.pink)
  const beatAt = (t: number) => (t * 112) / 60
  const barHeight = (i: number, x: number, t: number) => {
    const beat = beatAt(t) - x * 0.18 // the pattern travels to the right
    const kick = Math.exp(-(((beat % 1) + 1) % 1) * 4.5)
    const n = barSeed[i]
    return 0.1 + (0.2 + 0.8 * Math.abs(Math.sin(beat * Math.PI * (0.5 + (i % 4) * 0.25) + n * 6))) * (0.3 + n * 0.7) * (0.55 + 0.75 * kick)
  }

  // ── video: a strip of consecutive frames ──────────────────────────────────
  const cVideo = hue('video')
  const film = new THREE.Mesh(quad, flat(P.additive ? P.line : P.dim, P.additive ? 0.85 : 0.5))
  film.renderOrder = 8
  scene.add(film)
  const HOLES = 130
  const HOLE_STEP = 0.27
  const holes = instanced(HOLES * 2, flat('#ffffff'), 9)
  const frames = Array.from({ length: FRAMES }, () => {
    const geo = ctx.keep(new THREE.PlaneGeometry(FRAME_W, FRAME_H))
    const mesh = new THREE.Mesh(geo, flat('#ffffff'))
    mesh.renderOrder = 10
    scene.add(mesh)
    return { mesh, geo, mat: mesh.material as T.MeshBasicMaterial, shown: -1 }
  })
  /** Crop the picture to the frame's shape, panning a little more each frame. */
  const crop = (geo: T.BufferGeometry, tex: T.Texture, step: number) => {
    const img = tex.image as { width: number; height: number }
    const want = FRAME_W / FRAME_H
    const have = img.width / img.height
    const w = Math.min(1, want / have) * 0.78
    const h = Math.min(1, have / want) * 0.78
    const u0 = (1 - w) * (0.15 + 0.23 * step)
    const v0 = (1 - h) * (0.6 - 0.06 * step)
    const uv = geo.attributes.uv as T.BufferAttribute
    uv.setXY(0, u0, v0 + h); uv.setXY(1, u0 + w, v0 + h); uv.setXY(2, u0, v0); uv.setXY(3, u0 + w, v0)
    uv.needsUpdate = true
  }

  // ── shape: a cloud of points becomes a model ──────────────────────────────
  const shapes: Array<{ cloud: ModelCloud | null; wire: T.LineSegments | null; ring: T.LineLoop }> = []
  const ringGeo = ctx.keep(new THREE.BufferGeometry().setFromPoints(
    Array.from({ length: 48 }, (_, i) => new THREE.Vector3(Math.cos((i / 48) * Math.PI * 2) * 0.72, Math.sin((i / 48) * Math.PI * 2) * 0.13, 0)),
  ))
  const ringMat = ctx.keep(new THREE.LineBasicMaterial({ color: P.pink, transparent: true, opacity: 0.55, depthTest: false }))
  const solids = [new THREE.IcosahedronGeometry(0.66, 0), new THREE.TorusKnotGeometry(0.42, 0.13, 40, 6), new THREE.OctahedronGeometry(0.7, 0)]
    .map((g) => { ctx.keep(g); return ctx.keep(new THREE.WireframeGeometry(g)) })
  const wireMat = ctx.keep(new THREE.LineBasicMaterial({ color: P.pink, transparent: true, opacity: 0.9, depthTest: false }))
  const models = (await Promise.all((ctx.options.models ?? []).map((src) => loadPoints(src, 5000)))).filter((m) => m !== null)
  for (let i = 0; i < SHAPES; i++) {
    const ring = new THREE.LineLoop(ringGeo, ringMat)
    ring.renderOrder = 10
    scene.add(ring)
    let cloud: ModelCloud | null = null
    let wire: T.LineSegments | null = null
    if (models.length) {
      cloud = modelCloud(ctx, models[i % models.length]!, { size: 0.052, seed: 40 + i })
      cloud.object.scale.setScalar(0.84)
      cloud.object.renderOrder = 20
      scene.add(cloud.object)
    } else {
      // No model could be loaded: turn a plain wireframe solid instead.
      wire = new THREE.LineSegments(solids[i % solids.length], wireMat)
      wire.renderOrder = 20
      scene.add(wire)
    }
    shapes.push({ cloud, wire, ring })
  }

  // Colours for the picture tiles (the lane runs in flat colour until loaded).
  Promise.all(ctx.options.art.map((src) => sampleImage(src, GRID, GRID))).then((all) => {
    all.forEach((data, i) => {
      pictures[i] = data
        ? Array.from({ length: TILES }, (_, k) => new THREE.Color().setRGB(data[k * 4] / 255, data[k * 4 + 1] / 255, data[k * 4 + 2] / 255, THREE.SRGBColorSpace))
        : fallback
    })
  })
  const nArt = Math.max(1, ctx.options.art.length)

  return {
    poster: 7.3,
    resize({ aspect }) {
      ;(cam.userData.fit as (a: number) => void)(aspect)
      half = (HEIGHT / 2) * aspect
      layout()
    },
    update(t) {
      const edge = half + 1.6
      // How far past the line something is, as 0→1 over `reach` world units.
      const made = (x: number, reach: number) => ramp(x, gate, gate + reach)

      // backdrop
      dustData.forEach((d, i) => {
        const x = (((d.x + t * d.v) % 40) + 40) % 40 - 20
        dust.set(i, x, d.y + Math.sin(t * 0.3 + i) * 0.15, 0, tone(hues[d.c], 0.9), d.s, P.additive ? 0.22 : 0.12)
      })
      dust.commit()
      SIGNALS.forEach((s, i) => {
        const pulse = 0.6 + 0.4 * Math.sin(t * 2.4 + i * 1.3)
        gateGlow.set(i * 2, gate, laneY(i), 0, hues[s], 0.9, (P.additive ? 0.3 : 0.16) * pulse)
        gateGlow.set(i * 2 + 1, gate, laneY(i), 0, hues[s], 0.2, 0.95)
      })
      gateGlow.commit()

      // text
      const yText = laneY(0)
      for (let k = 0; k < WORDS * 2; k++) {
        const d = wordData[k % WORDS]
        const left = slide(wordX[k % WORDS] + (k >= WORDS ? wordSpan : 0), t, wordSpan * 2)
        const right = left + d.w
        const from = Math.max(left, gate)
        const shown = right > gate && left < edge
        // The written part of the word: from the line to its leading edge.
        if (shown) place(words, k, (from + right) / 2, yText, right - from, 0.26)
        else place(words, k, 0, 0, 0, 0)
        words.setColorAt(k, tone(cText, 0.35 + 0.65 * d.sure))
        // An unsure word carries the alternative it did not pick, which drops away.
        const doubt = d.sure < 0.4 && right > gate ? 1 - made(left, 2.2) : 0
        if (doubt > 0.01 && shown) place(ghosts, k, (from + right) / 2, yText + 0.4 + (1 - doubt) * 0.35, (right - from) * 0.8, 0.16)
        else place(ghosts, k, 0, 0, 0, 0)
        ghosts.setColorAt(k, tone(cDoubt, 0.75 * doubt))
        // Its tokens, still loose, on the way to the line.
        for (let j = 0; j < 3; j++) {
          const x = left + (d.w * (j + 0.5)) / d.tokens
          const on = j < d.tokens && x < gate && x > -edge
          if (on) tokens.set(k * 3 + j, x, yText + Math.sin(t * 3 + k + j * 2) * 0.09, 0, cText, 0.17, 0.35 + 0.6 * ramp(x, -edge, gate))
          else tokens.hide(k * 3 + j)
        }
      }
      words.instanceMatrix.needsUpdate = true
      ghosts.instanceMatrix.needsUpdate = true
      words.instanceColor!.needsUpdate = true
      ghosts.instanceColor!.needsUpdate = true
      tokens.commit()

      // image
      const yImg = laneY(1)
      const cardPeriod = Math.max(CARDS * CARD_PITCH, span())
      const tile = CARD / GRID
      const flicker = Math.floor(t * 9)
      cards.forEach((card, c) => {
        const offset = c * (cardPeriod / CARDS)
        const x = slide(offset, t, cardPeriod)
        const pass = Math.floor((offset + t * SPEED) / cardPeriod)
        const which = (((c + pass * 3) % nArt) + nArt) % nArt
        const visible = Math.abs(x) < edge
        const p = made(x - CARD * 0.2, 3.2) // 0 noise … 1 picture
        const picture = pictures[which] ?? fallback
        for (let k = 0; k < TILES; k++) {
          const i = c * TILES + k
          if (!visible) { place(tiles, i, 0, 0, 0, 0); continue }
          const f = tileData[k]
          const q = smooth(ramp(p, f.d, f.d + 0.6))
          const tx = x + ((k % GRID) - GRID / 2 + 0.5) * tile
          const ty = yImg - (Math.floor(k / GRID) - GRID / 2 + 0.5) * tile
          const s = tile * (0.62 + 0.4 * q)
          place(tiles, i, tx + f.jx * 0.12 * (1 - q), ty + f.jy * 0.12 * (1 - q), s, s)
          const n = hash(k * 7.3 + c * 31 + flicker * (0.5 + f.h))
          tmp.setHSL(n, P.additive ? 0.75 : 0.6, P.additive ? 0.32 + 0.3 * f.h : 0.62 + 0.2 * f.h)
          tiles.setColorAt(i, tmp.lerp(picture[k], q))
        }
        // The real picture fades in over the settled tiles, with a small pop.
        const tex = textures[which]
        const sharp = ramp(p, 0.9, 1)
        card.mesh.visible = visible && sharp > 0 && !!tex
        if (card.mesh.visible) {
          const mat = card.mesh.material as T.MeshBasicMaterial
          if (card.shown !== which) {
            mat.map = tex
            mat.needsUpdate = true
            card.shown = which
          }
          mat.opacity = sharp
          card.mesh.position.set(x, yImg + Math.sin(t * 1.1 + c) * 0.04, 0)
          card.mesh.scale.setScalar(0.94 + 0.1 * easeBack(made(x - CARD * 0.2 - 2.9, 1.1)))
        }
      })
      tiles.instanceMatrix.needsUpdate = true
      tiles.instanceColor!.needsUpdate = true

      // speech
      const ySpeech = laneY(2)
      for (let i = 0; i < TICKS; i++) {
        const x = -half - 1 + i * TICK_STEP
        if (x > edge) { place(ticks, i, 0, 0, 0, 0); continue }
        const s = x - t * SPEED * 1.5
        const phrase = Math.pow(Math.max(0, Math.sin(s * 0.5) * Math.sin(s * 0.19 + 1.3), 0.8 * Math.sin(s * 0.37 + 2.1) * Math.sin(s * 0.83)), 0.6)
        const detail = 0.3 + 0.7 * Math.abs(Math.sin(s * 7.3) * Math.sin(s * 2.9 + 0.6))
        const voiced = made(x, 0.9)
        const a = 0.035 + phrase * detail * 0.78 * voiced
        place(ticks, i, x, ySpeech, 0.05, a * 2)
        ticks.setColorAt(i, tone(cSpeech, 0.3 + 0.7 * Math.min(1, a * 2.2)))
      }
      ticks.instanceMatrix.needsUpdate = true
      ticks.instanceColor!.needsUpdate = true

      // music
      const yMusic = laneY(3) - 0.74
      for (let i = 0; i < BARS; i++) {
        const x = -half - 1 + (i + 0.5) * BAR_STEP
        if (x > edge) { place(bars, i, 0, 0, 0, 0); place(caps, i, 0, 0, 0, 0); continue }
        const loud = 0.12 + 0.88 * made(x, 1.2)
        const h = barHeight(i, x, t) * loud * 1.25
        // The cap rides the recent peak and sinks slowly.
        const peak = Math.max(h, barHeight(i, x, t - 0.09) * loud * 1.25 - 0.03, barHeight(i, x, t - 0.18) * loud * 1.25 - 0.07, barHeight(i, x, t - 0.27) * loud * 1.25 - 0.12)
        place(bars, i, x, yMusic + h / 2, BAR_STEP * 0.62, h)
        place(caps, i, x, yMusic + peak + 0.06, BAR_STEP * 0.62, 0.045)
        const mix = 0.5 + 0.5 * Math.sin(x * 0.5 - t * 0.8)
        tmp2.copy(cMusic).lerp(cMusic2, mix)
        bars.setColorAt(i, tone(tmp2, 0.35 + 0.6 * loud))
        caps.setColorAt(i, tone(tmp2, loud))
      }
      bars.instanceMatrix.needsUpdate = true
      caps.instanceMatrix.needsUpdate = true
      bars.instanceColor!.needsUpdate = true
      caps.instanceColor!.needsUpdate = true

      // video
      const yVideo = laneY(4)
      film.position.set(0, yVideo, 0)
      film.scale.set(half * 2 + 4, FRAME_H + 0.5, 1)
      const holePeriod = HOLES * HOLE_STEP
      for (let i = 0; i < HOLES; i++) {
        const x = slide(i * HOLE_STEP, t, holePeriod)
        for (let row = 0; row < 2; row++) {
          if (Math.abs(x) > edge) place(holes, i * 2 + row, 0, 0, 0, 0)
          else place(holes, i * 2 + row, x, yVideo + (row ? 1 : -1) * (FRAME_H / 2 + 0.125), 0.11, 0.09)
          holes.setColorAt(i * 2 + row, ground)
        }
      }
      holes.instanceMatrix.needsUpdate = true
      holes.instanceColor!.needsUpdate = true
      const framePeriod = FRAMES * FRAME_PITCH
      frames.forEach((f, i) => {
        const offset = i * FRAME_PITCH
        const x = slide(offset, t, framePeriod)
        const pass = Math.floor((offset + t * SPEED) / framePeriod)
        // Four frames in a row come from the same picture: a clip.
        const clip = Math.floor(i / 4) + pass * 5
        const which = ((clip % nArt) + nArt) % nArt
        const tex = textures[which]
        f.mesh.position.set(x, yVideo, 0)
        f.mesh.visible = Math.abs(x) < edge
        const key = which * 4 + (i % 4)
        if (tex && f.shown !== key) {
          f.mat.map = tex
          f.mat.needsUpdate = true
          crop(f.geo, tex, i % 4)
          f.shown = key
        }
        // Blank film before the line, a rendered frame after it.
        const lit = made(x + FRAME_W / 2, FRAME_W)
        if (tex) f.mat.color.copy(ground).lerp(white, 0.12 + 0.88 * lit)
        else f.mat.color.copy(ground).lerp(cVideo, 0.15 + 0.5 * lit)
      })

      // shape
      const yShape = laneY(5)
      const shapePeriod = Math.max(SHAPES * SHAPE_PITCH, span())
      shapes.forEach((s, i) => {
        const x = slide(i * (shapePeriod / SHAPES), t, shapePeriod)
        const visible = Math.abs(x) < edge
        const built = made(x + 0.9, 2.6)
        s.ring.visible = visible
        s.ring.position.set(x, yShape - 0.8, 0)
        if (s.cloud) {
          s.cloud.object.visible = visible
          s.cloud.object.position.set(x, yShape + 0.04, 0)
          s.cloud.build(built)
          s.cloud.turn(t * 0.7 + i * 1.9)
          s.cloud.time(t)
        }
        if (s.wire) {
          s.wire.visible = visible
          s.wire.position.set(x, yShape, 0)
          s.wire.rotation.set(t * 0.5 + i, t * 0.7 + i * 2, 0)
          s.wire.scale.setScalar(0.35 + 0.65 * smooth(built))
        }
      })
    },
  }
}

export default signals
