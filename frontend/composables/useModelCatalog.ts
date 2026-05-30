// Network model catalog — one entry per logical model (CatalogModel),
// HuggingFace-enriched, with which nodes serve it.
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
  architecture: string
  context_length: number | null
  input_modalities: string[]
  output_modalities: string[]
  supported_features: string[]
  pipeline_tag: string | null
  downloads: number | null
  likes: number | null
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

  const fetchModels = async () => {
    loading.value = true
    error.value = ''
    try {
      const res = await fetch(`${config.public.apiBase}/api/inference/models/`, {
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
