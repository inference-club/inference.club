// Client for the audio-enhancement playground (NVIDIA Maxine Studio Voice).
// Talks to the real OpenAI-compatible /v1/audio/enhance endpoint with the
// logged-in session (multipart upload), and lists only audio-enhance models.
// Audio file IN → cleaned audio file OUT (raw bytes).

import type { ModelInfo } from '@/composables/usePlayground'

export interface EnhanceOptions {
  model: string
  responseFormat?: string
}

export interface EnhanceResult {
  // the cleaned audio blob returned by the endpoint
  blob: Blob
  contentType: string
}

export function useAudioEnhance() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  // Only audio-enhance-typed models (audio → cleaned audio).
  const listEnhanceModels = async (): Promise<ModelInfo[]> => {
    const res = await fetch(`${config.public.apiBase}/v1/models`, {
      credentials: 'include',
    })
    if (!res.ok) throw new Error(`Failed to load models (HTTP ${res.status})`)
    const data = await res.json()
    return (data.data ?? [])
      .map((m: Partial<ModelInfo> & { id: string }) => ({
        id: m.id,
        input_modalities: m.input_modalities ?? ['audio'],
        supported_features: m.supported_features ?? [],
        context_length: m.context_length ?? null,
        service_type: m.service_type ?? 'llm',
      }))
      .filter((m: ModelInfo) => m.service_type === 'audio-enhance')
  }

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  const enhance = async (
    file: Blob,
    filename: string,
    opts: EnhanceOptions,
    signal?: AbortSignal,
  ): Promise<EnhanceResult> => {
    const form = new FormData()
    form.append('file', file, filename)
    form.append('model', opts.model)
    if (opts.responseFormat) form.append('response_format', opts.responseFormat)

    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/audio/enhance`, {
      method: 'POST',
      credentials: 'include',
      headers: { ...(token ? { 'X-CSRFToken': token } : {}) },
      body: form,
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))

    const blob = await res.blob()
    return {
      blob,
      contentType: res.headers.get('content-type') || blob.type || 'audio/wav',
    }
  }

  return { listEnhanceModels, enhance }
}
