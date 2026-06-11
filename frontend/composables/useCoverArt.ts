// Cover-art generation (docs/prd/06-media-playback-experience.md, phase 5).
// Reuses the production image pipeline: generate a square image via
// /v1/images/generations (which stores a normal IMAGE request + OUTPUT_IMAGE
// asset and returns its request_id), then link it as a track or playlist
// cover via the cover endpoints in useContentSharing.

import type { ModelInfo } from '@/composables/usePlayground'

export interface CoverResult {
  requestId: string
  url: string
}

const COVER_SIZE = '1024x1024'

const IMPROVE_SYSTEM = `You are an art director writing prompts for an AI image generator that makes square album cover art. Rewrite the user's draft into one vivid, concrete prompt: strong central visual concept, art style/medium, color palette, lighting, composition. No typography or text in the image. Respond with ONLY the rewritten prompt — no quotes, no preamble.`

export function useCoverArt() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  const _models = async (serviceType: string): Promise<ModelInfo[]> => {
    const res = await fetch(`${config.public.apiBase}/v1/models`, {
      credentials: 'include',
    })
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
      .filter((m: ModelInfo) => m.service_type === serviceType)
  }

  const listImageModels = () => _models('image')
  const listChatModels = () => _models('llm')

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  /** One LLM pass turning a song/playlist description into a tight art prompt. */
  const improvePrompt = async (
    model: string,
    draft: string,
    signal?: AbortSignal,
  ): Promise<string> => {
    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/chat/completions`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-CSRFToken': token } : {}),
      },
      body: JSON.stringify({
        model,
        messages: [
          { role: 'system', content: IMPROVE_SYSTEM },
          { role: 'user', content: draft },
        ],
        stream: false,
        temperature: 0.9,
        max_tokens: 400,
      }),
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    const data = await res.json()
    const content: string = data?.choices?.[0]?.message?.content ?? ''
    if (!content.trim()) throw new Error('The model returned an empty reply')
    return content.trim().replace(/^["']|["']$/g, '')
  }

  /** Generate one square cover candidate; returns the stored request + URL. */
  const generateCover = async (
    model: string,
    prompt: string,
    signal?: AbortSignal,
  ): Promise<CoverResult> => {
    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/images/generations`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-CSRFToken': token } : {}),
      },
      body: JSON.stringify({ model, prompt, n: 1, size: COVER_SIZE }),
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    const data = await res.json()
    const url: string | undefined = data?.data?.[0]?.url
    const requestId: string | undefined = data?.request_id
    if (!url || !requestId) throw new Error('No image came back from the model')
    return { requestId, url }
  }

  return { listImageModels, listChatModels, improvePrompt, generateCover }
}
