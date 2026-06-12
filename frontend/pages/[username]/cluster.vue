<script setup lang="ts">
// Living Cluster, public view (PRD 07): /[github_login]/cluster renders the
// provider's Kubernetes fleet in 3D from their k8s-derived manifest, with
// live state layered on via the cluster proxy. Linked from the provider
// profile. Owners get the richer /dashboard/cluster (commands shown there).
import { ArrowLeft, Boxes } from 'lucide-vue-next'
import type { ParsedManifest, PublicProfile } from '@/composables/useManifest'
import {
  buildClusterSnapshot,
  useClusterHistory,
  useClusterState,
} from '@/composables/useClusterState'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const config = useRuntimeConfig()
const auth = useAuthStore()

const username = computed(() => String(route.params.username || ''))

const apiBase =
  import.meta.server && config.apiBaseInternal
    ? config.apiBaseInternal
    : config.public.apiBase

const { data, error } = await useFetch<PublicProfile>(
  () => `${apiBase}/api/users/${encodeURIComponent(username.value)}/`,
  { credentials: 'include' },
)

if (error.value) {
  const status = (error.value as { statusCode?: number }).statusCode ?? 500
  throw createError({
    statusCode: status === 404 ? 404 : 500,
    statusMessage:
      status === 404
        ? `No inference.club profile for @${username.value}`
        : 'Failed to load profile',
    fatal: true,
  })
}

// The provider to render: ?provider=<id> when the profile links a specific
// agent, else the first one with a kubernetes-derived manifest.
const k8sProviders = computed(() =>
  (data.value?.providers ?? []).filter(
    p => p.manifest?.is_valid && p.manifest.parsed.discovery === 'kubernetes',
  ),
)
const provider = computed(() => {
  const wanted = Number(route.query.provider)
  return (
    k8sProviders.value.find(p => p.id === wanted) ?? k8sProviders.value[0] ?? null
  )
})

const { state, activity, start } = useClusterState(() => provider.value?.id)
const { revisions, loadHistory, fetchRevision } = useClusterHistory(() => provider.value?.id)
onMounted(() => {
  if (provider.value) {
    start()
    void loadHistory()
  }
})

// Story mode (V3): a selected revision freezes the scene at that moment —
// live state and request pulses only apply to the live view.
const storyRevisionId = ref<number | null>(null)
const storyManifest = ref<ParsedManifest | null>(null)
watch(storyRevisionId, async (id) => {
  storyManifest.value = id == null ? null : await fetchRevision(id)
})

const snapshot = computed(() =>
  storyRevisionId.value != null && storyManifest.value
    ? buildClusterSnapshot(storyManifest.value)
    : buildClusterSnapshot(provider.value?.manifest?.parsed, state.value, activity.value),
)

const isOwner = computed(
  () => auth.isAuthenticated && auth.user?.github_login === data.value?.github_login,
)

useHead({
  title: () => `@${username.value} — cluster · inference.club`,
})
</script>

<template>
  <div class="flex h-[calc(100vh-4rem)] min-h-[480px] flex-col">
    <div class="flex items-center gap-3 px-4 py-3">
      <NuxtLink
        :to="`/${username}`"
        class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft class="size-4" /> @{{ username }}
      </NuxtLink>
      <div class="flex items-center gap-2">
        <Boxes class="size-4 text-muted-foreground" />
        <h1 class="text-lg font-semibold">Living cluster</h1>
        <span v-if="provider" class="text-sm text-muted-foreground font-mono">{{ provider.name }}</span>
      </div>
    </div>

    <div v-if="!provider" class="flex flex-1 items-center justify-center px-4 text-center">
      <p class="max-w-md text-sm text-muted-foreground">
        @{{ username }} has no kubernetes-discovered cluster to show yet.
        Agents running with <code class="text-foreground">AGENT_DISCOVERY=kubernetes</code> light this page up.
      </p>
    </div>

    <template v-else-if="snapshot">
      <ClusterScene
        :snapshot="snapshot"
        :show-commands="isOwner"
        class="flex-1"
      />
      <div class="px-4 pb-3">
        <ClusterStoryBar v-model="storyRevisionId" :revisions="revisions" />
      </div>
    </template>
  </div>
</template>
