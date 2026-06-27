import { ref } from 'vue'

export type AccessPolicy = 'PRIVATE' | 'AUTHENTICATED' | 'RESTRICTED'

export interface ProviderServiceItem {
  id: number
  provider: { id: number; name: string }
  name: string
  host_id: string
  engine: string
  is_active: boolean
  access_policy: AccessPolicy
  allowed_github_users: string[]
  models: string[]
}

export interface HostAccessItem {
  id: number
  provider_id: number
  host_id: string
  hostname: string
  is_active: boolean
  access_policy: AccessPolicy
  allowed_github_users: string[]
}

export function useServices() {
  const config = useRuntimeConfig()
  const services = ref<ProviderServiceItem[]>([])
  const hosts = ref<HostAccessItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const getCsrf = () => {
    if (!import.meta.client) return null
    return (
      document.cookie
        .split('; ')
        .find((c) => c.startsWith('csrftoken='))
        ?.split('=')[1] ?? null
    )
  }

  const fetchServices = async () => {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(`${config.public.apiBase}/api/inference/services/`, {
        credentials: 'include',
      })
      if (!res.ok) throw new Error('Failed to load services')
      const data = await res.json()
      services.value = Array.isArray(data) ? data : (data.results ?? [])
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load services'
    } finally {
      loading.value = false
    }
  }

  const updateService = async (
    id: number,
    payload: { access_policy: AccessPolicy; allowed_github_users: string[] }
  ) => {
    const csrf = getCsrf()
    const res = await fetch(`${config.public.apiBase}/api/inference/services/${id}/`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...(csrf ? { 'X-CSRFToken': csrf } : {}),
      },
      credentials: 'include',
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error('Failed to update service')
    return (await res.json()) as ProviderServiceItem
  }

  const fetchHosts = async () => {
    try {
      const res = await fetch(`${config.public.apiBase}/api/inference/hosts/`, {
        credentials: 'include',
      })
      if (!res.ok) throw new Error('Failed to load nodes')
      const data = await res.json()
      hosts.value = Array.isArray(data) ? data : (data.results ?? [])
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load nodes'
    }
  }

  const updateHost = async (
    id: number,
    payload: { access_policy: AccessPolicy; allowed_github_users: string[] }
  ) => {
    const csrf = getCsrf()
    const res = await fetch(`${config.public.apiBase}/api/inference/hosts/${id}/`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...(csrf ? { 'X-CSRFToken': csrf } : {}),
      },
      credentials: 'include',
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error('Failed to update node')
    return (await res.json()) as HostAccessItem
  }

  return { services, hosts, loading, error, fetchServices, updateService, fetchHosts, updateHost }
}
