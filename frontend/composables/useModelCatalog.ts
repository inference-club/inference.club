// Network model catalog — one entry per logical model (CatalogModel), with
// operator-declared capabilities and which nodes serve it.
import { ref } from 'vue'

export interface CatalogProvider {
  name: string
  online: boolean
}

export interface CatalogModelItem {
  slug: string
  display_name: string
  hf_repo_id: string
  hf_url: string
  is_custom: boolean
  context_length: number | null
  input_modalities: string[]
  output_modalities: string[]
  supported_features: string[]
  provider_count: number
  online_provider_count: number
  providers: CatalogProvider[]
}

export function useModelCatalog() {
  const config = useRuntimeConfig()
  const models = ref<CatalogModelItem[]>([])
  // Start truthy so SSR/first paint shows the skeleton, not a flash of the
  // "no models yet" empty state before the client fetch runs.
  const loading = ref(true)
  const error = ref('')

  // By default the catalog shows only models runnable right now (≥1 online
  // node). Pass true to also include offline/retired deployments.
  const fetchModels = async (includeOffline = false) => {
    loading.value = true
    error.value = ''
    try {
      const qs = includeOffline ? '?include_offline=1' : ''
      const res = await fetch(`${config.public.apiBase}/api/inference/models/${qs}`, {
        credentials: 'include',
      })
      if (!res.ok) throw new Error(`Failed to load models (HTTP ${res.status})`)
      const data = await res.json()
      models.value = data.models ?? []
    } catch (e: unknown) {
      error.value = (e as { message?: string })?.message || 'Failed to load models'
    } finally {
      loading.value = false
    }
  }

  return { models, loading, error, fetchModels }
}
