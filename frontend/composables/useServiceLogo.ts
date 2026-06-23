// Upload / remove a custom logo for one of the caller's services.
// Mirrors the multipart-upload shape used by useVoiceCloning: a FormData POST
// with the session cookie (credentials) + CSRF token. The logo then surfaces
// through the manifest's enriched parsed services (svc.logo_url).
export function useServiceLogo() {
  const config = useRuntimeConfig()
  const apiBase = config.public.apiBase as string

  const csrf = (): string | null => {
    if (typeof document === 'undefined' || !document.cookie) return null
    const hit = document.cookie.split('; ').find((c) => c.startsWith('csrftoken='))
    return hit ? decodeURIComponent(hit.split('=')[1]) : null
  }

  const _detail = async (res: Response) => {
    try {
      const e = await res.json()
      return e?.detail || e?.error?.message || `Request failed (HTTP ${res.status})`
    } catch {
      return `Request failed (HTTP ${res.status})`
    }
  }

  const base = (serviceId: number) =>
    `${apiBase}/api/inference/services/${serviceId}/logo/`

  // Returns the new public logo URL.
  const upload = async (serviceId: number, file: File): Promise<string> => {
    const fd = new FormData()
    fd.append('logo', file, file.name || 'logo')
    const token = csrf()
    const res = await fetch(base(serviceId), {
      method: 'POST',
      credentials: 'include',
      headers: { ...(token ? { 'X-CSRFToken': token } : {}) },
      body: fd,
    })
    if (!res.ok) throw new Error(await _detail(res))
    const data = await res.json()
    return data.logo_url as string
  }

  const remove = async (serviceId: number): Promise<void> => {
    const token = csrf()
    const res = await fetch(base(serviceId), {
      method: 'DELETE',
      credentials: 'include',
      headers: { ...(token ? { 'X-CSRFToken': token } : {}) },
    })
    if (!res.ok && res.status !== 204) throw new Error(await _detail(res))
  }

  return { upload, remove }
}
