// One playback speed for everything that plays sound on the site: clips,
// narrations and the global player. Chosen once, remembered on this device,
// applied wherever a player mounts.

export const RATE_MIN = 0.5
export const RATE_MAX = 3
export const RATE_STEP = 0.05
export const RATE_PRESETS = [0.75, 1, 1.25, 1.5, 2, 2.5, 3]
const KEY = 'playback-rate'

const clampRate = (r: number) =>
  Math.round(Math.min(RATE_MAX, Math.max(RATE_MIN, Number.isFinite(r) ? r : 1)) / RATE_STEP) * RATE_STEP

export function usePlaybackRate() {
  const rate = useState<number>('playback-rate', () => 1)
  const loaded = useState<boolean>('playback-rate-loaded', () => false)
  if (import.meta.client && !loaded.value) {
    loaded.value = true
    const saved = Number(localStorage.getItem(KEY))
    if (saved) rate.value = clampRate(saved)
  }

  const setRate = (r: number) => {
    rate.value = clampRate(r)
    if (import.meta.client) localStorage.setItem(KEY, String(rate.value))
  }

  /** Apply the current speed to a media element, keeping voices at pitch. */
  const apply = (el: HTMLMediaElement | null | undefined) => {
    if (!el) return
    el.preservesPitch = true
    // defaultPlaybackRate survives a new `src`; playbackRate takes effect now.
    el.defaultPlaybackRate = rate.value
    el.playbackRate = rate.value
  }

  const label = computed(() => `${Number(rate.value.toFixed(2))}×`)
  return { rate, setRate, apply, label }
}
