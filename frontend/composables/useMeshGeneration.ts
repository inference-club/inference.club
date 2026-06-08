// Client for the image-to-3D playground. Talks to the OpenAI-style extension
// endpoint POST /v1/3d/generations (multipart: image + options JSON) with the
// logged-in session. The backend stores the GLB in MinIO and returns its
// inference.club URL plus generation metadata, so a result is just a model URL
// to drop into <ModelViewer>.

import type { ModelInfo } from '@/composables/usePlayground'
import type { MeshMeta } from '@/types'

export interface MeshOptions {
  resolution?: string
  seed?: number
  randomize_seed?: boolean
}

export interface MeshResult {
  url: string | null
  metadata: MeshMeta
  requestId: string
}

export function useMeshGeneration() {
  const config = useRuntimeConfig()

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  // Only image-to-3D models (image → 3D mesh).
  const listMeshModels = async (): Promise<ModelInfo[]> => {
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
      .filter((m: ModelInfo) => m.service_type === 'mesh')
  }

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  // Source image + options → textured GLB.
  const generate = async (
    image: Blob,
    filename: string,
    model: string,
    options: MeshOptions,
    signal?: AbortSignal,
  ): Promise<MeshResult> => {
    const form = new FormData()
    form.append('image', image, filename)
    form.append('model', model)
    form.append('options', JSON.stringify(options))

    const token = csrf()
    const res = await fetch(`${config.public.apiBase}/v1/3d/generations`, {
      method: 'POST',
      credentials: 'include',
      headers: { ...(token ? { 'X-CSRFToken': token } : {}) },
      body: form,
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    const body = await res.json()
    return {
      url: body?.data?.[0]?.url ?? null,
      metadata: body?.metadata ?? {},
      requestId: String(body?.request_id ?? ''),
    }
  }

  return { listMeshModels, generate }
}
