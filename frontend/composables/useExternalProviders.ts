// Browse + pin models from external LLM providers (OpenRouter/NVIDIA/Groq).
// Talks to /api/inference/providers/<slug>/{models,pins} (PRD 19 §5).

export interface CatalogModel {
  model_id: string
  display_name: string
  context_length: number | null
  input_modalities: string[]
  pinned: boolean
}

export function useExternalProviders() {
  const config = useRuntimeConfig()
  const base = `${config.public.apiBase}/api/inference/providers`

  const csrf = () =>
    document.cookie
      .split('; ')
      .find((c) => c.startsWith('csrftoken='))
      ?.split('=')[1]

  const headers = () => {
    const token = csrf()
    return { 'Content-Type': 'application/json', ...(token ? { 'X-CSRFToken': token } : {}) }
  }

  const _err = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.detail || e?.error?.message || `Request failed (HTTP ${res.status})`
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  // The provider's catalog (annotated with the user's pins).
  const browse = async (slug: string, q = '', refresh = false): Promise<CatalogModel[]> => {
    const qs = new URLSearchParams()
    if (q) qs.set('q', q)
    if (refresh) qs.set('refresh', '1')
    const res = await fetch(`${base}/${slug}/models?${qs.toString()}`, { credentials: 'include' })
    if (!res.ok) throw new Error(await _err(res))
    return (await res.json()).data ?? []
  }

  const pin = async (slug: string, model: CatalogModel): Promise<void> => {
    const res = await fetch(`${base}/${slug}/pins`, {
      method: 'POST',
      credentials: 'include',
      headers: headers(),
      body: JSON.stringify({
        model_id: model.model_id,
        display_name: model.display_name,
        context_length: model.context_length,
        input_modalities: model.input_modalities,
      }),
    })
    if (!res.ok) throw new Error(await _err(res))
  }

  const unpin = async (slug: string, modelId: string): Promise<void> => {
    const res = await fetch(`${base}/${slug}/pins`, {
      method: 'DELETE',
      credentials: 'include',
      headers: headers(),
      body: JSON.stringify({ model_id: modelId }),
    })
    if (!res.ok && res.status !== 204) throw new Error(await _err(res))
  }

  return { browse, pin, unpin }
}
