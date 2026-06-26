// Client for managing the user's external-service API keys (Brave, ElevenLabs,
// …). Talks to the session-authenticated /api/inference/api-keys endpoints.
// Keys are write-only: the server returns only an is_set flag + masked hint.

export interface ApiKeyInfo {
  service: string
  name: string
  description: string
  docs_url: string
  // 'tool' or 'llm_provider' (external LLM clouds you can pin models from — PRD 19).
  category: string
  is_set: boolean
  hint: string
  updated: string | null
}

export function useApiKeys() {
  const config = useRuntimeConfig()
  const base = `${config.public.apiBase}/api/inference/api-keys`

  const csrf = () =>
    document.cookie.split('; ').find((c) => c.startsWith('csrftoken='))?.split('=')[1]

  const list = async (): Promise<ApiKeyInfo[]> => {
    const res = await fetch(`${base}/`, { credentials: 'include' })
    if (!res.ok) throw new Error('Failed to load API keys')
    return (await res.json()).data ?? []
  }

  const setKey = async (service: string, value: string) => {
    const t = csrf()
    const res = await fetch(`${base}/${service}/`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(t ? { 'X-CSRFToken': t } : {}) },
      body: JSON.stringify({ value }),
    })
    if (!res.ok) throw new Error('Failed to save key')
    return res.json()
  }

  const clearKey = async (service: string) => {
    const t = csrf()
    const res = await fetch(`${base}/${service}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: t ? { 'X-CSRFToken': t } : undefined,
    })
    if (!res.ok) throw new Error('Failed to clear key')
    return res.json()
  }

  return { list, setKey, clearKey }
}
