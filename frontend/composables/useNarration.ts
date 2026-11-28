/**
 * "Narrate this": a link or text in, a finished narration out.
 *
 * A narration is a Studio episode with extra fields the server fills in as it
 * works (`narration`, `source`, `audio_url`, `cover_image_url`). This client
 * starts one, follows it, and offers the handful of fixes a listener needs:
 * re-voice a piece, reword it, leave a note about it, pick another take,
 * rebuild the joined file. The Studio remains the place for fine control.
 */
import type { Episode, Segment } from '@/composables/useStudio'

export type NarrationStage = '' | 'reading' | 'planning' | 'voicing' | 'mixing' | 'done' | 'error' | 'stopped'

export interface NarrationState {
  stage: NarrationStage
  active: boolean
  error: string
  /** 0–1 across the whole run. */
  fraction: number
  counts: { total: number; ready: number; flagged: number; error: number; working: number; waiting: number }
  /** Which model does each job: voice, clean, check, judge, cover, read. */
  models: Record<string, string>
  voice: { sample?: string | null }
  events: Array<{ at: string; message: string }>
  started?: string
  finished?: string
  mix: { seconds?: number; at?: string; offsets?: Array<{ segment_id: number; start: number; end: number }> }
  /** False when takes changed since the joined file was built. */
  mix_current: boolean
  /** segment id → "intro" | "heading" | "body". */
  kinds: Record<string, string>
}

export interface NarrationSource {
  url?: string
  source_url?: string
  title?: string
  author?: string
  published?: string
  site?: string
  via?: string
  words?: number
}

export interface Narration extends Episode {
  source: NarrationSource
  narration: NarrationState
  audio_url: string | null
  audio_seconds: number | null
  cover_image_url: string | null
  segment_count?: number
}

function csrf(): string {
  if (!import.meta.client) return ''
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

export function useNarration() {
  const base = useRuntimeConfig().public.apiBase as string
  const get = <T>(path: string) =>
    $fetch<T>(`${base}${path}`, { credentials: 'include', headers: { Accept: 'application/json' } })
  const send = <T>(method: 'POST' | 'PATCH' | 'DELETE', path: string, body?: unknown) =>
    $fetch<T>(`${base}${path}`, {
      method,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(csrf() ? { 'X-CSRFToken': csrf() } : {}) },
      body: body ?? {},
    })

  /** Start narrating. `input` is a link or the text itself; the server tells them apart. */
  const start = (input: string, opts: { title?: string; voiceSampleId?: number | null } = {}) => {
    const value = input.trim()
    const isLink = /^(https?:\/\/)?[\w.-]+\.[a-z]{2,}(\/\S*)?$/i.test(value)
    return send<Narration>('POST', '/v1/narrations', {
      ...(isLink ? { url: value } : { text: value }),
      ...(opts.title ? { title: opts.title } : {}),
      ...(opts.voiceSampleId ? { voice_sample_id: opts.voiceSampleId } : {}),
    })
  }

  const list = async () =>
    ((await get<{ data: Narration[] }>('/v1/episodes')).data ?? []).filter((e) => e.narration?.stage)
  const fetchOne = (id: number | string) => get<Narration>(`/v1/episodes/${id}`)
  const remove = (id: number) => send<void>('DELETE', `/v1/episodes/${id}`)
  const cancel = (id: number) => send<Narration>('POST', `/v1/episodes/${id}/cancel`)
  /** Rebuild the single joined file from the takes currently chosen. */
  const mix = (id: number) => send<Narration>('POST', `/v1/episodes/${id}/mix`)
  /** Voice every piece that is not good yet. */
  const resume = (id: number) => send<Narration>('POST', `/v1/episodes/${id}/produce`)

  /** Voice one piece again (take, clean, trim, check, retake if poor). */
  const revoice = (segmentId: number) => send<Segment>('POST', `/v1/segments/${segmentId}/produce`)
  const reword = (segmentId: number, text: string) => send<Segment>('PATCH', `/v1/segments/${segmentId}`, { text })
  const chooseTake = (segmentId: number, variantId: number) =>
    send<Segment>('POST', `/v1/segments/${segmentId}/variants/${variantId}/select`)
  /** Say what is wrong in plain words; the piece is fixed and voiced again. */
  const feedback = (segmentId: number, note: string) =>
    send<{ understood: { summary: string; text_changed: boolean; lexicon: Record<string, string> }; segment: Segment }>(
      'POST', `/v1/segments/${segmentId}/feedback`, { note })

  // Voice notes: record, transcribe with the club's speech-to-text, send as a note.
  let sttModel: string | null | undefined
  const transcribe = async (blob: Blob, ext: string): Promise<string> => {
    if (sttModel === undefined) {
      const models = await get<{ data: Array<{ id: string; service_type?: string; provider?: string }> }>('/v1/models')
      sttModel = models.data.find((m) => m.service_type === 'stt' && !m.provider)?.id ?? null
    }
    if (!sttModel) return ''
    const form = new FormData()
    form.append('file', blob, `note.${ext}`)
    form.append('model', sttModel)
    const res = await fetch(`${base}/v1/audio/transcriptions`, {
      method: 'POST',
      credentials: 'include',
      headers: csrf() ? { 'X-CSRFToken': csrf() } : {},
      body: form,
    })
    return res.ok ? String((await res.json()).text ?? '').trim() : ''
  }

  return { start, list, fetchOne, remove, cancel, mix, resume, revoice, reword, chooseTake, feedback, transcribe }
}

/** m:ss, or h:mm:ss past an hour. */
export function clock(seconds?: number | null): string {
  const s = Math.max(0, Math.round(seconds ?? 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${r}` : `${m}:${r}`
}
