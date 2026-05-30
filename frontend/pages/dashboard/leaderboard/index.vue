<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { Trophy, Github } from 'lucide-vue-next'
import { useLeaderboard, type LeaderboardRange } from '@/composables/useLeaderboard'

definePageMeta({
  layout: 'app',
})

const { entries, loading, error, fetchLeaderboard } = useLeaderboard()

const RANGES: { value: LeaderboardRange; label: string }[] = [
  { value: 'hour', label: 'Hour' },
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'year', label: 'Year' },
  { value: 'all', label: 'All time' },
]

const range = ref<LeaderboardRange>('day')

watch(range, (r) => fetchLeaderboard(r))
onMounted(() => fetchLeaderboard(range.value))

const fmt = (n: number) => n.toLocaleString()
const medal = (rank: number) =>
  rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : ''
</script>

<template>
  <div class="container mx-auto py-6 max-w-3xl">
    <div class="mb-4">
      <h1 class="text-2xl font-bold flex items-center gap-2">
        <Trophy class="h-6 w-6 text-amber-500" />
        Token Leaderboard
      </h1>
      <p class="text-sm text-muted-foreground mt-1">
        Top token consumers across inference.club.
      </p>
    </div>

    <!-- Range toggle -->
    <div class="inline-flex flex-wrap rounded-lg border p-1 mb-5 gap-1">
      <button
        v-for="r in RANGES"
        :key="r.value"
        class="px-3 py-1 text-sm rounded-md transition-colors"
        :class="range === r.value
          ? 'bg-primary text-primary-foreground'
          : 'text-muted-foreground hover:text-foreground hover:bg-accent'"
        @click="range = r.value"
      >
        {{ r.label }}
      </button>
    </div>

    <div v-if="loading && entries.length === 0" class="space-y-2">
      <div v-for="i in 5" :key="i" class="h-12 bg-muted rounded animate-pulse" />
    </div>

    <div v-else-if="error" class="p-4 bg-destructive/10 text-destructive rounded text-sm">
      {{ error }}
    </div>

    <Card v-else-if="entries.length === 0" class="p-6 text-center text-muted-foreground">
      No inference activity in this period yet.
    </Card>

    <Card v-else class="overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-muted/50 text-muted-foreground">
          <tr>
            <th class="text-left font-medium px-4 py-2 w-12">#</th>
            <th class="text-left font-medium px-4 py-2">Member</th>
            <th class="text-right font-medium px-4 py-2">Tokens</th>
            <th class="text-right font-medium px-4 py-2 hidden sm:table-cell">In / Out</th>
            <th class="text-right font-medium px-4 py-2">Requests</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="e in entries"
            :key="e.rank"
            class="border-t"
            :class="e.rank <= 3 ? 'bg-amber-500/5' : ''"
          >
            <td class="px-4 py-2 font-semibold">{{ medal(e.rank) || e.rank }}</td>
            <td class="px-4 py-2">
              <a
                v-if="e.github_login"
                :href="`https://github.com/${e.github_login}`"
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex items-center gap-1.5 font-medium hover:text-primary transition-colors"
              >
                <Github class="size-3.5" /> {{ e.github_login }}
              </a>
              <span v-else class="font-medium">{{ e.owner }}</span>
            </td>
            <td class="px-4 py-2 text-right font-mono font-semibold">{{ fmt(e.total_tokens) }}</td>
            <td class="px-4 py-2 text-right font-mono text-muted-foreground hidden sm:table-cell">
              {{ fmt(e.prompt_tokens) }} / {{ fmt(e.completion_tokens) }}
            </td>
            <td class="px-4 py-2 text-right font-mono text-muted-foreground">{{ fmt(e.requests) }}</td>
          </tr>
        </tbody>
      </table>
    </Card>
  </div>
</template>
