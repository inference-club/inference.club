// Client for the image-generation playground. Talks to the real
// OpenAI-compatible /v1/images/{generations,edits} endpoints with the
// logged-in session. The backend stores each image in MinIO and returns an
// inference.club URL by default, so results are just <img src> URLs.

import type { ModelInfo } from '@/composables/usePlayground'

export interface GeneratedImage {
  url?: string
  b64_json?: string
  revised_prompt?: string
}

export interface GenerateOptions {
  model: string
  prompt: string
  n?: number
  size?: string
  quality?: string
}

export function useImageGeneration() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  // Only image-generation models (text → image).
  const listImageModels = async (): Promise<ModelInfo[]> => {
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
      .filter((m: ModelInfo) => m.service_type === 'image')
  }

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  // Text → image.
  const generate = async (
    opts: GenerateOptions,
    signal?: AbortSignal,
  ): Promise<GeneratedImage[]> => {
    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/images/generations`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-CSRFToken': token } : {}),
      },
      body: JSON.stringify({
        model: opts.model,
        prompt: opts.prompt,
        ...(opts.n ? { n: opts.n } : {}),
        ...(opts.size ? { size: opts.size } : {}),
        ...(opts.quality ? { quality: opts.quality } : {}),
      }),
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    return (await res.json())?.data ?? []
  }

  // Source image(s) + prompt → edited image. A single source uses the classic
  // `image` field; several references go through `image[]` — models like
  // FLUX.2 Klein fuse multiple reference images into one result.
  const edit = async (
    images: { blob: Blob; name: string }[],
    opts: GenerateOptions,
    signal?: AbortSignal,
  ): Promise<GeneratedImage[]> => {
    const form = new FormData()
    if (images.length === 1) {
      form.append('image', images[0].blob, images[0].name)
    } else {
      for (const img of images) form.append('image[]', img.blob, img.name)
    }
    form.append('model', opts.model)
    form.append('prompt', opts.prompt)
    if (opts.n) form.append('n', String(opts.n))
    if (opts.size) form.append('size', opts.size)

    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/images/edits`, {
      method: 'POST',
      credentials: 'include',
      headers: { ...(token ? { 'X-CSRFToken': token } : {}) },
      body: form,
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    return (await res.json())?.data ?? []
  }

  return { listImageModels, generate, edit }
}
