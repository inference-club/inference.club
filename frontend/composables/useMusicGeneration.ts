// Client for the music-generation playground. Talks to the OpenAI-style
// extension endpoint POST /v1/music/generations (JSON in, raw audio bytes out)
// with the logged-in session. The backend forwards to a `music` service
// (ACE-Step); the agent hides ACE-Step's async submit/poll/download behind one
// reply, so a result here is simply an audio blob to play and store.

import type { ModelInfo } from '@/composables/usePlayground'

export interface MusicOptions {
  model: string
  prompt: string
  lyrics?: string
  audio_duration?: number
  inference_steps?: number
  guidance_scale?: number
  seed?: number
  use_random_seed?: boolean
  audio_format?: string
  bpm?: number
  key_scale?: string
}

export interface GeneratedSong {
  blob: Blob
  url: string // object URL for playback
  contentType: string
}

export function useMusicGeneration() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  // Only text-to-music models (prompt → song).
  const listMusicModels = async (): Promise<ModelInfo[]> => {
    const res = await fetch(`${config.public.apiBase}/v1/models`, { credentials: 'include' })
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
      .filter((m: ModelInfo) => m.service_type === 'music')
  }

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  // Prompt (+ optional lyrics & controls) → a rendered song.
  const generate = async (opts: MusicOptions, signal?: AbortSignal): Promise<GeneratedSong> => {
    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/music/generations`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-CSRFToken': token } : {}),
      },
      body: JSON.stringify({
        model: opts.model,
        prompt: opts.prompt,
        ...(opts.lyrics ? { lyrics: opts.lyrics } : {}),
        ...(opts.audio_duration ? { audio_duration: opts.audio_duration } : {}),
        ...(opts.inference_steps ? { inference_steps: opts.inference_steps } : {}),
        ...(opts.guidance_scale != null ? { guidance_scale: opts.guidance_scale } : {}),
        ...(opts.use_random_seed === false ? { use_random_seed: false, seed: opts.seed } : {}),
        ...(opts.audio_format ? { audio_format: opts.audio_format } : {}),
        ...(opts.bpm ? { bpm: opts.bpm } : {}),
        ...(opts.key_scale ? { key_scale: opts.key_scale } : {}),
      }),
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    const blob = await res.blob()
    return {
      blob,
      url: URL.createObjectURL(blob),
      contentType: res.headers.get('content-type') || 'audio/mpeg',
    }
  }

  return { listMusicModels, generate }
}
