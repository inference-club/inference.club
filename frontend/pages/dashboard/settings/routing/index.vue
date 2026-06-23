<script setup lang="ts">
import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import { Network, Server, Lock, Check } from 'lucide-vue-next'
import { useAuth } from '@/composables/useAuth'

definePageMeta({
  layout: 'app',
  requireAuth: true,
  gateTitleKey: 'dashboard.items.routing',
})

type RoutingPref = 'ANY' | 'PREFER_OWN' | 'ONLY_OWN'

const { user, updateAccount } = useAuth()

const current = computed<RoutingPref>(() => user.value?.routing_preference ?? 'ANY')
const saving = ref<RoutingPref | null>(null)

const OPTIONS: { value: RoutingPref; label: string; description: string; icon: typeof Network }[] = [
  {
    value: 'ANY',
    label: 'Use any provider',
    description:
      'Route to any online node that serves the model and that you have access to. The default — maximizes availability across the network.',
    icon: Network,
  },
  {
    value: 'PREFER_OWN',
    label: 'Prefer my own nodes',
    description:
      'Use one of your own nodes whenever it serves the requested model. Fall back to the rest of the network only when none of yours do.',
    icon: Server,
  },
  {
    value: 'ONLY_OWN',
    label: 'Only my own nodes',
    description:
      'Never route to other members. If none of your own nodes serve the model, the request fails instead of going elsewhere.',
    icon: Lock,
  },
]

const select = async (value: RoutingPref) => {
  if (value === current.value || saving.value) return
  saving.value = value
  try {
    await updateAccount({ routing_preference: value })
    toast.success('Routing preference updated')
  } catch {
    toast.error('Failed to update routing preference')
  } finally {
    saving.value = null
  }
}
</script>

<template>
  <div class="mx-auto w-full max-w-2xl px-3 sm:px-6 py-6 space-y-6">
    <div>
      <h1 class="text-2xl font-bold flex items-center gap-2">
        <Network class="h-6 w-6" />
        Routing
      </h1>
      <p class="text-muted-foreground text-sm mt-1">
        When several providers serve the same model, choose which nodes your
        requests are routed to. Applies to all your inference requests.
      </p>
    </div>

    <div class="space-y-3">
      <button
        v-for="opt in OPTIONS"
        :key="opt.value"
        type="button"
        :disabled="saving !== null"
        class="w-full text-left rounded-lg border p-4 transition-colors disabled:opacity-60"
        :class="current === opt.value
          ? 'border-primary bg-primary/[0.04] ring-1 ring-primary/30'
          : 'hover:bg-muted/50'"
        @click="select(opt.value)"
      >
        <div class="flex items-start gap-3">
          <component :is="opt.icon" class="size-5 mt-0.5 shrink-0 text-muted-foreground" />
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="font-medium">{{ opt.label }}</span>
              <Badge v-if="opt.value === 'ANY'" variant="secondary">default</Badge>
            </div>
            <p class="text-sm text-muted-foreground mt-1">{{ opt.description }}</p>
          </div>
          <span
            class="flex size-5 shrink-0 items-center justify-center rounded-full"
            :class="current === opt.value ? 'bg-primary text-primary-foreground' : 'border'"
          >
            <Check v-if="current === opt.value" class="size-3.5" />
          </span>
        </div>
      </button>
    </div>

    <p class="text-xs text-muted-foreground">
      Tip: pair “Only my own nodes” with the
      <NuxtLink to="/dashboard/settings/access" class="underline">Access</NuxtLink>
      settings to control who else can use the models you serve.
    </p>
  </div>
</template>
