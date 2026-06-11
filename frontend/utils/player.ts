// Track model for the global music player (docs/prd/06-media-playback.md).
// A "track" is just a slim, playback-oriented view of a MUSIC InferenceRequest,
// so queues can be built from any list endpoint without extra fetches.

import type { InferenceRequest } from '@/types'

export interface PlayerTrack {
  id: string
  title: string
  url: string
  duration?: number | null
  coverUrl?: string | null
  owner?: string | null
  /** Detail-page link target; lets the player bar jump to the request. */
  requestId: string
}

export function trackFromRequest(r: InferenceRequest): PlayerTrack | null {
  if (r.inference_type !== 'MUSIC' || !r.output_audio_url) return null
  const payloadPrompt =
    typeof r.payload?.prompt === 'string' ? (r.payload.prompt as string) : ''
  return {
    id: String(r.id),
    requestId: String(r.id),
    title: (r.prompt_preview || payloadPrompt || 'Untitled song').trim(),
    url: r.output_audio_url,
    duration: r.audio_seconds ?? null,
    coverUrl: r.cover_image_url ?? null,
    owner: r.github_login || r.owner || null,
  }
}

export function tracksFromRequests(rs: InferenceRequest[]): PlayerTrack[] {
  return rs
    .map(trackFromRequest)
    .filter((t): t is PlayerTrack => t !== null)
}

/** mm:ss (or h:mm:ss) for player timestamps. */
export function formatTrackTime(seconds?: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return '–:––'
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

/** Total playlist runtime, Spotify-style ("47 min", "1 hr 12 min"). */
export function formatRuntime(seconds?: number | null): string | null {
  if (!seconds || seconds <= 0) return null
  const mins = Math.round(seconds / 60)
  if (mins < 60) return `${Math.max(1, mins)} min`
  return `${Math.floor(mins / 60)} hr ${mins % 60} min`
}

// --- recently played (client-only, no backend history table) -----------------

const RECENT_KEY = 'ic-recently-played'
const RECENT_MAX = 20

export function recentlyPlayed(): PlayerTrack[] {
  if (typeof localStorage === 'undefined') return []
  try {
    const raw = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
    return Array.isArray(raw) ? (raw as PlayerTrack[]) : []
  } catch {
    return []
  }
}

export function rememberPlayed(track: PlayerTrack): void {
  if (typeof localStorage === 'undefined') return
  try {
    const rest = recentlyPlayed().filter((t) => t.id !== track.id)
    localStorage.setItem(
      RECENT_KEY,
      JSON.stringify([track, ...rest].slice(0, RECENT_MAX)),
    )
  } catch {
    /* storage full/blocked — recently-played is best-effort */
  }
}
