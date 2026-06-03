import { ref } from 'vue'
import type { InferenceRequest } from '@/types'

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export function useInferenceRequest() {
  const config = useRuntimeConfig()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const getCsrfToken = () => {
    const name = 'csrftoken'
    let cookieValue = null
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';')
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim()
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1))
          break
        }
      }
    }
    return cookieValue
  }

  const createInferenceRequest = async (data: Partial<InferenceRequest>) => {
    loading.value = true
    error.value = null

    try {
      const csrfToken = getCsrfToken()
      if (!csrfToken) {
        throw new Error('CSRF token not found')
      }

      const response = await fetch(`${config.public.apiBase}/api/inference/requests/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        credentials: 'include',
        body: JSON.stringify(data),
      })

      if (!response.ok) {
        throw new Error('Failed to create inference request')
      }

      return await response.json()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'An error occurred'
      throw e
    } finally {
      loading.value = false
    }
  }

  // Optional filters shared by the list endpoints: ?type=IMAGE narrows to a
  // modality, ?search= matches the stored prompt / model name.
  interface ListFilters { type?: string; search?: string }
  const buildQuery = (limit: number, offset: number, filters: ListFilters = {}) => {
    const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (filters.type) qs.set('type', filters.type)
    if (filters.search) qs.set('search', filters.search)
    return qs.toString()
  }

  const listInferenceRequests = async (
    limit: number = 10,
    offset: number = 0,
    filters: ListFilters = {},
  ) => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(
        `${config.public.apiBase}/api/inference/requests/?${buildQuery(limit, offset, filters)}`,
        {
          credentials: 'include',
        }
      )

      if (!response.ok) {
        throw new Error('Failed to fetch inference requests')
      }

      return await response.json() as PaginatedResponse<InferenceRequest>
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'An error occurred'
      throw e
    } finally {
      loading.value = false
    }
  }

  const listAllInferenceRequests = async (
    limit: number = 10,
    offset: number = 0,
    filters: ListFilters = {},
  ) => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(
        `${config.public.apiBase}/api/inference/requests/all/?${buildQuery(limit, offset, filters)}`,
        { credentials: 'include' }
      )

      if (!response.ok) {
        throw new Error('Failed to fetch inference requests')
      }

      return await response.json() as PaginatedResponse<InferenceRequest>
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'An error occurred'
      throw e
    } finally {
      loading.value = false
    }
  }

  // Public, unauthenticated listing of a user's requests for their profile.
  // scope: 'consumed' = requests they made, 'served' = requests their nodes served.
  const listPublicUserRequests = async (
    githubLogin: string,
    scope: 'consumed' | 'served' = 'consumed',
    limit: number = 10,
    offset: number = 0,
    filters: ListFilters = {},
  ) => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(
        `${config.public.apiBase}/api/users/${encodeURIComponent(githubLogin)}/requests/`
          + `?scope=${scope}&${buildQuery(limit, offset, filters)}`,
        { credentials: 'include' }
      )

      if (!response.ok) {
        throw new Error('Failed to fetch inference requests')
      }

      return await response.json() as PaginatedResponse<InferenceRequest>
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'An error occurred'
      throw e
    } finally {
      loading.value = false
    }
  }

  const getInferenceRequest = async (id: string) => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(
        `${config.public.apiBase}/api/inference/requests/${id}/`,
        { credentials: 'include' }
      )

      if (!response.ok) {
        throw new Error(
          response.status === 404
            ? 'Inference request not found'
            : 'Failed to fetch inference request'
        )
      }

      return await response.json() as InferenceRequest
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'An error occurred'
      throw e
    } finally {
      loading.value = false
    }
  }

  const deleteInferenceRequest = async (id: string) => {
    loading.value = true
    error.value = null

    try {
      const csrfToken = getCsrfToken()
      const response = await fetch(
        `${config.public.apiBase}/api/inference/requests/${id}/`,
        {
          method: 'DELETE',
          headers: csrfToken ? { 'X-CSRFToken': csrfToken } : undefined,
          credentials: 'include',
        }
      )

      // DRF returns 204 No Content on a successful destroy.
      if (!response.ok && response.status !== 204) {
        throw new Error('Failed to delete inference request')
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'An error occurred'
      throw e
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    createInferenceRequest,
    listInferenceRequests,
    listAllInferenceRequests,
    listPublicUserRequests,
    getInferenceRequest,
    deleteInferenceRequest,
  }
}