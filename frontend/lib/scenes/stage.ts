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
