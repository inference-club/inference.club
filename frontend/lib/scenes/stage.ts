// The stage every scene runs on. It owns the things scenes should not have to
// think about: loading three.js on demand, the renderer and its size, pausing
// off screen, reduced motion, the palette, and cleaning up.
//
// A scene is a function. It receives a StageContext, adds objects to
// `ctx.scene`, and returns `update(t, dt)`. See README.md for a walkthrough.

import type * as T from 'three'
import { paletteFor, type Palette } from './theme'

export interface StageContext<O = unknown> {
  THREE: typeof T
  scene: T.Scene
  /** Replace with your own camera if you need a different projection. */
  camera: T.Camera
  renderer: T.WebGLRenderer
  palette: Palette
  dark: boolean
  /** Current canvas size in CSS pixels. */
  width: number
  height: number
  aspect: number
  /** True when the person asked for reduced motion: one still frame is drawn. */
  still: boolean
  /** Whatever the caller passed as scene options. */
  options: O
  /** Register anything with dispose() so the stage frees it on unmount. */
  keep<X extends { dispose(): void }>(x: X): X
  /** A material in a palette colour that glows on night and inks on paper. */
  glow(color: string, opacity?: number): T.MeshBasicMaterial
  /** Tell the page something (for example a counter to show beside the canvas). */
  emit(name: string, value: unknown): void
}

export interface SceneInstance {
  /** Called every frame while visible. `t` is seconds since the scene began. */
  update(t: number, dt: number): void
  /** Called when the canvas changes size (and once at start). */
  resize?(ctx: { width: number; height: number; aspect: number }): void
  dispose?(): void
  /** The moment to draw for reduced motion (seconds). Default 6. */
  poster?: number
}

export type SceneFactory<O = unknown> = (ctx: StageContext<O>) => SceneInstance | Promise<SceneInstance>

export interface MountOptions<O> {
  dark: boolean
  options: O
  onEmit?: (name: string, value: unknown) => void
  onReady?: () => void
}

/** Mount `factory` into `el`. Resolves to a function that tears it down. */
export async function mountStage<O>(
  el: HTMLElement,
  factory: SceneFactory<O>,
  opts: MountOptions<O>,
): Promise<() => void> {
  const THREE: typeof T = await import('three')
  const palette = paletteFor(opts.dark)
  // The canvas is opaque and painted with the palette's ground colour. Lights
  // are drawn additively, and additive blending on a transparent canvas also
  // adds alpha, which shows unlit (black) marks as dark smudges over the page.
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'low-power' })
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.setClearColor(palette.ground, 1)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, el.clientWidth < 640 ? 1.5 : 2))
  renderer.domElement.style.cssText = 'display:block;width:100%;height:100%'
  el.appendChild(renderer.domElement)

  const trash: Array<{ dispose(): void }> = []
  const ctx: StageContext<O> = {
    THREE,
    scene: new THREE.Scene(),
    camera: new THREE.PerspectiveCamera(35, 1, 0.1, 200),
    renderer,
    palette,
    dark: opts.dark,
    width: el.clientWidth || 1,
    height: el.clientHeight || 1,
    aspect: (el.clientWidth || 1) / (el.clientHeight || 1),
    still: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    options: opts.options,
    keep: (x) => (trash.push(x), x),
    glow: (color, opacity = 1) => {
      const m = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity,
        depthWrite: false,
        blending: palette.additive ? THREE.AdditiveBlending : THREE.NormalBlending,
      })
      trash.push(m)
      return m
    },
    emit: (name, value) => opts.onEmit?.(name, value),
  }

  let instance: SceneInstance
  let dead = false
  try {
    instance = await factory(ctx)
  } catch (e) {
    renderer.dispose()
    renderer.domElement.remove()
    throw e
  }

  const resize = () => {
    const w = el.clientWidth
    const h = el.clientHeight
    if (!w || !h) return
    ctx.width = w
    ctx.height = h
    ctx.aspect = w / h
    renderer.setSize(w, h, false)
    const cam = ctx.camera as T.PerspectiveCamera
    if (cam.isPerspectiveCamera) {
      cam.aspect = ctx.aspect
      cam.updateProjectionMatrix()
    }
    instance.resize?.(ctx)
  }

  const clock = new THREE.Clock()
  let visible = true
  let raf = 0
  let elapsed = 0
  const frame = () => {
    raf = 0
    if (dead || !visible) return
    const dt = Math.min(clock.getDelta(), 0.05)
    elapsed += dt
    instance.update(ctx.still ? instance.poster ?? 6 : elapsed, ctx.still ? 0 : dt)
    renderer.render(ctx.scene, ctx.camera)
    if (!ctx.still) raf = requestAnimationFrame(frame)
  }
  const kick = () => {
    if (!raf && visible && !dead) raf = requestAnimationFrame(frame)
  }

  const ro = new ResizeObserver(() => {
    resize()
    kick()
  })
  ro.observe(el)
  const io = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting
    if (visible) {
      clock.getDelta() // drop the time spent off screen
      kick()
    }
  }, { rootMargin: '80px' })
  io.observe(el)

  resize()
  kick()
  opts.onReady?.()

  return () => {
    dead = true
    cancelAnimationFrame(raf)
    ro.disconnect()
    io.disconnect()
    instance.dispose?.()
    trash.forEach((x) => x.dispose())
    renderer.dispose()
    renderer.domElement.remove()
  }
}

// ── Small helpers scenes share ─────────────────────────────────────────────

/** Deterministic random numbers, so a scene looks the same on every visit. */
export function seeded(seed: number): () => number {
  let s = seed >>> 0
  return () => {
    s = (s + 0x6d2b79f5) >>> 0
    let x = Math.imul(s ^ (s >>> 15), 1 | s)
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296
  }
}

export const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
export const smooth = (x: number) => {
  const t = clamp01(x)
  return t * t * (3 - 2 * t)
}
/** 0→1 as `x` passes from `a` to `b`. */
export const ramp = (x: number, a: number, b: number) => clamp01((x - a) / (b - a))

/** Ease out: fast, then settling. */
export const easeOut = (x: number) => 1 - (1 - clamp01(x)) ** 3
/** Ease in and out, stronger than `smooth`. */
export const easeInOut = (x: number) => {
  const t = clamp01(x)
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2
}
/** Ease out with a small overshoot: things that pop into place. */
export const easeBack = (x: number) => {
  const t = clamp01(x) - 1
  return 1 + 2.70158 * t * t * t + 1.70158 * t * t
}
/** A fixed pseudo-random number in 0..1 for `n` (the same on every frame). */
export const hash = (n: number) => {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453
  return x - Math.floor(x)
}

/**
 * A cloud of round lights whose position, colour, size and opacity can each be
 * set every frame: sparks, trails, halos, nodes. One draw call. Sizes are in
 * world units and follow the camera (flat or perspective).
 *
 * `hard` is where the disc's edge starts to fade: 0 is a soft glow, 0.8 a
 * crisp dot.
 */
export interface Sparks {
  object: T.Points
  count: number
  set(i: number, x: number, y: number, z: number, color: T.Color, size: number, alpha?: number): void
  hide(i: number): void
  /** Call once per frame after the last `set`. */
  commit(): void
}
export function sparks(ctx: StageContext, count: number, opts: { hard?: number; depthTest?: boolean } = {}): Sparks {
  const { THREE } = ctx
  const pos = new Float32Array(count * 3)
  const col = new Float32Array(count * 3)
  const look = new Float32Array(count * 2) // size, alpha
  const geo = ctx.keep(new THREE.BufferGeometry())
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
  geo.setAttribute('look', new THREE.BufferAttribute(look, 2))
  const mat = ctx.keep(new THREE.ShaderMaterial({
    uniforms: { uScale: { value: 1 }, uPersp: { value: 0 }, uHard: { value: opts.hard ?? 0 } },
    vertexShader: `
      attribute vec3 color; attribute vec2 look;
      uniform float uScale, uPersp;
      varying vec3 vColor; varying float vAlpha;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_Position = projectionMatrix * mv;
        gl_PointSize = look.x * uScale * mix(1.0, 1.0 / max(0.001, -mv.z), uPersp);
        vColor = color; vAlpha = look.y;
      }`,
    fragmentShader: `
      uniform float uHard;
      varying vec3 vColor; varying float vAlpha;
      void main() {
        float d = length(gl_PointCoord - 0.5) * 2.0;
        float a = smoothstep(1.0, uHard, d);
        gl_FragColor = vec4(vColor, a * a * vAlpha);
        #include <colorspace_fragment>
      }`,
    transparent: true,
    depthWrite: false,
    depthTest: opts.depthTest ?? false,
    blending: ctx.palette.additive ? THREE.AdditiveBlending : THREE.NormalBlending,
  }))
  const object = new THREE.Points(geo, mat)
  object.frustumCulled = false
  const size = new THREE.Vector2()
  object.onBeforeRender = (renderer, _scene, camera) => {
    renderer.getDrawingBufferSize(size)
    const persp = camera as T.PerspectiveCamera
    const flat = camera as T.OrthographicCamera
    mat.uniforms.uPersp.value = persp.isPerspectiveCamera ? 1 : 0
    mat.uniforms.uScale.value = persp.isPerspectiveCamera
      ? size.y / (2 * Math.tan((persp.fov * Math.PI) / 360))
      : size.y / (flat.top - flat.bottom)
  }
  return {
    object,
    count,
    set(i, x, y, z, color, s, alpha = 1) {
      pos[i * 3] = x; pos[i * 3 + 1] = y; pos[i * 3 + 2] = z
      col[i * 3] = color.r; col[i * 3 + 1] = color.g; col[i * 3 + 2] = color.b
      look[i * 2] = s; look[i * 2 + 1] = alpha
    },
    hide(i) {
      look[i * 2 + 1] = 0
    },
    commit() {
      geo.attributes.position.needsUpdate = true
      geo.attributes.color.needsUpdate = true
      geo.attributes.look.needsUpdate = true
    },
  }
}

/**
 * A generated 3D model as a coloured point cloud (see
 * scripts/showcase/mesh_points.py). Positions span -1..1 on the model's
 * longest side, Y up; colours are linear RGB. Null if it cannot be loaded.
 */
export interface PointModel { count: number; positions: Float32Array; colors: Float32Array }
export async function loadPoints(url: string, limit = Infinity): Promise<PointModel | null> {
  try {
    const res = await fetch(url)
    if (!res.ok) return null
    const buf = await res.arrayBuffer()
    const view = new DataView(buf)
    if (view.getUint32(0, true) !== 0x54504349) return null // "ICPT"
    const total = view.getUint32(4, true)
    const count = Math.min(total, limit)
    const positions = new Float32Array(count * 3)
    const colors = new Float32Array(count * 3)
    for (let i = 0; i < count * 3; i++) {
      positions[i] = view.getInt16(8 + i * 2, true) / 32767
      const c = view.getUint8(8 + total * 6 + i) / 255
      colors[i] = c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
    }
    return { count, positions, colors }
  } catch {
    return null
  }
}

/**
 * A point model that can build itself and fall apart. Every point has a place
 * in the model and a place in a loose "raw" cloud (a shell around the model,
 * or a flat sheet somewhere else); `build` moves points from one to the other,
 * lowest first. Place and size it with `object.position` and `object.scale`.
 */
export interface ModelCloud {
  object: T.Points
  /** 0 = all raw, 1 = fully built. */
  build(v: number): void
  /** 0 = whole, 1 = blown away. */
  dissolve(v: number): void
  /** Turn about the vertical axis (radians). */
  turn(angle: number): void
  /** Seconds, to keep the raw cloud drifting. */
  time(t: number): void
  /** The raw cloud as a flat sheet centred at `x,y,z` (model units), `w` by `h`. */
  sheet(x: number, y: number, z: number, w: number, h: number): void
}
export function modelCloud(
  ctx: StageContext,
  model: PointModel,
  /** `tint` colours raw points; pass null to keep each point's own colour. */
  opts: { size?: number; tint?: string | null; seed?: number } = {},
): ModelCloud {
  const { THREE } = ctx
  const rnd = seeded(opts.seed ?? 11)
  const seeds = new Float32Array(model.count * 3)
  for (let i = 0; i < seeds.length; i++) seeds[i] = rnd()
  const geo = ctx.keep(new THREE.BufferGeometry())
  geo.setAttribute('position', new THREE.BufferAttribute(model.positions, 3))
  geo.setAttribute('color', new THREE.BufferAttribute(model.colors, 3))
  geo.setAttribute('seed', new THREE.BufferAttribute(seeds, 3))
  const u = {
    uBuild: { value: 1 }, uGone: { value: 0 }, uAngle: { value: 0 }, uTime: { value: 0 },
    uSize: { value: opts.size ?? 0.03 }, uTint: { value: new THREE.Color(opts.tint ?? ctx.palette.pink) }, uTintAmt: { value: opts.tint === null ? 0 : 1 },
    uSheet: { value: 0 }, uFrom: { value: new THREE.Vector3() }, uSpread: { value: new THREE.Vector2(1, 1) },
    uScale: { value: 1 }, uPersp: { value: 0 },
    // At night, a little light on every point so dark parts of a model still read.
    uLift: { value: new THREE.Color(ctx.palette.dim).multiplyScalar(ctx.palette.additive ? 0.16 : 0) },
  }
  const mat = ctx.keep(new THREE.ShaderMaterial({
    uniforms: u,
    vertexShader: `
      attribute vec3 color; attribute vec3 seed;
      uniform float uBuild, uGone, uAngle, uTime, uSize, uSheet, uScale, uPersp, uTintAmt;
      uniform vec3 uTint, uFrom, uLift; uniform vec2 uSpread;
      varying vec3 vColor; varying float vAlpha;
      vec3 turnY(vec3 p, float a) { float c = cos(a), s = sin(a); return vec3(c * p.x + s * p.z, p.y, c * p.z - s * p.x); }
      void main() {
        // Lower points arrive first, with some shuffle so it is not a hard edge.
        float order = 0.6 * (position.y * 0.5 + 0.5) + 0.4 * seed.z;
        float x = clamp((uBuild * 1.45 - order) / 0.45, 0.0, 1.0);
        float p = 1.0 - pow(1.0 - x, 3.0);                        // leave quickly, land softly
        vec3 target = turnY(position, uAngle);
        vec3 shell = turnY(normalize(seed - 0.5 + 0.001) * (0.85 + 0.6 * seed.x), uTime * (0.25 + 0.5 * seed.y));
        vec3 sheet = uFrom + vec3((seed.x - 0.5) * uSpread.x, (seed.y - 0.5) * uSpread.y, 0.0);
        vec3 raw = mix(shell, sheet, uSheet);
        vec3 pos = mix(raw, target, p);
        pos.z += sin(p * 3.14159) * 0.35 * uSheet;                 // fly in an arc towards the viewer
        float gone = smoothstep(0.0, 1.0, uGone * 1.5 - seed.y * 0.5);
        pos += gone * vec3(seed.x - 0.5, 0.25 + seed.z, seed.y - 0.5) * 2.4;
        vec4 mv = modelViewMatrix * vec4(pos, 1.0);
        gl_Position = projectionMatrix * mv;
        float world = uSize * length(modelMatrix[0].xyz) * mix(0.6, 1.0, smoothstep(0.6, 1.0, p)) * (1.0 - 0.5 * gone);
        gl_PointSize = max(1.5, world * uScale * mix(1.0, 1.0 / max(0.001, -mv.z), uPersp));
        float depth = 0.74 + 0.26 * clamp(target.z * 0.9 + 0.5, 0.0, 1.0); // nearer points a little brighter
        vColor = mix(mix(color, uTint, uTintAmt), (color + uLift) * depth, smoothstep(0.5, 1.0, p));
        // On a sheet, a point shows only from just before it lifts off.
        float lifted = mix(1.0, smoothstep(-0.03, 0.0, uBuild * 1.45 - order), uSheet);
        vAlpha = mix(0.6, 1.0, p) * (1.0 - gone) * lifted;
      }`,
    fragmentShader: `
      varying vec3 vColor; varying float vAlpha;
      void main() {
        float d = length(gl_PointCoord - 0.5) * 2.0;
        if (d > 1.0 || vAlpha < 0.02) discard;
        gl_FragColor = vec4(vColor, vAlpha * smoothstep(1.0, 0.7, d));
        #include <colorspace_fragment>
      }`,
    transparent: true,
  }))
  const object = new THREE.Points(geo, mat)
  object.frustumCulled = false
  const size = new THREE.Vector2()
  object.onBeforeRender = (renderer, _scene, camera) => {
    renderer.getDrawingBufferSize(size)
    const persp = camera as T.PerspectiveCamera
    const flat = camera as T.OrthographicCamera
    u.uPersp.value = persp.isPerspectiveCamera ? 1 : 0
    u.uScale.value = persp.isPerspectiveCamera
      ? size.y / (2 * Math.tan((persp.fov * Math.PI) / 360))
      : size.y / (flat.top - flat.bottom)
  }
  return {
    object,
    build: (v) => { u.uBuild.value = v },
    dissolve: (v) => { u.uGone.value = v },
    turn: (a) => { u.uAngle.value = a },
    time: (t) => { u.uTime.value = t },
    sheet: (x, y, z, w, h) => {
      u.uSheet.value = 1
      u.uFrom.value.set(x, y, z)
      u.uSpread.value.set(w, h)
    },
  }
}

/** A soft round light as a texture, for points and sprites. */
export function softDot(THREE: typeof T, keep: StageContext['keep'], hard = false): T.Texture {
  const size = 64
  const cv = document.createElement('canvas')
  cv.width = cv.height = size
  const g = cv.getContext('2d')!
  const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  grad.addColorStop(0, 'rgba(255,255,255,1)')
  grad.addColorStop(hard ? 0.55 : 0.25, 'rgba(255,255,255,0.9)')
  grad.addColorStop(hard ? 0.7 : 0.6, hard ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.25)')
  grad.addColorStop(1, 'rgba(255,255,255,0)')
  g.fillStyle = grad
  g.fillRect(0, 0, size, size)
  return keep(new THREE.CanvasTexture(cv))
}

/** An orthographic camera that always shows `height` world units vertically. */
export function flatCamera(ctx: StageContext, height: number): T.OrthographicCamera {
  const cam = new ctx.THREE.OrthographicCamera(-1, 1, 1, -1, -50, 50)
  const fit = (aspect: number, h = height) => {
    cam.top = h / 2
    cam.bottom = -h / 2
    cam.left = (-h / 2) * aspect
    cam.right = (h / 2) * aspect
    cam.updateProjectionMatrix()
  }
  fit(ctx.aspect)
  cam.userData.fit = fit
  ctx.camera = cam
  return cam
}

/** Average colours of an image on a small grid (for mosaics). Null on failure. */
export function sampleImage(src: string, cols: number, rows: number): Promise<Uint8ClampedArray | null> {
  return new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      try {
        const cv = document.createElement('canvas')
        cv.width = cols
        cv.height = rows
        const g = cv.getContext('2d')!
        // Centre-crop to the grid's shape.
        const want = cols / rows
        const have = img.width / img.height
        const sw = have > want ? img.height * want : img.width
        const sh = have > want ? img.height : img.width / want
        g.drawImage(img, (img.width - sw) / 2, (img.height - sh) / 2, sw, sh, 0, 0, cols, rows)
        resolve(g.getImageData(0, 0, cols, rows).data)
      } catch {
        resolve(null)
      }
    }
    img.onerror = () => resolve(null)
    img.src = src
  })
}
