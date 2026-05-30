// Public, unauthenticated snapshot of the live network for the status page.
import { ref } from 'vue'

export interface NetworkStatus {
  generated_at: string
  providers: { online: number; total: number }
  models_available: number
  tokens: { total: number; last_24h: number }
  requests: { total: number; last_24h: number }
  daily_tokens: { date: string; tokens: number }[]
  models: {
    slug: string
    display_name: string
    input_modalities: string[]
    supported_features: string[]
    online_provider_count: number
  }[]
  nodes: { name: string; github_login: string | null; model_count: number }[]
}

export function useNetworkStatus() {
  const config = useRuntimeConfig()
  const status = ref<NetworkStatus | null>(null)
  const error = ref('')
  const loading = ref(true)

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${config.public.apiBase}/api/inference/network/`)
      if (!res.ok) throw new Error(`Failed to load network status (HTTP ${res.status})`)
      status.value = await res.json()
      error.value = ''
    } catch (e: unknown) {
      error.value = (e as { message?: string })?.message || 'Failed to load network status'
    } finally {
      loading.value = false
    }
  }

  return { status, error, loading, fetchStatus }
}
