import { ref } from 'vue'

function getCookie(name: string) {
  if (typeof document === 'undefined') return undefined; // SSR guard
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()!.split(';').shift();
}

interface TokenResponse {
  token: string
}

interface DeleteResponse {
  detail: string
}

interface TokenPrefix {
  id: string
  prefix: string
}

export const useToken = () => {
  const token = ref<string | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const config = useRuntimeConfig()
  const tokens = ref<TokenPrefix[]>([])

  const csrfToken = import.meta.client ? getCookie('csrftoken') : undefined

  const refreshTokens = async () => {
    if (!import.meta.client) return
    try {
      const headers = csrfToken ? { 'X-CSRFToken': csrfToken } : undefined
      const { data, error: fetchError } = await useFetch<{ tokens: TokenPrefix[] }>(`${config.public.apiBase}/api/token/list/`, {
        method: 'GET',
        credentials: 'include',
        headers,
      })
      console.log('Fetched tokens:', data.value, fetchError.value)
      if (fetchError.value) {
        throw new Error(fetchError.value.message)
      }
      if (data.value && Array.isArray(data.value.tokens)) {
        tokens.value = data.value.tokens
        console.log('Assigned tokens.value:', tokens.value)
      }
    } catch (err) {
      // Optionally handle error
      console.error('Error fetching tokens:', err)
    }
  }

  const createToken = async () => {
    isLoading.value = true
    error.value = null

    try {
      const headers = csrfToken ? { 'X-CSRFToken': csrfToken } : undefined
      const { data, error: fetchError } = await useFetch<TokenResponse>(`${config.public.apiBase}/api/token/`, {
        method: 'POST',
        credentials: 'include',
        headers,
      })

      if (fetchError.value) {
        throw new Error(fetchError.value.message)
      }

      if (data.value && 'token' in data.value) {
        token.value = data.value.token
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to create token'
    } finally {
      isLoading.value = false
    }
  }

  const deleteToken = async () => {
    isLoading.value = true
    error.value = null

    try {
      const headers = csrfToken ? { 'X-CSRFToken': csrfToken } : undefined
      const { error: fetchError } = await useFetch<DeleteResponse>(`${config.public.apiBase}/api/token/`, {
        method: 'DELETE',
        credentials: 'include',
        headers,
      })

      if (fetchError.value) {
        throw new Error(fetchError.value.message)
      }

      token.value = null
      await refreshTokens()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to delete token'
    } finally {
      isLoading.value = false
    }
  }

  if (import.meta.client) {
    refreshTokens()
  }

  return {
    token,
    tokens,
    isLoading,
    error,
    createToken,
    deleteToken,
    refreshTokens
  }
}