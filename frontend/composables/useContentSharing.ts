import { ref } from 'vue'
import type { Collection, InferenceRequest, Visibility } from '@/types'

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

interface ListFilters {
  type?: string
  search?: string
  sort?: string
}

// Sharing & curation API client — visibility edits, stars, bookmarks, and
// collections (docs/prd/01-content-sharing.md). Mirrors useInferenceRequest's
// cookie-session + CSRF conventions.
export function useContentSharing() {
  const config = useRuntimeConfig()
  const loading = ref(false)
  const error = ref<string | null>(null)
  // During SSR (inside the container) the browser-facing apiBase may be
  // unreachable; use the server-only internal base when set. This is what makes
  // public share pages (/s/<token>) render server-side — otherwise the SSR fetch
  // to localhost:<port> fails and the page falls back to "Not available".
  const apiOrigin =
    import.meta.server && config.apiBaseInternal
      ? (config.apiBaseInternal as string)
      : config.public.apiBase
  const base = `${apiOrigin}/api/inference`

  // When SSR fetches through the internal base, the backend builds absolute
  // asset URLs (audio/image/3D) from that internal host — e.g.
  // http://backend:8001/... — which the *browser* can't reach. Rewrite those
  // back to the public origin so the hydrated page points at reachable URLs.
  // No-op in prod, where the internal base is unset and origins already match.
  const publicOrigin = config.public.apiBase
  const rewriteAssetUrls = <T>(data: T): T => {
    if (apiOrigin === publicOrigin) return data
    return JSON.parse(JSON.stringify(data).split(apiOrigin).join(publicOrigin)) as T
  }

  const getCsrfToken = (): string | null => {
    const name = 'csrftoken'
    if (typeof document === 'undefined' || !document.cookie) return null
    for (const raw of document.cookie.split(';')) {
      const cookie = raw.trim()
      if (cookie.startsWith(name + '=')) {
        return decodeURIComponent(cookie.substring(name.length + 1))
      }
    }
    return null
  }

  // Authenticated JSON request with CSRF for mutating verbs.
  const api = async <T>(path: string, options: RequestInit = {}): Promise<T> => {
    const method = (options.method || 'GET').toUpperCase()
    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers as Record<string, string> | undefined),
    }
    if (method !== 'GET') {
      const csrf = getCsrfToken()
      if (csrf) headers['X-CSRFToken'] = csrf
    }
    const resp = await fetch(`${base}${path}`, {
      credentials: 'include',
      ...options,
      method,
      headers,
    })
    if (!resp.ok) {
      throw new Error(`Request failed (${resp.status})`)
    }
    if (resp.status === 204) return undefined as T
    return rewriteAssetUrls((await resp.json()) as T)
  }

  const buildQuery = (limit: number, offset: number, filters: ListFilters = {}) => {
    const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (filters.type) qs.set('type', filters.type)
    if (filters.search) qs.set('search', filters.search)
    if (filters.sort) qs.set('sort', filters.sort)
    return qs.toString()
  }

  const withState = async <T>(fn: () => Promise<T>): Promise<T> => {
    loading.value = true
    error.value = null
    try {
      return await fn()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'An error occurred'
      throw e
    } finally {
      loading.value = false
    }
  }

  // --- visibility -----------------------------------------------------------

  const updateVisibility = (id: string | number, visibility: Visibility) =>
    withState(() =>
      api<InferenceRequest>(`/requests/${id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ visibility }),
      }),
    )

  // --- stars ----------------------------------------------------------------

  const toggleStar = (id: string | number, on: boolean) =>
    withState(() =>
      api<{ is_starred: boolean; star_count: number }>(`/requests/${id}/star/`, {
        method: on ? 'POST' : 'DELETE',
      }),
    )

  const listStarred = (limit = 12, offset = 0, filters: ListFilters = {}) =>
    withState(() =>
      api<PaginatedResponse<InferenceRequest>>(
        `/requests/starred/?${buildQuery(limit, offset, filters)}`,
      ),
    )

  // --- bookmarks ------------------------------------------------------------

  const toggleBookmark = (id: string | number, on: boolean) =>
    withState(() =>
      api<{ is_bookmarked: boolean }>(`/requests/${id}/bookmark/`, {
        method: on ? 'POST' : 'DELETE',
      }),
    )

  const listBookmarked = (limit = 12, offset = 0, filters: ListFilters = {}) =>
    withState(() =>
      api<PaginatedResponse<InferenceRequest>>(
        `/requests/bookmarked/?${buildQuery(limit, offset, filters)}`,
      ),
    )

  // --- moderation -----------------------------------------------------------

  const reportRequest = (
    id: string | number,
    payload: { reason: string; details?: string },
  ) =>
    withState(() =>
      api<{ reported: boolean; already_reported: boolean }>(
        `/requests/${id}/report/`,
        { method: 'POST', body: JSON.stringify(payload) },
      ),
    )

  // --- shared-by-token (public) --------------------------------------------

  const getSharedRequest = (token: string) =>
    withState(() => api<InferenceRequest>(`/shared/${encodeURIComponent(token)}/`))

  const shareUrl = (token?: string | null): string => {
    if (!token) return ''
    const origin = typeof window !== 'undefined' ? window.location.origin : ''
    return `${origin}/s/${token}`
  }

  // --- collections ----------------------------------------------------------

  const listCollections = () =>
    withState(() => api<Collection[]>(`/collections/`))

  const getCollection = (slug: string) =>
    withState(() => api<Collection>(`/collections/${slug}/`))

  const createCollection = (payload: {
    name: string
    description?: string
    visibility?: Visibility
  }) =>
    withState(() =>
      api<Collection>(`/collections/`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    )

  const updateCollection = (
    slug: string,
    payload: Partial<{ name: string; description: string; visibility: Visibility }>,
  ) =>
    withState(() =>
      api<Collection>(`/collections/${slug}/`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    )

  const deleteCollection = (slug: string) =>
    withState(() => api<unknown>(`/collections/${slug}/`, { method: 'DELETE' }))

  const addToCollection = (slug: string, requestId: string | number) =>
    withState(() =>
      api<{ in_collection: boolean }>(`/collections/${slug}/items/${requestId}/`, {
        method: 'POST',
      }),
    )

  const removeFromCollection = (slug: string, requestId: string | number) =>
    withState(() =>
      api<{ in_collection: boolean }>(`/collections/${slug}/items/${requestId}/`, {
        method: 'DELETE',
      }),
    )

  // --- public collections (unauthenticated) ---------------------------------
  // These live under /api/users/<login>/, not /api/inference, so hit them with
  // an absolute URL rather than the `base` prefix.

  const publicGet = async <T>(path: string): Promise<T> => {
    const resp = await fetch(`${apiOrigin}/api${path}`, {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
    if (!resp.ok) throw new Error(`Request failed (${resp.status})`)
    return rewriteAssetUrls((await resp.json()) as T)
  }

  const listPublicCollections = (githubLogin: string) =>
    withState(() =>
      publicGet<Collection[]>(`/users/${encodeURIComponent(githubLogin)}/collections/`),
    )

  const getPublicCollection = (githubLogin: string, slug: string) =>
    withState(() =>
      publicGet<Collection>(
        `/users/${encodeURIComponent(githubLogin)}/collections/${slug}/`,
      ),
    )

  return {
    loading,
    error,
    updateVisibility,
    toggleStar,
    listStarred,
    toggleBookmark,
    listBookmarked,
    reportRequest,
    getSharedRequest,
    shareUrl,
    listCollections,
    getCollection,
    createCollection,
    updateCollection,
    deleteCollection,
    addToCollection,
    removeFromCollection,
    listPublicCollections,
    getPublicCollection,
  }
}
