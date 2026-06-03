// Client for the text-to-speech playground. Talks to the real
// OpenAI-compatible /v1/audio/speech endpoint (which returns raw audio bytes)
// plus the /v1/audio/voices helper, using the logged-in session.

import type { ModelInfo } from '@/composables/usePlayground'

export interface SynthesizeOptions {
  model: string
  input: string
  voice?: string
  language?: string
  response_format?: string
}

export interface SynthesizedAudio {
  blob: Blob
  url: string // object URL for playback
  contentType: string
}

export function useTextToSpeech() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  const listTtsModels = async (): Promise<ModelInfo[]> => {
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
      .filter((m: ModelInfo) => m.service_type === 'tts')
  }

  const listVoices = async (model: string): Promise<string[]> => {
    const res = await fetch(
      `${config.public.apiBase}/v1/audio/voices?model=${encodeURIComponent(model)}`,
      { credentials: 'include' },
    )
    if (!res.ok) return []
    return (await res.json())?.voices ?? []
  }

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  const synthesize = async (
    opts: SynthesizeOptions,
    signal?: AbortSignal,
  ): Promise<SynthesizedAudio> => {
    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/audio/speech`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-CSRFToken': token } : {}),
      },
      body: JSON.stringify({
        model: opts.model,
        input: opts.input,
        ...(opts.voice ? { voice: opts.voice } : {}),
        ...(opts.language ? { language: opts.language } : {}),
        ...(opts.response_format ? { response_format: opts.response_format } : {}),
      }),
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    const blob = await res.blob()
    return {
      blob,
      url: URL.createObjectURL(blob),
      contentType: res.headers.get('content-type') || 'audio/wav',
    }
  }

  return { listTtsModels, listVoices, synthesize }
}
