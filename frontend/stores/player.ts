// Global music player (docs/prd/06-media-playback-experience.md, phase 2).
// One store owns one shared HTMLAudioElement; every play affordance in the app
// (cards, playlists, the music home) routes through it, so playback survives
// navigation and the bottom bar is the single source of truth.

import { defineStore } from 'pinia'
import type { PlayerTrack } from '@/utils/player'
import { rememberPlayed } from '@/utils/player'

export type RepeatMode = 'off' | 'all' | 'one'

interface PlayerState {
  queue: PlayerTrack[]
  /** Index into `queue` of the current track (-1 = nothing loaded). */
  index: number
  /** Play order as queue indices — identity normally, shuffled when shuffle
   * is on (current track first, so toggling never interrupts playback). */
  order: number[]
  shuffle: boolean
  repeat: RepeatMode
  playing: boolean
  currentTime: number
  duration: number
  volume: number
  /** Bumped on queue replacement so the queue popover can reset scroll. */
  queueVersion: number
}

// The audio element is module-level (not state): it must never be serialized,
// and there is exactly one for the whole app.
let audio: HTMLAudioElement | null = null

const shuffled = (n: number, first: number): number[] => {
  const rest = Array.from({ length: n }, (_, i) => i).filter((i) => i !== first)
  for (let i = rest.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[rest[i], rest[j]] = [rest[j], rest[i]]
  }
  return first >= 0 ? [first, ...rest] : rest
}

export const usePlayerStore = defineStore('player', {
  state: (): PlayerState => ({
    queue: [],
    index: -1,
    order: [],
    shuffle: false,
    repeat: 'off',
    playing: false,
    currentTime: 0,
    duration: 0,
    volume: 1,
    queueVersion: 0,
  }),

  getters: {
    current(state): PlayerTrack | null {
      return state.index >= 0 ? state.queue[state.index] ?? null : null
    },
    hasQueue(state): boolean {
      return state.queue.length > 0
    },
    /** Position of the current track within the play order. */
    orderPos(state): number {
      return state.order.indexOf(state.index)
    },
    hasNext(): boolean {
      return (
        this.repeat !== 'off' ||
        (this.orderPos >= 0 && this.orderPos < this.order.length - 1)
      )
    },
    hasPrev(): boolean {
      return this.orderPos > 0 || this.currentTime > 3
    },
  },

  actions: {
    _el(): HTMLAudioElement | null {
      if (typeof window === 'undefined') return null
      if (!audio) {
        audio = new Audio()
        audio.preload = 'metadata'
        // The OUTPUT_AUDIO asset is a public CORS-served kind; anonymous mode
        // keeps the element analyzable (visualizer) without tainting.
        audio.crossOrigin = 'anonymous'
        audio.addEventListener('timeupdate', () => {
          this.currentTime = audio?.currentTime ?? 0
        })
        audio.addEventListener('durationchange', () => {
          const d = audio?.duration
          this.duration = Number.isFinite(d) ? (d as number) : 0
        })
        audio.addEventListener('play', () => {
          this.playing = true
        })
        audio.addEventListener('pause', () => {
          this.playing = false
        })
        audio.addEventListener('ended', () => this._onEnded())
        audio.volume = this.volume
        this._mediaSessionHandlers()
      }
      return audio
    },

    /** The element, for the visualizer's analyser hookup. */
    audioElement(): HTMLAudioElement | null {
      return this._el()
    },

    _load(index: number, autoplay = true) {
      const el = this._el()
      const track = this.queue[index]
      if (!el || !track) return
      this.index = index
      this.currentTime = 0
      this.duration = track.duration ?? 0
      el.src = track.url
      if (autoplay) {
        void el.play().catch(() => {
          // Autoplay can be blocked until a user gesture; the bar shows the
          // paused state and the next tap starts playback.
          this.playing = false
        })
      }
      rememberPlayed(track)
      this._mediaSessionMetadata(track)
    },

    /** Replace the queue and start playing at `startIndex`.
     * Pass -1 to let the player pick (random when shuffling, else first). */
    playQueue(tracks: PlayerTrack[], startIndex = 0, opts: { shuffle?: boolean } = {}) {
      if (!tracks.length) return
      this.queue = tracks.slice()
      this.queueVersion++
      this.shuffle = opts.shuffle ?? this.shuffle
      let start = startIndex
      if (start < 0) {
        start = this.shuffle ? Math.floor(Math.random() * tracks.length) : 0
      }
      start = Math.min(Math.max(start, 0), tracks.length - 1)
      this.order = this.shuffle
        ? shuffled(tracks.length, start)
        : tracks.map((_, i) => i)
      this._load(start)
    },

    playTrack(track: PlayerTrack) {
      this.playQueue([track], 0)
    },

    /** Append without interrupting playback; starts playing if idle. */
    addToQueue(tracks: PlayerTrack[]) {
      const fresh = tracks.filter((t) => !this.queue.some((q) => q.id === t.id))
      if (!fresh.length) return
      const base = this.queue.length
      this.queue.push(...fresh)
      this.order.push(...fresh.map((_, i) => base + i))
      if (this.index === -1) this._load(this.order[0])
    },

    removeFromQueue(queueIndex: number) {
      if (queueIndex < 0 || queueIndex >= this.queue.length) return
      const removingCurrent = queueIndex === this.index
      this.queue.splice(queueIndex, 1)
      this.order = this.order
        .filter((i) => i !== queueIndex)
        .map((i) => (i > queueIndex ? i - 1 : i))
      if (this.queue.length === 0) {
        this.clear()
        return
      }
      if (removingCurrent) {
        const next = this.order[0] ?? 0
        this._load(next, this.playing)
      } else if (this.index > queueIndex) {
        this.index--
      }
    },

    jumpTo(queueIndex: number) {
      if (queueIndex >= 0 && queueIndex < this.queue.length) this._load(queueIndex)
    },

    toggle() {
      const el = this._el()
      if (!el || this.index === -1) return
      if (el.paused) void el.play().catch(() => {})
      else el.pause()
    },

    next() {
      if (this.repeat === 'one') {
        this._load(this.index)
        return
      }
      const pos = this.orderPos
      if (pos >= 0 && pos < this.order.length - 1) {
        this._load(this.order[pos + 1])
      } else if (this.repeat === 'all' && this.order.length) {
        this._load(this.order[0])
      }
    },

    prev() {
      const el = this._el()
      // Spotify behavior: restart the track unless we're right at the start.
      if (el && el.currentTime > 3) {
        el.currentTime = 0
        return
      }
      const pos = this.orderPos
      if (pos > 0) this._load(this.order[pos - 1])
      else if (el) el.currentTime = 0
    },

    _onEnded() {
      if (this.repeat === 'one') {
        this._load(this.index)
        return
      }
      const pos = this.orderPos
      if (pos >= 0 && pos < this.order.length - 1) {
        this._load(this.order[pos + 1])
      } else if (this.repeat === 'all' && this.order.length) {
        this._load(this.order[0])
      } else {
        this.playing = false
      }
    },

    seek(seconds: number) {
      const el = this._el()
      if (el && Number.isFinite(seconds)) {
        el.currentTime = Math.min(Math.max(seconds, 0), this.duration || seconds)
        this.currentTime = el.currentTime
      }
    },

    setVolume(v: number) {
      this.volume = Math.min(Math.max(v, 0), 1)
      const el = this._el()
      if (el) el.volume = this.volume
    },

    toggleShuffle() {
      this.shuffle = !this.shuffle
      this.order = this.shuffle
        ? shuffled(this.queue.length, this.index)
        : this.queue.map((_, i) => i)
    },

    cycleRepeat() {
      this.repeat = this.repeat === 'off' ? 'all' : this.repeat === 'all' ? 'one' : 'off'
    },

    clear() {
      const el = this._el()
      if (el) {
        el.pause()
        el.removeAttribute('src')
        el.load()
      }
      this.queue = []
      this.order = []
      this.index = -1
      this.playing = false
      this.currentTime = 0
      this.duration = 0
      this.queueVersion++
    },

    // --- Media Session: OS media keys + lock-screen artwork ------------------

    _mediaSessionMetadata(track: PlayerTrack) {
      if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) return
      navigator.mediaSession.metadata = new MediaMetadata({
        title: track.title,
        artist: track.owner || 'inference.club',
        album: 'inference.club',
        artwork: track.coverUrl
          ? [{ src: track.coverUrl, sizes: '1024x1024', type: 'image/png' }]
          : [],
      })
    },

    _mediaSessionHandlers() {
      if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) return
      const ms = navigator.mediaSession
      ms.setActionHandler('play', () => this.toggle())
      ms.setActionHandler('pause', () => this.toggle())
      ms.setActionHandler('previoustrack', () => this.prev())
      ms.setActionHandler('nexttrack', () => this.next())
      try {
        ms.setActionHandler('seekto', (e) => {
          if (e.seekTime != null) this.seek(e.seekTime)
        })
      } catch {
        /* seekto unsupported on some browsers */
      }
    },
  },
})
