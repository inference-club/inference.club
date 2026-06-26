// Shared client for the /v1/files Media Library API (PRD 17 §5).
//
// One place every surface (chat, agent, the library, the per-modality
// playgrounds) uploads media through — instead of re-implementing
// FileReader → FormData + a CSRF helper on each page. An upload returns a
// stable, opaque MediaAsset reference (`public_id` + gated `url`) that can be
// referenced in a chat message, a generation request, or browsed in the
// library.

// One stored media asset, mirroring MediaAssetDetailSerializer.
export interface MediaFile {
  id: number
  public_id: string
  kind: string // INPUT_IMAGE | INPUT_AUDIO | INPUT_VIDEO | INPUT_DOC | OUTPUT_*
  visibility: string // PUBLIC | UNLISTED | PRIVATE | SECRET
  content_type: string
  size_bytes: number | null
  duration_seconds: number | null
  metadata?: Record<string, unknown>
  url: string // gated content URL (/api/inference/assets/<public_id>/)
  produced_by?: { request_id: number; type: string } | null
  derived_from?: { id: number; kind: string }[]
  derivatives?: { id: number; kind: string }[]
  created_on: string
}

export interface MediaFileList {
  object: 'list'
  total: number
  limit: number
  offset: number
  data: MediaFile[]
}

export interface ListFilesParams {
  kind?: string
  bound?: 'true' | 'false'
  q?: string
  limit?: number
  offset?: number
}

export function useUploads() {
  const config = useRuntimeConfig()
  const base = `${config.public.apiBase}/v1/files`

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  const _errorMessage = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.error?.message || e?.detail || JSON.stringify(e)
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  // Upload a file. `kind` is optional — the backend detects it from the
  // content type; pass it to force a specific MediaAsset kind.
  const uploadFile = async (
    file: Blob,
    opts: { name?: string; kind?: string } = {},
    signal?: AbortSignal,
  ): Promise<MediaFile> => {
    const form = new FormData()
    form.append('file', file, opts.name || (file as File).name || 'upload')
    if (opts.kind) form.append('kind', opts.kind)
    const token = csrf()
    const res = await fetch(base, {
      method: 'POST',
      credentials: 'include',
      headers: { ...(token ? { 'X-CSRFToken': token } : {}) },
      body: form,
      signal,
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    return (await res.json()) as MediaFile
  }

  // List the caller's own media (owner-scoped on the server).
  const listFiles = async (params: ListFilesParams = {}): Promise<MediaFileList> => {
    const qs = new URLSearchParams()
    if (params.kind) qs.set('kind', params.kind)
    if (params.bound) qs.set('bound', params.bound)
    if (params.q) qs.set('q', params.q)
    if (params.limit != null) qs.set('limit', String(params.limit))
    if (params.offset != null) qs.set('offset', String(params.offset))
    const res = await fetch(`${base}?${qs.toString()}`, { credentials: 'include' })
    if (!res.ok) throw new Error(await _errorMessage(res))
    return (await res.json()) as MediaFileList
  }

  const getFile = async (ref: string): Promise<MediaFile> => {
    const res = await fetch(`${base}/${ref}`, { credentials: 'include' })
    if (!res.ok) throw new Error(await _errorMessage(res))
    return (await res.json()) as MediaFile
  }

  const updateFile = async (
    ref: string,
    patch: { visibility?: string; metadata?: Record<string, unknown> },
  ): Promise<MediaFile> => {
    const token = csrf()
    const res = await fetch(`${base}/${ref}`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(token ? { 'X-CSRFToken': token } : {}) },
      body: JSON.stringify(patch),
    })
    if (!res.ok) throw new Error(await _errorMessage(res))
    return (await res.json()) as MediaFile
  }

  const deleteFile = async (ref: string): Promise<void> => {
    const token = csrf()
    const res = await fetch(`${base}/${ref}`, {
      method: 'DELETE',
      credentials: 'include',
      headers: token ? { 'X-CSRFToken': token } : undefined,
    })
    if (!res.ok && res.status !== 204) throw new Error(await _errorMessage(res))
  }

  return { uploadFile, listFiles, getFile, updateFile, deleteFile }
}
