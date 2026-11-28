/**
 * Client for the Narration Studio API (PRD 12 §5.4 / V3): episodes, their
 * ordered segments, each segment's takes (variants), and the per-segment
 * pipeline actions (process / regenerate / select take).
 */
export interface Word { word: string; start: number; end: number }

export interface Grade {
  score: number
  should_regenerate: boolean
  reason: string
  method: string
  // Autopilot / audition extras (present on takes scored by the produce loop).
  take_score?: number
  grade_score?: number
  wps?: number
  pace_penalty?: number
  accepted?: boolean
  attempt?: number
  seed?: number | null
  /** Seconds of stray sound removed after the last word. */
  tail_cut?: number
}

export interface Variant {
  id: number
  text: string
  duration_seconds: number | null
  words: Word[]
  audio_url: string | null
  cleaned_audio_url: string | null
  clean_status: 'not_cleaned' | 'cleaned' | 'unavailable' | 'error'
  // The StudioVoice-cleaned, *untrimmed* audio the waveform editor draws against.
  enhanced_audio_url: string | null
  enhanced_duration: number | null
  enhanced_words: Word[]
  // Keep-ranges [[start, end], …] on the enhanced timeline; gaps are what was cut.
  trim_intervals: [number, number][]
  transcript: string
  grade: Grade | null
  seed: number | null
  inference_request_id: number | null
  created_on: string
}

export type SegmentStatus = 'pending' | 'queued' | 'generating' | 'ready' | 'flagged' | 'error'

export interface Segment {
  id: number
  position: number
  text: string
  original_text: string
  status: SegmentStatus
  selected_variant_id: number | null
  voice_sample_id: number | null
  voice_sample_name?: string | null
  variants: Variant[]
  created_on: string
  modified_on: string
}

export interface Episode {
  id: number
  title: string
  description: string
  voice_model: string
  voice_sample_id: number | null
  voice_sample_name?: string | null
  settings?: EpisodeSettings
  segments: Segment[]
  created_on: string
  modified_on: string
}

/** Per-episode production settings (backend merges defaults on read). */
export interface EpisodeSettings {
  lexicon: Record<string, string>
  temperature: number
  cfg_scale: number
  top_p: number
  cfg_filter_top_k: number
  speed_factor: number
  max_attempts: number
  accept_score: number
  min_wps: number
  max_wps: number
  trim_pad: number
  trim_gap_threshold: number
  trim_max_gap: number
  // null = loudness leveling off
  loudness_lufs: number | null
}

/** PATCH payload: any key may be null (reset to default); loudness may be "off". */
export type EpisodeSettingsPatch = {
  [K in Exclude<keyof EpisodeSettings, 'loudness_lufs'>]?: EpisodeSettings[K] | null
} & { loudness_lufs?: number | 'off' | null }

export interface SavedVoice {
  id: number
  speaker_name: string
  label: string
  is_default: boolean
  transcript: string
  duration_seconds: number | null
}

export interface VoiceOption {
  model: string
  label: string
  provider: string
  voice_cloning: boolean
}

export interface VoiceSampleOption {
  id: number
  name: string
  has_transcript: boolean
}

export interface StudioVoices {
  voices: VoiceOption[]
  samples: VoiceSampleOption[]
}

export interface EpisodeSummary {
  id: number
  title: string
  segment_count: number
  created_on: string
  modified_on: string
}

function csrf(): string {
  if (!import.meta.client) return ''
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

export function useStudio() {
  const config = useRuntimeConfig()
  const base = config.public.apiBase as string

  const get = <T>(path: string) =>
    $fetch<T>(`${base}${path}`, { credentials: 'include', headers: { Accept: 'application/json' } })
  const send = <T>(method: 'POST' | 'PATCH' | 'DELETE', path: string, body?: unknown) =>
    $fetch<T>(`${base}${path}`, {
      method,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(csrf() ? { 'X-CSRFToken': csrf() } : {}) },
      body: body ?? {},
    })

  return {
    listEpisodes: () => get<{ data: EpisodeSummary[] }>('/v1/episodes').then((r) => r.data),
    getEpisode: (id: number | string) => get<Episode>(`/v1/episodes/${id}`),
    createEpisode: (title: string) => send<Episode>('POST', '/v1/episodes', { title }),
    updateEpisode: (id: number, body: {
      title?: string; voice_model?: string; voice_sample_id?: number | null; settings?: EpisodeSettingsPatch
    }) => send<Episode>('PATCH', `/v1/episodes/${id}`, body),
    // Autopilot: generate → clean → transcribe → trim → level → grade → retake
    // until accepted, for every segment not ready (all of them with `force`).
    produceEpisode: (id: number, body: { force?: boolean; attempts?: number; accept?: number } = {}) =>
      send<Episode>('POST', `/v1/episodes/${id}/produce`, body),
    // Download every selected take as a zip (01.wav… + manifest.json).
    exportEpisode: async (id: number) => {
      const res = await fetch(`${base}/v1/episodes/${id}/export`, { credentials: 'include' })
      if (!res.ok) {
        let detail = `Export failed (HTTP ${res.status})`
        try { detail = ((await res.json()) as { detail?: string }).detail || detail } catch { /* not JSON */ }
        throw new Error(detail)
      }
      const cd = res.headers.get('Content-Disposition') || ''
      const m = cd.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i)
      const filename = m ? decodeURIComponent((m[1] || m[2]).trim()) : `episode-${id}.zip`
      const objectUrl = URL.createObjectURL(await res.blob())
      const a = document.createElement('a')
      a.href = objectUrl
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
      return filename
    },
    listVoices: () => get<StudioVoices>('/v1/studio/voices'),
    createFromText: (text: string, targetWords?: number, title?: string) =>
      send<Episode>('POST', '/v1/episodes/from-text', {
        text, target_words: targetWords, title,
      }),
    deleteEpisode: (id: number) => send('DELETE', `/v1/episodes/${id}`),

    addSegment: (epId: number, text: string) =>
      send<Segment>('POST', `/v1/episodes/${epId}/segments`, { text }),
    updateSegment: (id: number, body: { text?: string; voice_sample_id?: number | null }) =>
      send<Segment>('PATCH', `/v1/segments/${id}`, body),
    deleteSegment: (id: number) => send('DELETE', `/v1/segments/${id}`),
    reorder: (epId: number, order: number[]) =>
      send<Episode>('POST', `/v1/episodes/${epId}/segments/reorder`, { order }),

    processSegment: (id: number) => send<Segment>('POST', `/v1/segments/${id}/process`),
    regenerateSegment: (id: number, body: { text?: string; seed?: number } = {}) =>
      send<Segment>('POST', `/v1/segments/${id}/regenerate`, body),
    retrimSegment: (id: number, remove: [number, number][]) =>
      send<Segment>('POST', `/v1/segments/${id}/retrim`, { remove }),
    selectVariant: (segId: number, variantId: number) =>
      send<Segment>('POST', `/v1/segments/${segId}/variants/${variantId}/select`),
    // Audition N takes (or specific seeds) of one line; all scored, best selected.
    auditionSegment: (id: number, body: { count?: number } | { seeds: number[] } = { count: 4 }) =>
      send<Segment>('POST', `/v1/segments/${id}/takes`, body),
    saveVariantAsVoice: (segId: number, variantId: number, body: {
      speaker_name: string; label?: string; is_default?: boolean; use_for_episode?: boolean
    }) => send<SavedVoice>('POST', `/v1/segments/${segId}/variants/${variantId}/save-voice`, body),
  }
}
