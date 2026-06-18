// Authenticated client for saved chat threads (ChatGPT/Claude-style history).
// Talks to the session-authenticated /api/inference/threads/ endpoints — NOT
// the /v1 proxy. Mirrors useInferenceRequest's auth + pagination conventions.
import { ref } from 'vue'
import type { ChatUsage, TokenLogprob } from '@/composables/usePlayground'

// One persisted turn. Mirrors the playground's in-memory Msg, minus transient
// UI state, plus the logprobs/usage we want to keep.
export interface StoredMessage {
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  usage?: ChatUsage
  logprobs?: TokenLogprob[]
  reasoningLogprobs?: TokenLogprob[]
  model?: string
}

// Slim card returned by the list endpoint (no messages blob).
export interface ChatThreadSummary {
  public_id: string
  title: string
  model: string
  message_count: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  has_logprobs: boolean
  title_generated: boolean
  created_on: string
  modified_on: string
}

// Full thread from the detail/create endpoint.
export interface ChatThreadDetail extends ChatThreadSummary {
  messages: StoredMessage[]
}

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface ChatThreadWrite {
  model?: string
  title?: string
  messages: StoredMessage[]
}

export function useChatThreads() {
  const config = useRuntimeConfig()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const base = `${config.public.apiBase}/api/inference/threads`

  const getCsrfToken = () => {
    const name = 'csrftoken'
    if (document.cookie && document.cookie !== '') {
      for (const raw of document.cookie.split(';')) {
        const cookie = raw.trim()
        if (cookie.startsWith(name + '=')) {
          return decodeURIComponent(cookie.substring(name.length + 1))
        }
      }
    }
    return null
  }

  const listThreads = async (limit = 10, offset = 0) => {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(`${base}/?limit=${limit}&offset=${offset}`, {
        credentials: 'include',
      })
      if (!res.ok) throw new Error('Failed to fetch chats')
      return (await res.json()) as PaginatedResponse<ChatThreadSummary>
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'An error occurred'
      throw e
    } finally {
      loading.value = false
    }
  }

  const getThread = async (id: string) => {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(`${base}/${id}/`, { credentials: 'include' })
      if (!res.ok) {
        throw new Error(res.status === 404 ? 'Chat not found' : 'Failed to fetch chat')
      }
      return (await res.json()) as ChatThreadDetail
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'An error occurred'
      throw e
    } finally {
      loading.value = false
    }
  }

  const createThread = async (data: ChatThreadWrite) => {
    const csrf = getCsrfToken()
    const res = await fetch(`${base}/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRFToken': csrf } : {}) },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to save chat')
    return (await res.json()) as ChatThreadDetail
  }

  const updateThread = async (id: string, data: Partial<ChatThreadWrite>) => {
    const csrf = getCsrfToken()
    const res = await fetch(`${base}/${id}/`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRFToken': csrf } : {}) },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to update chat')
    return (await res.json()) as ChatThreadDetail
  }

  const deleteThread = async (id: string) => {
    const csrf = getCsrfToken()
    const res = await fetch(`${base}/${id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: csrf ? { 'X-CSRFToken': csrf } : undefined,
    })
    if (!res.ok && res.status !== 204) throw new Error('Failed to delete chat')
  }

  return { loading, error, listThreads, getThread, createThread, updateThread, deleteThread }
}
