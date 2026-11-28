// One AudioContext shared across the app (the global player bar's visualizer).
// Browsers
// cap the number of live contexts, so a module-level singleton (created lazily
// on first playback) keeps us to one regardless of how many song cards mount.
let ctx: AudioContext | null = null

export function getSharedAudioContext(): AudioContext | null {
  if (ctx) return ctx
  if (typeof window === 'undefined') return null
  const Ctor =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctor) return null
  ctx = new Ctor()
  // Once the player's element is wired through this context, a suspended
  // context means the song "plays" (the clock runs) in silence. Contexts start
  // suspended when created outside a user gesture and are suspended again by
  // the browser after an interruption, so resume on the next gesture and
  // whenever the tab comes back.
  const resume = () => void resumeSharedAudioContext()
  window.addEventListener('pointerdown', resume, { passive: true })
  window.addEventListener('keydown', resume, { passive: true })
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') resume()
  })
  return ctx
}

/** Resume the shared context if the browser has suspended it. Safe to call
 * any time; a no-op when no context exists or it is already running. */
export async function resumeSharedAudioContext(): Promise<void> {
  if (!ctx || ctx.state === 'running' || ctx.state === 'closed') return
  try {
    await ctx.resume()
  } catch {
    /* needs a user gesture; the listeners above retry on the next one */
  }
}

/** Whether to route the player through Web Audio for the visualizer. Not on
 * touch devices: there the bar has no room for it, and audio routed through
 * an AudioContext stops when a phone locks or the tab is backgrounded, where
 * a plain media element keeps playing. */
export function visualizerSupported(): boolean {
  if (typeof window === 'undefined') return false
  return !window.matchMedia?.('(pointer: coarse)').matches
}

// createMediaElementSource may only be called once per element, but the
// player bar (which hosts the visualizer) can unmount/remount across layout
// switches while the global player's element lives on. Cache the analyser per
// element so re-mounts reattach instead of throwing.
const analysers = new WeakMap<HTMLAudioElement, AnalyserNode>()

export function getSharedAnalyser(el: HTMLAudioElement): AnalyserNode | null {
  const cached = analysers.get(el)
  if (cached) {
    void resumeSharedAudioContext()
    return cached
  }
  if (!visualizerSupported()) return null
  const context = getSharedAudioContext()
  if (!context) return null
  try {
    const source = context.createMediaElementSource(el)
    const analyser = context.createAnalyser()
    analyser.fftSize = 256
    analyser.smoothingTimeConstant = 0.75
    source.connect(analyser)
    analyser.connect(context.destination)
    analysers.set(el, analyser)
    void resumeSharedAudioContext()
    return analyser
  } catch {
    return null
  }
}
