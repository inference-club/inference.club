// Client for the video-generation playground. Talks to the OpenAI-style
// extension endpoint POST /v1/videos/generations (JSON in, raw MP4 bytes out)
// with the logged-in session. The backend forwards to a `video` service
// (LTX-2); the agent streams the rendered MP4 back in one reply, so a result
// here is simply a video blob. We display it from the persisted VIDEO request
// (in the recent strip), so the returned blob is only used to release its URL.

import type { ModelInfo } from '@/composables/usePlayground'

export interface VideoOptions {
  model: string
  prompt: string
  negative_prompt?: string
  // First-frame conditioning image as a data URI (image-to-video). Omit for
  // pure text-to-video.
  image?: string
  image_strength?: number
  duration?: number
  num_frames?: number
  fps?: number
  width?: number
  height?: number
  seed?: number
  use_random_seed?: boolean
  num_inference_steps?: number
  guidance_scale?: number
  enhance_prompt?: boolean
}

export interface GeneratedVideo {
  blob: Blob
  url: string // object URL
  contentType: string
}

export function useVideoGeneration() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  // Only text/image-to-video models (prompt → video).
  const listVideoModels = async (): Promise<ModelInfo[]> => {
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
      .filter((m: ModelInfo) => m.service_type === 'video')
  }

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  // Prompt (+ optional first-frame image & controls) → a rendered video.
  const generate = async (opts: VideoOptions, signal?: AbortSignal): Promise<GeneratedVideo> => {
    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/videos/generations`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-CSRFToken': token } : {}),
      },
      body: JSON.stringify({
        model: opts.model,
        prompt: opts.prompt,
        ...(opts.negative_prompt ? { negative_prompt: opts.negative_prompt } : {}),
        ...(opts.image ? { image: opts.image, image_strength: opts.image_strength ?? 1 } : {}),
        ...(opts.duration ? { duration: opts.duration } : {}),
        ...(opts.num_frames ? { num_frames: opts.num_frames } : {}),
        ...(opts.fps ? { fps: opts.fps } : {}),
        ...(opts.width ? { width: opts.width } : {}),
        ...(opts.height ? { height: opts.height } : {}),
        ...(opts.num_inference_steps ? { num_inference_steps: opts.num_inference_steps } : {}),
        ...(opts.guidance_scale != null ? { guidance_scale: opts.guidance_scale } : {}),
        ...(opts.enhance_prompt ? { enhance_prompt: true } : {}),
        ...(opts.use_random_seed === false ? { seed: opts.seed } : {}),
      }),
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    const blob = await res.blob()
    return {
      blob,
      url: URL.createObjectURL(blob),
      contentType: res.headers.get('content-type') || 'video/mp4',
    }
  }

  return { listVideoModels, generate }
}
