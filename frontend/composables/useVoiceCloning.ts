// Client for the voice-cloning playground (Dia) — the voice-sample library
// CRUD under /api/inference/voice-samples/ plus the generation endpoint
// /v1/voice/generations (returns raw audio bytes). Mirrors useTextToSpeech /
// useContentSharing cookie-session + CSRF conventions. See
// docs/prd/09-voice-cloning.md.
import type { ModelInfo } from '@/composables/usePlayground'

export interface VoiceSample {
  id: number
  speaker_name: string
  label: string
  is_default: boolean
  transcript: string
  transcript_source: 'stt' | 'manual' | 'edited'
  language: string
  duration_seconds: number | null
  audio_url: string | null
  content_type: string
  created_on: string
}

// One speaker == the set of samples sharing speaker_name, with a default + variations.
export interface Speaker {
  name: string
  default: VoiceSample | null
  variations: VoiceSample[]
  samples: VoiceSample[]
}

export interface GenerateVoiceOptions {
  model?: string
  input: string
  speakers?: Record<string, number> // "S1"/"S2" -> voice sample id
  cfg_scale?: number
  temperature?: number
  top_p?: number
  cfg_filter_top_k?: number
  speed_factor?: number
  max_new_tokens?: number
  seed?: number
  visibility?: string
  collection?: string
}

export interface GeneratedVoice {
  blob: Blob
  url: string
  contentType: string
  seed: string | null
}

export function useVoiceCloning() {
  const config = useRuntimeConfig()
  const apiBase = config.public.apiBase as string
  const libBase = `${apiBase}/api/inference/voice-samples`

  const csrf = (): string | null => {
    if (typeof document === 'undefined' || !document.cookie) return null
    const hit = document.cookie.split('; ').find((c) => c.startsWith('csrftoken='))
    return hit ? decodeURIComponent(hit.split('=')[1]) : null
  }

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || e?.detail || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  // --- Models -------------------------------------------------------------
  // Voice-cloning models are tts services that advertise the voice-cloning
  // feature (Dia). Plain Riva tts services are excluded.
  const listVoiceModels = async (): Promise<ModelInfo[]> => {
    const res = await fetch(`${apiBase}/v1/models`, { credentials: 'include' })
    if (!res.ok) throw new Error(`Failed to load models (HTTP ${res.status})`)
    const data = await res.json()
    return (data.data ?? [])
      .map((m: Partial<ModelInfo> & { id: string }) => ({
        id: m.id,
        input_modalities: m.input_modalities ?? ['text'],
        supported_features: m.supported_features ?? [],
        context_length: m.context_length ?? null,
        service_type: m.service_type ?? 'llm',
      }))
      .filter(
        (m: ModelInfo) =>
          m.service_type === 'tts' && (m.supported_features ?? []).includes('voice-cloning'),
      )
  }

  // --- Voice-sample library ----------------------------------------------
  const listSamples = async (): Promise<VoiceSample[]> => {
    const res = await fetch(`${libBase}/`, { credentials: 'include' })
    if (!res.ok) throw new Error(await _errorMessage(res))
    return await res.json()
  }

  // Group flat samples into speakers (default first, then variations).
  const groupBySpeaker = (samples: VoiceSample[]): Speaker[] => {
    const map = new Map<string, Speaker>()
    for (const s of samples) {
      let sp = map.get(s.speaker_name)
      if (!sp) {
        sp = { name: s.speaker_name, default: null, variations: [], samples: [] }
        map.set(s.speaker_name, sp)
      }
      sp.samples.push(s)
      if (s.is_default) sp.default = s
      else sp.variations.push(s)
    }
    return [...map.values()].sort((a, b) => a.name.localeCompare(b.name))
  }

  const createSample = async (opts: {
    audio: Blob
    filename?: string
    speaker_name: string
    label?: string
    transcript?: string
    language?: string
    is_default?: boolean
  }): Promise<VoiceSample> => {
    const fd = new FormData()
    fd.append('audio', opts.audio, opts.filename || 'sample.wav')
    fd.append('speaker_name', opts.speaker_name)
    if (opts.label) fd.append('label', opts.label)
    if (opts.transcript) fd.append('transcript', opts.transcript)
    if (opts.language) fd.append('language', opts.language)
    if (opts.is_default) fd.append('is_default', 'true')
    const token = csrf()
    const res = await fetch(`${libBase}/`, {
      method: 'POST',
      credentials: 'include',
      headers: { ...(token ? { 'X-CSRFToken': token } : {}) },
      body: fd,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    return await res.json()
  }

  const updateSample = async (
    id: number,
    patch: Partial<Pick<VoiceSample, 'speaker_name' | 'label' | 'transcript' | 'language' | 'is_default'>>,
  ): Promise<VoiceSample> => {
    const token = csrf()
    const res = await fetch(`${libBase}/${id}/`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(token ? { 'X-CSRFToken': token } : {}) },
      body: JSON.stringify(patch),
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    return await res.json()
  }

  const deleteSample = async (id: number): Promise<void> => {
    const token = csrf()
    const res = await fetch(`${libBase}/${id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { ...(token ? { 'X-CSRFToken': token } : {}) },
    })
    if (!res.ok && res.status !== 204) throw new Error(await _errorMessage(res))
  }

  const transcribeSample = async (id: number): Promise<VoiceSample> => {
    const token = csrf()
    const res = await fetch(`${libBase}/${id}/transcribe/`, {
      method: 'POST',
      credentials: 'include',
      headers: { ...(token ? { 'X-CSRFToken': token } : {}) },
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    return await res.json()
  }

  // --- Generation ---------------------------------------------------------
  const generate = async (
    opts: GenerateVoiceOptions,
    signal?: AbortSignal,
  ): Promise<GeneratedVoice> => {
    const token = csrf()
    const res = await fetch(`${apiBase}/v1/voice/generations`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(token ? { 'X-CSRFToken': token } : {}) },
      body: JSON.stringify(opts),
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    const blob = await res.blob()
    return {
      blob,
      url: URL.createObjectURL(blob),
      contentType: res.headers.get('content-type') || 'audio/wav',
      seed: res.headers.get('x-seed'),
    }
  }

  return {
    listVoiceModels,
    listSamples,
    groupBySpeaker,
    createSample,
    updateSample,
    deleteSample,
    transcribeSample,
    generate,
  }
}
