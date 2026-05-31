<script setup lang="ts">
import { computed } from 'vue'
import { Github, ExternalLink } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/composables/useAuth'

definePageMeta({
  layout: 'app',
})

const { user } = useAuth()

const githubLogin = computed(() => user.value?.github_login ?? null)
</script>

<template>
  <div class="container max-w-2xl mx-auto p-6 space-y-6">
    <div>
      <h1 class="text-2xl font-bold">General</h1>
      <p class="text-muted-foreground text-sm mt-1">
        Account information and preferences.
      </p>
    </div>

    <Card class="p-6">
      <h2 class="text-lg font-semibold mb-4">Account</h2>
      <dl class="space-y-3 text-sm">
        <div class="flex justify-between gap-4">
          <dt class="text-muted-foreground">GitHub</dt>
          <dd v-if="githubLogin" class="flex items-center gap-2">
            <Github class="size-4" />
            <span class="font-mono">{{ githubLogin }}</span>
          </dd>
          <dd v-else class="text-muted-foreground">—</dd>
        </div>
        <div class="flex justify-between gap-4">
          <dt class="text-muted-foreground">Signed in with</dt>
          <dd class="flex items-center gap-1.5">
            <Github class="size-4" /> GitHub
          </dd>
        </div>
        <div class="flex justify-between gap-4">
          <dt class="text-muted-foreground">Email</dt>
          <dd class="font-mono">{{ user?.email ?? '—' }}</dd>
        </div>
        <div class="flex justify-between gap-4">
          <dt class="text-muted-foreground">Status</dt>
          <dd>{{ user?.is_active ? 'Active' : 'Inactive' }}</dd>
        </div>
        <div v-if="user?.is_staff" class="flex justify-between gap-4">
          <dt class="text-muted-foreground">Role</dt>
          <dd>{{ user.is_superuser ? 'Superuser' : 'Staff' }}</dd>
        </div>
      </dl>

      <div v-if="githubLogin" class="mt-5 pt-4 border-t">
        <Button as-child variant="outline" size="sm">
          <NuxtLink :to="`/${githubLogin}`">
            <ExternalLink class="size-4" />
            View public profile
          </NuxtLink>
        </Button>
      </div>
    </Card>

    <Card class="p-6">
      <h2 class="text-lg font-semibold mb-2">Coming soon</h2>
      <p class="text-sm text-muted-foreground">
        Display name, profile preferences, and account deletion will land here.
      </p>
    </Card>
  </div>
</template>
