<script setup lang="ts">
import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import { Github, ExternalLink } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/composables/useAuth'
import type { Visibility } from '@/types'
import { VISIBILITY_META, VISIBILITY_ORDER } from '@/utils/visibility'

definePageMeta({
  layout: 'app',
})

const { user, updateAccount } = useAuth()

const githubLogin = computed(() => user.value?.github_login ?? null)

const defaultVisibility = computed<Visibility>(
  () => user.value?.default_request_visibility ?? 'UNLISTED',
)
const profileEnabled = computed(() => user.value?.public_profile_enabled ?? true)

const savingVis = ref(false)
const savingProfile = ref(false)

const onVisibilityChange = async (value: Visibility) => {
  if (value === defaultVisibility.value) return
  savingVis.value = true
  try {
    await updateAccount({ default_request_visibility: value })
    toast.success('Default visibility updated')
  } catch {
    toast.error('Failed to update default visibility')
  } finally {
    savingVis.value = false
  }
}

const onProfileToggle = async (value: boolean) => {
  savingProfile.value = true
  try {
    await updateAccount({ public_profile_enabled: value })
    toast.success(value ? 'Public profile enabled' : 'Public profile hidden')
  } catch {
    toast.error('Failed to update profile setting')
  } finally {
    savingProfile.value = false
  }
}
</script>

<template>
  <div class="mx-auto w-full max-w-2xl px-4 sm:px-6 py-6 space-y-6">
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

    <Card class="p-6 space-y-6">
      <div>
        <h2 class="text-lg font-semibold">Sharing &amp; privacy</h2>
        <p class="text-sm text-muted-foreground mt-1">
          Defaults for new inference requests and your public profile.
        </p>
      </div>

      <div class="space-y-2">
        <Label>Default visibility for new requests</Label>
        <Select
          :model-value="defaultVisibility"
          :disabled="savingVis"
          @update:model-value="(v) => onVisibilityChange(v as Visibility)"
        >
          <SelectTrigger class="w-full sm:max-w-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="v in VISIBILITY_ORDER" :key="v" :value="v">
              {{ VISIBILITY_META[v].label }}
            </SelectItem>
          </SelectContent>
        </Select>
        <p class="text-xs text-muted-foreground">
          {{ VISIBILITY_META[defaultVisibility].description }}
          New requests use this unless you change them individually.
        </p>
      </div>

      <div class="flex items-start justify-between gap-4 pt-4 border-t">
        <div class="min-w-0">
          <Label for="public-profile-switch">Public profile</Label>
          <p class="text-xs text-muted-foreground mt-1">
            When off, your profile at
            <span class="font-mono">/{{ githubLogin || 'you' }}</span>
            is hidden from everyone, regardless of individual request visibility.
          </p>
        </div>
        <Switch
          id="public-profile-switch"
          :model-value="profileEnabled"
          :disabled="savingProfile"
          @update:model-value="onProfileToggle"
        />
      </div>
    </Card>
  </div>
</template>
