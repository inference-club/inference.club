// "Every kind of signal": six lanes flowing left to right, one per thing the
// club makes, each drawn as what it is rather than as an icon.
//
//   text    words as small bars, brighter when the model was surer
//   image   scattered tiles settling into a real generated picture
//   speech  a voice's waveform, in bursts
//   music   bars moving on a beat
//   video   a strip of frames (real pictures) sliding past
//   shape   wireframe solids turning as they travel
//
// The view is flat (orthographic) and LANES world units tall with the lanes
// evenly spaced, so HTML labels placed at (i + 0.5) / 6 of the height line up.

import type * as T from 'three'
import { flatCamera, ramp, sampleImage, seeded, smooth, type SceneFactory } from '../stage'
import { SIGNALS, signalColor } from '../theme'

export interface SignalsOptions {
  /** Real generated pictures: used for the mosaic and the film strip. */
  art: string[]
}

const LANE = 2 // world units between lanes
const HEIGHT = SIGNALS.length * LANE
const GRID = 12 // mosaic tiles per side

const signals: SceneFactory<SignalsOptions> = async (ctx) => {
  const { THREE, palette: P, scene } = ctx
  const cam = flatCamera(ctx, HEIGHT)
  const rnd = seeded(7)
  const laneY = (i: number) => HEIGHT / 2 - LANE / 2 - i * LANE
  const color = (s: (typeof SIGNALS)[number]) => new THREE.Color(signalColor(P, s))
  // Half the visible width; lanes span a little more than the view.
  let half = (HEIGHT / 2) * ctx.aspect
  const span = () => half * 2 + 3
  const wrap = (x: number) => ((((x + span() / 2) % span()) + span()) % span()) - span() / 2

  // Hairline under each lane.
  const rules = new THREE.LineSegments(
    ctx.keep(new THREE.BufferGeometry()),
    ctx.keep(new THREE.LineBasicMaterial({ color: P.line, transparent: true, opacity: 0.55 })),
  )
  scene.add(rules)
  const layRules = () => {
    const pts: number[] = []
    SIGNALS.forEach((_, i) => pts.push(-half - 2, laneY(i) - LANE / 2 + 0.02, -1, half + 2, laneY(i) - LANE / 2 + 0.02, -1))
    rules.geometry.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
  }

  const dummy = new THREE.Object3D()
  const quad = ctx.keep(new THREE.PlaneGeometry(1, 1))

  // ── text: words as bars ───────────────────────────────────────────────────
  const WORDS = 26
  const words = new THREE.InstancedMesh(quad, ctx.glow('#ffffff'), WORDS)
  const wordData = Array.from({ length: WORDS }, () => ({ w: 0.25 + rnd() * 0.85, sure: 0.3 + rnd() * 0.7 }))
  let cursor = 0
  const wordX = wordData.map((d) => { const x = cursor; cursor += d.w + 0.16; return x })
  const wordSpan = cursor
  wordData.forEach((d, i) => words.setColorAt(i, color('text').multiplyScalar(P.additive ? d.sure : 1).lerp(new THREE.Color(P.ground), P.additive ? 0 : 1 - d.sure)))
  scene.add(words)

  // ── image: tiles settle into a picture ────────────────────────────────────
  const TILES = GRID * GRID
  const tiles = new THREE.InstancedMesh(quad, ctx.keep(new THREE.MeshBasicMaterial({ transparent: true })), TILES)
  const tileFrom = Array.from({ length: TILES }, () => ({ x: -(2 + rnd() * 5), y: (rnd() - 0.5) * 1.5, d: rnd() * 0.45, c: new THREE.Color().setHSL(rnd(), 0.5, P.additive ? 0.45 : 0.6) }))
  const pictures: T.Color[][] = []
  const fallback = Array.from({ length: TILES }, (_, k) => color('image').multiplyScalar(0.35 + 0.65 * ((k % GRID) / GRID)))
  scene.add(tiles)

  // ── speech: a waveform in bursts ──────────────────────────────────────────
  const WAVE = 220
  const wavePos = new Float32Array(WAVE * 3)
  const waveGeo = ctx.keep(new THREE.BufferGeometry())
  waveGeo.setAttribute('position', new THREE.BufferAttribute(wavePos, 3))
  const wave = new THREE.Line(waveGeo, ctx.keep(new THREE.LineBasicMaterial({ color: signalColor(P, 'speech'), transparent: true, opacity: 0.95 })))
  scene.add(wave)

  // ── music: bars on a beat ─────────────────────────────────────────────────
  const BARS = 64
  const bars = new THREE.InstancedMesh(quad, ctx.glow(signalColor(P, 'music'), 0.9), BARS)
  const barSeed = Array.from({ length: BARS }, () => rnd())
  scene.add(bars)

  // ── video: a strip of frames ──────────────────────────────────────────────
  const loader = new THREE.TextureLoader()
  const FRAMES = 7
  const frameW = 1.5
  const frameGap = 0.2
  const frames = Array.from({ length: FRAMES }, (_, i) => {
    const m = ctx.keep(new THREE.MeshBasicMaterial({ color: signalColor(P, 'video'), transparent: true, opacity: 0.35 }))
    const src = ctx.options.art[i % Math.max(1, ctx.options.art.length)]
    if (src) {
      loader.load(src, (tex) => {
        tex.colorSpace = THREE.SRGBColorSpace
        m.map = ctx.keep(tex)
        m.color.set('#ffffff')
        m.opacity = 1
        m.needsUpdate = true
      })
    }
    const mesh = new THREE.Mesh(ctx.keep(new THREE.PlaneGeometry(frameW, frameW * 0.6)), m)
    scene.add(mesh)
    return mesh
  })
  // Sprocket holes above and below the strip.
  const HOLES = 60
  const holes = new THREE.InstancedMesh(quad, ctx.glow(signalColor(P, 'video'), 0.7), HOLES * 2)
  scene.add(holes)

  // ── shape: wireframe solids ───────────────────────────────────────────────
  const solids = [
    new THREE.IcosahedronGeometry(0.62, 0),
    new THREE.TorusKnotGeometry(0.4, 0.12, 30, 5),
    new THREE.OctahedronGeometry(0.66, 0),
    new THREE.TorusGeometry(0.46, 0.18, 8, 18),
    new THREE.DodecahedronGeometry(0.58, 0),
  ].map((geo, i) => {
    ctx.keep(geo)
    const wire = new THREE.LineSegments(
      ctx.keep(new THREE.WireframeGeometry(geo)),
      ctx.keep(new THREE.LineBasicMaterial({ color: signalColor(P, 'shape'), transparent: true, opacity: 0.9 })),
    )
    wire.userData.offset = i * 3.4
    scene.add(wire)
    return wire
  })

  // Load pictures for the mosaic (the scene runs with flat colour until then).
  Promise.all(ctx.options.art.slice(0, 4).map((src) => sampleImage(src, GRID, GRID))).then((all) => {
    all.forEach((data) => {
      if (!data) return
      pictures.push(Array.from({ length: TILES }, (_, k) => new THREE.Color().setRGB(data[k * 4] / 255, data[k * 4 + 1] / 255, data[k * 4 + 2] / 255, THREE.SRGBColorSpace)))
    })
  })

  const tmp = new THREE.Color()
  const SPEED = 1.25

  return {
    poster: 3.4,
    resize({ aspect }) {
      ;(cam.userData.fit as (a: number) => void)(aspect)
      half = (HEIGHT / 2) * aspect
      layRules()
    },
    update(t) {
      // text
      const yText = laneY(0)
      wordData.forEach((d, i) => {
        let x = ((wordX[i] + t * SPEED) % wordSpan) - wordSpan / 2
        // Repeat the run of words if the view is wider than one run.
        if (wordSpan < span()) x = wrap(x)
        dummy.position.set(x + d.w / 2, yText, 0)
        dummy.rotation.set(0, 0, 0)
        dummy.scale.set(d.w, 0.3, 1)
        dummy.updateMatrix()
        words.setMatrixAt(i, dummy.matrix)
      })
      words.instanceMatrix.needsUpdate = true

      // image: assemble (0–3s), hold, slide away, next picture
      const CYCLE = 6.5
      const phase = (t % CYCLE) / CYCLE
      const picture = pictures.length ? pictures[Math.floor(t / CYCLE) % pictures.length] : fallback
      const yImg = laneY(1)
      const size = 1.56 / GRID
      const cx = Math.min(half * 0.35, 2.2)
      const leave = smooth(ramp(phase, 0.8, 1)) * (half + 3)
      for (let k = 0; k < TILES; k++) {
        const f = tileFrom[k]
        const p = smooth(ramp(phase, f.d * 0.5, 0.42 + f.d * 0.5))
        const tx = cx + ((k % GRID) - GRID / 2 + 0.5) * size
        const ty = yImg - (Math.floor(k / GRID) - GRID / 2 + 0.5) * size
        dummy.position.set(cx + f.x * (1 - p) * (half / 5) + (tx - cx) * p + leave, yImg + f.y * (1 - p) + (ty - yImg) * p, 0)
        dummy.rotation.set(0, 0, (1 - p) * (f.d * 6 - 1.3))
        dummy.scale.setScalar(size * (0.55 + 0.47 * p))
        dummy.updateMatrix()
        tiles.setMatrixAt(k, dummy.matrix)
        tiles.setColorAt(k, tmp.copy(f.c).lerp(picture[k], p))
      }
      tiles.instanceMatrix.needsUpdate = true
      if (tiles.instanceColor) tiles.instanceColor.needsUpdate = true

      // speech
      const ySpeech = laneY(2)
      for (let i = 0; i < WAVE; i++) {
        const x = -half - 1 + (i / (WAVE - 1)) * (half * 2 + 2)
        const s = x - t * SPEED * 1.6
        const burst = Math.pow(Math.max(0, Math.sin(s * 0.55) * Math.sin(s * 0.21 + 1.3)), 0.7)
        wavePos[i * 3] = x
        wavePos[i * 3 + 1] = ySpeech + burst * 0.72 * Math.sin(s * 9.5) * (0.6 + 0.4 * Math.sin(s * 23.1))
        wavePos[i * 3 + 2] = 0
      }
      waveGeo.attributes.position.needsUpdate = true

      // music: 110 beats a minute
      const yMusic = laneY(3) - 0.72
      const beat = (t * 110) / 60
      const kick = Math.exp(-(beat % 1) * 5)
      const step = (half * 2 + 2) / BARS
      for (let i = 0; i < BARS; i++) {
        const n = barSeed[i]
        const h = 0.12 + (0.25 + 0.75 * Math.abs(Math.sin(beat * Math.PI * (0.5 + (i % 4) * 0.25) + n * 6))) * (0.35 + n * 0.75) * (0.7 + 0.5 * kick)
        dummy.position.set(-half - 1 + (i + 0.5) * step, yMusic + h / 2, 0)
        dummy.rotation.set(0, 0, 0)
        dummy.scale.set(step * 0.5, h, 1)
        dummy.updateMatrix()
        bars.setMatrixAt(i, dummy.matrix)
      }
      bars.instanceMatrix.needsUpdate = true

      // video
      const yVideo = laneY(4)
      const stripSpan = Math.max(FRAMES * (frameW + frameGap), span())
      frames.forEach((mesh, i) => {
        const x = ((i * (stripSpan / FRAMES) + t * SPEED * 0.8) % stripSpan) - stripSpan / 2
        mesh.position.set(x, yVideo, 0)
      })
      const holeStep = (half * 2 + 2) / HOLES
      for (let i = 0; i < HOLES; i++) {
        const x = -half - 1 + ((i * holeStep + t * SPEED * 0.8) % (half * 2 + 2))
        for (let row = 0; row < 2; row++) {
          dummy.position.set(x, yVideo + (row ? 0.62 : -0.62), 0)
          dummy.rotation.set(0, 0, 0)
          dummy.scale.set(0.09, 0.07, 1)
          dummy.updateMatrix()
          holes.setMatrixAt(i * 2 + row, dummy.matrix)
        }
      }
      holes.instanceMatrix.needsUpdate = true

      // shape
      const yShape = laneY(5)
      const solidSpan = Math.max(solids.length * 3.4, span())
      solids.forEach((wire, i) => {
        wire.position.set(((wire.userData.offset * (solidSpan / (solids.length * 3.4)) + t * SPEED * 0.7) % solidSpan) - solidSpan / 2, yShape, 0)
        wire.rotation.set(t * 0.5 + i, t * 0.7 + i * 2, 0)
      })
    },
  }
}

export default signals
