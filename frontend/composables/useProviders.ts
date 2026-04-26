interface ProviderModel {
  id: number
  name: string
  context_window: number | null
  is_active: boolean
}

export interface Provider {
  id: number
  name: string
  callback_url: string
  is_active: boolean
  is_online: boolean
  last_heartbeat_at: string | null
  models: ProviderModel[]
  created_on: string
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

  return {
    providers,
    onlineProviders,
    aggregatedModels,
    isLoading,
    error,
    fetchProviders,
  }
}
