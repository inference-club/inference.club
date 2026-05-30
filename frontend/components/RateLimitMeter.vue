<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Gauge } from 'lucide-vue-next'

interface ScopeUsage {
  scope: string
  limit: number
  used: number
  remaining: number
  duration_seconds: number
  reset_in_seconds: number
}

const config = useRuntimeConfig()
const scopes = ref<ScopeUsage[]>([])
const loaded = ref(false)
let timer: ReturnType<typeof setInterval> | undefined

const SCOPE_LABELS: Record<string, string> = {
  inference: 'Chat & completions',
  models: 'Model list',
}

const fetchUsage = async () => {
  try {
    const res = await fetch(`${config.public.apiBase}/api/inference/usage/`, {
      credentials: 'include',
    })
    if (res.ok) {
      const data = await res.json()
      scopes.value = data.scopes ?? []
    }
  } catch {
    // Best-effort widget — ignore transient errors.
  } finally {
    loaded.value = true
  }
}

const pct = (s: ScopeUsage) =>
  s.limit ? Math.min(100, Math.round((s.used / s.limit) * 100)) : 0

const barClass = (s: ScopeUsage) => {
  const p = pct(s)
  return p >= 90 ? 'bg-destructive' : p >= 70 ? 'bg-amber-500' : 'bg-primary'
}

const period = (s: ScopeUsage) =>
  s.duration_seconds === 60
    ? 'min'
    : s.duration_seconds === 3600
      ? 'hour'
      : `${s.duration_seconds}s`

onMounted(() => {
  fetchUsage()
  timer = setInterval(fetchUsage, 10000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <Card class="p-4">
    <div class="flex items-center justify-between mb-3">
      <h2 class="font-semibold flex items-center gap-2">
        <Gauge class="size-4 text-primary" /> Your rate-limit usage
      </h2>
      <button class="text-xs text-muted-foreground hover:text-foreground" @click="fetchUsage">
        Refresh
      </button>
    </div>

    <div v-if="scopes.length" class="space-y-3">
      <div v-for="s in scopes" :key="s.scope">
        <div class="flex justify-between text-sm mb-1">
          <span>{{ SCOPE_LABELS[s.scope] || s.scope }}</span>
          <span class="font-mono text-muted-foreground">
            {{ s.used }} / {{ s.limit }} per {{ period(s) }}
          </span>
        </div>
        <div class="h-2 rounded-full bg-muted overflow-hidden">
          <div
            class="h-full rounded-full transition-all"
            :class="barClass(s)"
            :style="{ width: pct(s) + '%' }"
          />
        </div>
        <p class="text-xs text-muted-foreground mt-0.5">
          {{ s.remaining }} remaining<template v-if="s.used > 0">
            · a slot frees in {{ s.reset_in_seconds }}s</template>
        </p>
      </div>
    </div>
    <p v-else-if="loaded" class="text-sm text-muted-foreground">No recent activity.</p>
  </Card>
</template>
