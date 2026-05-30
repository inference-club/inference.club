<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Boxes, Cpu, Eye, Mic, Type, Video, Zap } from 'lucide-vue-next'
import { useNetworkStatus } from '@/composables/useNetworkStatus'

useHead({
  title: 'Network status · inference.club',
  meta: [
    {
      name: 'description',
      content: 'A live look at the inference.club network — online nodes, available models, and tokens served.',
    },
  ],
})

const { status, error, loading, fetchStatus } = useNetworkStatus()
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  fetchStatus()
  // Auto-refresh for a "live" feel.
  timer = setInterval(fetchStatus, 15000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const fmt = (n: number | null | undefined) => {
  const v = n ?? 0
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1000) return `${(v / 1000).toFixed(1)}K`
  return `${v}`
}

const MODALITY_ICON: Record<string, unknown> = { text: Type, image: Eye, audio: Mic, video: Video }

const maxDay = computed(() =>
  Math.max(1, ...(status.value?.daily_tokens ?? []).map((d) => d.tokens))
)
const updatedAt = computed(() => {
  if (!status.value) return ''
  try {
    return new Date(status.value.generated_at).toLocaleTimeString()
  } catch {
    return ''
  }
})
</script>

<template>
  <div class="relative overflow-hidden min-h-screen">
    <!-- Ambient gradient, matching the homepage -->
    <div class="pointer-events-none absolute inset-0 -z-10">
      <div class="absolute inset-x-0 top-0 h-[600px] bg-[radial-gradient(ellipse_at_top,rgba(139,92,246,0.16),transparent_55%)]" />
    </div>

    <section class="px-4 sm:px-6 lg:px-8 pt-16 pb-20 max-w-6xl mx-auto">
      <!-- Header -->
      <div class="text-center mb-10">
        <div class="inline-flex items-center gap-2 rounded-full border bg-background/60 backdrop-blur px-3 py-1 text-xs font-mono mb-5 shadow-sm">
          <span class="relative flex h-2 w-2">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
            <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <span class="text-muted-foreground">live</span>
          <span v-if="updatedAt" class="text-foreground">· updated {{ updatedAt }}</span>
        </div>
        <h1 class="text-4xl sm:text-5xl font-bold tracking-tight">The network, right now</h1>
        <p class="mt-4 text-muted-foreground max-w-2xl mx-auto">
          inference.club is a community network of home GPUs serving an OpenAI-compatible API.
          Here's what's online and what it's doing.
        </p>
      </div>

      <div v-if="error" class="p-4 bg-destructive/10 text-destructive rounded text-sm max-w-md mx-auto">
        {{ error }}
      </div>

      <!-- Stat tiles -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <Card v-for="(tile, i) in [
          { label: 'Nodes online', value: status ? `${status.providers.online}` : '–', sub: status ? `of ${status.providers.total} registered` : '', icon: Cpu },
          { label: 'Models available', value: status ? `${status.models_available}` : '–', sub: 'right now', icon: Boxes },
          { label: 'Tokens · 24h', value: status ? fmt(status.tokens.last_24h) : '–', sub: status ? `${fmt(status.tokens.total)} all-time` : '', icon: Zap },
          { label: 'Requests · 24h', value: status ? `${status.requests.last_24h}` : '–', sub: status ? `${fmt(status.requests.total)} all-time` : '', icon: Zap },
        ]" :key="i" class="p-5">
          <div class="flex items-center justify-between text-muted-foreground">
            <span class="text-xs uppercase tracking-wide">{{ tile.label }}</span>
            <component :is="tile.icon" class="size-4" />
          </div>
          <div class="mt-2 text-3xl font-bold tabular-nums">
            <span v-if="loading && !status" class="inline-block h-8 w-16 rounded bg-muted animate-pulse" />
            <template v-else>{{ tile.value }}</template>
          </div>
          <div class="text-xs text-muted-foreground mt-1">{{ tile.sub }}</div>
        </Card>
      </div>

      <!-- Tokens chart -->
      <Card class="mt-4 p-5">
        <h2 class="text-sm font-semibold mb-4">Tokens served · last 30 days</h2>
        <div class="flex items-end gap-1 h-32">
          <div
            v-for="d in status?.daily_tokens ?? []"
            :key="d.date"
            class="flex-1 rounded-t bg-gradient-to-t from-violet-500/70 to-fuchsia-500/70 min-h-[2px] transition-all"
            :style="{ height: `${Math.max(2, (d.tokens / maxDay) * 100)}%` }"
            :title="`${d.date}: ${d.tokens.toLocaleString()} tokens`"
          />
          <div v-if="!status" class="text-xs text-muted-foreground self-center mx-auto">Loading…</div>
        </div>
      </Card>

      <div class="grid lg:grid-cols-2 gap-4 mt-4">
        <!-- Models -->
        <Card class="p-5">
          <h2 class="text-sm font-semibold mb-3 flex items-center gap-2">
            <Boxes class="size-4" /> Available models
          </h2>
          <div v-if="!status?.models?.length" class="text-sm text-muted-foreground">
            {{ status ? 'No models online right now.' : 'Loading…' }}
          </div>
          <ul v-else class="space-y-2">
            <li v-for="m in status.models" :key="m.slug" class="flex items-center justify-between gap-2 text-sm">
              <div class="min-w-0">
                <div class="font-medium truncate">{{ m.display_name }}</div>
                <code class="text-xs text-muted-foreground break-all">{{ m.slug }}</code>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <component
                  :is="MODALITY_ICON[mod]"
                  v-for="mod in m.input_modalities"
                  :key="mod"
                  class="size-3.5 text-muted-foreground"
                />
                <Badge variant="secondary">{{ m.online_provider_count }} node{{ m.online_provider_count === 1 ? '' : 's' }}</Badge>
              </div>
            </li>
          </ul>
        </Card>

        <!-- Nodes -->
        <Card class="p-5">
          <h2 class="text-sm font-semibold mb-3 flex items-center gap-2">
            <Cpu class="size-4" /> Online nodes
          </h2>
          <div v-if="!status?.nodes?.length" class="text-sm text-muted-foreground">
            {{ status ? 'No nodes online right now.' : 'Loading…' }}
          </div>
          <ul v-else class="space-y-2">
            <li v-for="(n, i) in status.nodes" :key="i" class="flex items-center justify-between gap-2 text-sm">
              <div class="flex items-center gap-2 min-w-0">
                <span class="size-2 rounded-full bg-emerald-500 shrink-0" />
                <span class="font-medium truncate">{{ n.name }}</span>
                <NuxtLink
                  v-if="n.github_login"
                  :to="`/${n.github_login}`"
                  class="text-xs text-muted-foreground hover:text-foreground truncate"
                >@{{ n.github_login }}</NuxtLink>
              </div>
              <Badge variant="outline" class="shrink-0">{{ n.model_count }} model{{ n.model_count === 1 ? '' : 's' }}</Badge>
            </li>
          </ul>
        </Card>
      </div>

      <div class="text-center mt-10">
        <NuxtLink to="/dashboard">
          <Button size="lg">Join the network</Button>
        </NuxtLink>
      </div>
    </section>
  </div>
</template>
