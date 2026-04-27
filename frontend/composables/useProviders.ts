import type { OwnerServiceManifest } from '@/composables/useManifest'

interface ProviderModel {
  id: number
  name: string
  context_window: number | null
  is_active: boolean
}

export interface Provider {
  id: number
  name: string
  tailnet_hostname: string
  agent_port: number
  is_active: boolean
  is_online: boolean
  registered_at: string | null
  last_seen_at: string | null
  models: ProviderModel[]
  manifest: OwnerServiceManifest | null
  created_on: string
}

export interface PublicProvider extends Provider {
  owner: string
  github_login: string | null
}

export const useProviders = () => {
  const config = useRuntimeConfig()
  const providers = ref<Provider[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const fetchProviders = async () => {
    isLoading.value = true
    error.value = null
    try {
      const data = await $fetch<Provider[]>(`${config.public.apiBase}/api/inference/providers/`, {
        credentials: 'include',
      })
      providers.value = data
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load providers'
    } finally {
      isLoading.value = false
    }
  }

  const onlineProviders = computed(() => providers.value.filter(p => p.is_online))

  const aggregatedModels = computed(() => {
    const seen = new Map<string, { name: string; providers: string[] }>()
    for (const p of onlineProviders.value) {
      for (const m of p.models) {
        if (!m.is_active) continue
        const entry = seen.get(m.name) ?? { name: m.name, providers: [] }
        entry.providers.push(p.name)
        seen.set(m.name, entry)
      }
    }
    return Array.from(seen.values())
  })

  const refreshModels = async (providerId: number) => {
    isLoading.value = true
    error.value = null
    try {
      const csrfToken = import.meta.client
        ? document.cookie
            .split('; ')
            .find(c => c.startsWith('csrftoken='))
            ?.split('=')[1]
        : undefined
      await $fetch(
        `${config.public.apiBase}/api/inference/providers/${providerId}/refresh-models/`,
        {
          method: 'POST',
          credentials: 'include',
          headers: csrfToken ? { 'X-CSRFToken': csrfToken } : {},
        },
      )
      await fetchProviders()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to refresh models'
    } finally {
      isLoading.value = false
    }
  }

  return {
    providers,
    onlineProviders,
    aggregatedModels,
    isLoading,
    error,
    fetchProviders,
    refreshModels,
  }
}

export const useAllProviders = () => {
  const config = useRuntimeConfig()
  const providers = ref<PublicProvider[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const fetchAllProviders = async () => {
    isLoading.value = true
    error.value = null
    try {
      const data = await $fetch<PublicProvider[]>(
        `${config.public.apiBase}/api/inference/providers/all/`,
        { credentials: 'include' },
      )
      providers.value = data
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load network nodes'
    } finally {
      isLoading.value = false
    }
  }

  return { providers, isLoading, error, fetchAllProviders }
}
