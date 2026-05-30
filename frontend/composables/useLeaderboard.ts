import { ref } from 'vue'

export type LeaderboardRange = 'hour' | 'day' | 'week' | 'month' | 'year' | 'all'

export interface LeaderboardEntry {
  rank: number
  owner: string
  github_login: string | null
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  requests: number
}

export function useLeaderboard() {
  const config = useRuntimeConfig()
  const entries = ref<LeaderboardEntry[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const fetchLeaderboard = async (range: LeaderboardRange = 'day') => {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(
        `${config.public.apiBase}/api/inference/leaderboard/?range=${range}`,
        { credentials: 'include' }
      )
      if (!res.ok) throw new Error('Failed to load leaderboard')
      const data = await res.json()
      entries.value = data.results ?? []
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load leaderboard'
    } finally {
      loading.value = false
    }
  }

  return { entries, loading, error, fetchLeaderboard }
}
