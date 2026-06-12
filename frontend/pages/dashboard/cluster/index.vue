<script setup lang="ts">
// Living Cluster, owner view (PRD 07). Same scene as the public
// /[github_login]/cluster page, plus what only the owner should see: exact
// pod commands on the service cards, and a provider picker when more than
// one agent runs kubernetes discovery.
import { Boxes, ExternalLink } from 'lucide-vue-next'
import { useProviders } from '@/composables/useProviders'
import { buildClusterSnapshot, useClusterState } from '@/composables/useClusterState'
import { useAuthStore } from '@/stores/auth'

definePageMeta({
  layout: 'app',
})

const auth = useAuthStore()
const { providers, isLoading, fetchProviders } = useProviders()

const k8sProviders = computed(() =>
  providers.value.filter(
    p => p.manifest?.is_valid && p.manifest.parsed.discovery === 'kubernetes',
  ),
)

const selectedId = ref<number | null>(null)
const provider = computed(
  () =>
    k8sProviders.value.find(p => p.id === selectedId.value) ??
    k8sProviders.value[0] ??
    null,
)

const { state, start, refresh } = useClusterState(() => provider.value?.id)

onMounted(async () => {
  await fetchProviders()
  if (provider.value) start()
})

// Providers load async, and the picker can switch agents — (re)start or
// refetch against whichever provider is current. start() is idempotent.
watch(provider, (p, prev) => {
  if (!p) return
  if (!prev) start()
  else if (p.id !== prev.id) void refresh()
})

const snapshot = computed(() =>
  buildClusterSnapshot(provider.value?.manifest?.parsed, state.value),
)

const publicUrl = computed(() =>
  auth.user?.github_login && provider.value
    ? `/${auth.user.github_login}/cluster?provider=${provider.value.id}`
    : null,
)

useHead({ title: 'Cluster — inference.club' })
</script>

<template>
  <div class="flex h-[calc(100vh-7rem)] min-h-[480px] flex-col px-3 sm:px-6 py-4">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="flex items-center gap-2 text-2xl font-bold">
          <Boxes class="size-6 text-muted-foreground" /> Living cluster
        </h1>
        <p class="mt-1 text-sm text-muted-foreground">
          Your Kubernetes fleet, as discovered by the agent — machines, GPUs,
          memory, and the inference services running on them.
        </p>
      </div>
      <div class="flex items-center gap-3">
        <select
          v-if="k8sProviders.length > 1"
          v-model.number="selectedId"
          class="rounded-md border bg-background px-2 py-1.5 text-sm"
        >
          <option v-for="p in k8sProviders" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
        <NuxtLink
          v-if="publicUrl"
          :to="publicUrl"
          class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ExternalLink class="size-4" /> Public view
        </NuxtLink>
      </div>
    </div>

    <div v-if="isLoading && !provider" class="flex flex-1 items-center justify-center">
      <p class="text-sm text-muted-foreground">Loading providers…</p>
    </div>

    <div
      v-else-if="!provider"
      class="flex flex-1 items-center justify-center rounded-lg border bg-card px-4 text-center"
    >
      <div class="max-w-lg py-12 text-sm text-muted-foreground">
        <p>
          No kubernetes-discovered cluster yet. Run the agent inside your
          cluster with <code class="text-foreground">AGENT_DISCOVERY=kubernetes</code>
          and label your Services
          <code class="text-foreground">inference-club.com/managed=true</code> —
          the manifest (and this scene) builds itself from what's actually running.
        </p>
      </div>
    </div>

    <ClusterScene
      v-else-if="snapshot"
      :snapshot="snapshot"
      :show-commands="true"
      class="flex-1 rounded-lg border bg-card"
    />
  </div>
</template>
