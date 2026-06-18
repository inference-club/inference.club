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
  return ctx
}

// createMediaElementSource may only be called once per element, but the
// player bar (which hosts the visualizer) can unmount/remount across layout
// switches while the global player's element lives on. Cache the analyser per
// element so re-mounts reattach instead of throwing.
const analysers = new WeakMap<HTMLAudioElement, AnalyserNode>()

export function getSharedAnalyser(el: HTMLAudioElement): AnalyserNode | null {
  const cached = analysers.get(el)
  if (cached) return cached
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
    return analyser
  } catch {
    return null
  }
}
