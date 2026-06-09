// One AudioContext shared across every MusicVisualizer on the page. Browsers
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
