// Client for the speech-to-text playground. Talks to the real
// OpenAI-compatible /v1/audio/transcriptions endpoint with the logged-in
// session (multipart upload), and lists only STT-capable models.

import type { ModelInfo } from '@/composables/usePlayground'
import type { TranscriptionExtras } from '@/types'

export interface TranscriptionResult {
  text: string
  // verbose_json extras, when the model + request support timestamps
  words?: TranscriptionExtras['words']
  segments?: TranscriptionExtras['segments']
  language?: string
  duration?: number
  // metering: audio duration in seconds (usage.seconds)
  seconds?: number | null
  // handle to the persisted INPUT_AUDIO MediaAsset (the user's recording), so
  // the voice turn can be saved to a thread and replayed later.
  audioAssetId?: number
  audioUrl?: string
}

export interface TranscribeOptions {
  model: string
  language?: string
  prompt?: string
  // ask for word/segment timestamps; only honored when the model supports it
  timestamps?: boolean
}

export function useTranscription() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  // Only STT-typed models (audio → text).
  const listSttModels = async (): Promise<ModelInfo[]> => {
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
      .filter((m: ModelInfo) => m.service_type === 'stt')
  }

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  const transcribe = async (
    file: Blob,
    filename: string,
    opts: TranscribeOptions,
    signal?: AbortSignal,
  ): Promise<TranscriptionResult> => {
    const form = new FormData()
    form.append('file', file, filename)
    form.append('model', opts.model)
    if (opts.language) form.append('language', opts.language)
    if (opts.prompt) form.append('prompt', opts.prompt)
    if (opts.timestamps) {
      form.append('response_format', 'verbose_json')
      form.append('timestamp_granularities[]', 'word')
      form.append('timestamp_granularities[]', 'segment')
    }

    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/audio/transcriptions`, {
      method: 'POST',
      credentials: 'include',
      headers: { ...(token ? { 'X-CSRFToken': token } : {}) },
      body: form,
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))

    const data = await res.json()
    const usage = data?.usage as { seconds?: number } | undefined
    return {
      text: data?.text ?? '',
      words: data?.words,
      segments: data?.segments,
      language: data?.language,
      duration: data?.duration,
      seconds: usage?.seconds ?? data?.duration ?? null,
      audioAssetId: data?.audio_asset_id ?? undefined,
      audioUrl: data?.audio_url ?? undefined,
    }
  }

  return { listSttModels, transcribe }
}
