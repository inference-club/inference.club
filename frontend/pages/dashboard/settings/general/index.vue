<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Github, ExternalLink, VenetianMask, RefreshCw } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/composables/useAuth'
import type { Visibility } from '@/types'
import { VISIBILITY_META, VISIBILITY_ORDER } from '@/utils/visibility'

definePageMeta({
  layout: 'app',
})

const { user, updateAccount, regenerateAlias, isAnonymous } = useAuth()

const githubLogin = computed(() => user.value?.github_login ?? null)
const handle = computed(() => user.value?.handle ?? '')
const aliasOn = computed(() => !!user.value?.use_anon_alias)

// --- anonymous alias (GitHub users only; PRD 08) -------------------------
const savingAlias = ref(false)
const onAliasToggle = async (value: boolean) => {
  const message = value
    ? 'Go anonymous? Your profile moves to a random handle; ' +
      `/${githubLogin.value} will stop working and your GitHub avatar is replaced. ` +
      'You can switch back anytime.'
    : `Use your GitHub handle again? Your profile returns to /${githubLogin.value} ` +
      'and your alias URL stops working (the alias is kept if you switch back).'
  if (!confirm(message)) return
  savingAlias.value = true
  try {
    await updateAccount({ use_anon_alias: value })
    toast.success(value ? `You now go by ${user.value?.handle}` : `Back to ${user.value?.handle}`)
  } catch {
    toast.error('Failed to update alias setting')
  } finally {
    savingAlias.value = false
  }
}

const regenerating = ref(false)
const onRegenerateAlias = async () => {
  if (!confirm('Generate a new alias? Your current alias URL will stop working. Allowed once every 30 days.')) return
  regenerating.value = true
  try {
    await regenerateAlias()
    toast.success(`New alias: ${user.value?.anon_alias}`)
  } catch (e: any) {
    toast.error(e?.data?.detail || 'Could not regenerate alias')
  } finally {
    regenerating.value = false
  }
}

// Anonymous accounts can never publish publicly (the API enforces it too).
const isVisDisabled = (v: Visibility) => v === 'PUBLIC' && isAnonymous.value

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

const defaultCollection = computed(() => user.value?.default_collection_name ?? '')
const collectionDraft = ref(defaultCollection.value)
watch(defaultCollection, (v) => (collectionDraft.value = v))
const savingCollection = ref(false)

const onCollectionSave = async () => {
  const name = collectionDraft.value.trim()
  if (name === defaultCollection.value) return
  savingCollection.value = true
  try {
    await updateAccount({ default_collection_name: name })
    toast.success(name ? `New requests will be saved to “${name}”` : 'Default collection cleared')
  } catch {
    toast.error('Failed to update default collection')
  } finally {
    savingCollection.value = false
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
  <div class="mx-auto w-full max-w-2xl px-3 sm:px-6 py-6 space-y-6">
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
          <dt class="text-muted-foreground">Handle</dt>
          <dd class="flex items-center gap-2">
            <VenetianMask v-if="isAnonymous || aliasOn" class="size-4" />
            <span class="font-mono">{{ handle || '—' }}</span>
          </dd>
        </div>
        <div v-if="githubLogin" class="flex justify-between gap-4">
          <dt class="text-muted-foreground">GitHub</dt>
          <dd class="flex items-center gap-2">
            <Github class="size-4" />
            <span class="font-mono">{{ githubLogin }}</span>
            <span v-if="aliasOn" class="text-xs text-muted-foreground">(hidden publicly)</span>
          </dd>
        </div>
        <div class="flex justify-between gap-4">
          <dt class="text-muted-foreground">Signed in with</dt>
          <dd v-if="isAnonymous" class="flex items-center gap-1.5">
            <VenetianMask class="size-4" />
            {{ user?.account_type === 'GUEST' ? 'Guest session' : 'Passcode' }}
          </dd>
          <dd v-else class="flex items-center gap-1.5">
            <Github class="size-4" /> GitHub
          </dd>
        </div>
        <div v-if="!isAnonymous" class="flex justify-between gap-4">
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

      <p v-if="isAnonymous" class="mt-4 text-xs text-muted-foreground">
        This is an anonymous account: nothing here identifies you, and your
        generations stay unlisted. Sign in with GitHub from the user menu to
        keep it permanently.
      </p>

      <div v-if="handle" class="mt-5 pt-4 border-t">
        <Button as-child variant="outline" size="sm">
          <NuxtLink :to="`/${handle}`">
            <ExternalLink class="size-4" />
            {{ isAnonymous ? 'View unlisted profile' : 'View public profile' }}
          </NuxtLink>
        </Button>
      </div>
    </Card>

    <Card v-if="!isAnonymous" class="p-6 space-y-4">
      <div>
        <h2 class="text-lg font-semibold">Anonymous alias</h2>
        <p class="text-sm text-muted-foreground mt-1">
          Go by a random handle instead of your GitHub name — everywhere:
          profile URL, generations, feeds. A GitHub badge stays on your profile
          (proof it's a real account) but never links to you.
        </p>
      </div>
      <div class="flex items-start justify-between gap-4">
        <div class="min-w-0">
          <Label for="alias-switch">Use an anonymous alias</Label>
          <p class="text-xs text-muted-foreground mt-1">
            <template v-if="aliasOn">
              You currently go by
              <span class="font-mono text-foreground">{{ handle }}</span>.
            </template>
            <template v-else-if="user?.anon_alias">
              Your alias <span class="font-mono">{{ user.anon_alias }}</span> is saved and reused when you switch.
            </template>
            <template v-else>
              An alias is generated the first time you switch.
            </template>
          </p>
        </div>
        <Switch
          id="alias-switch"
          :model-value="aliasOn"
          :disabled="savingAlias"
          @update:model-value="onAliasToggle"
        />
      </div>
      <div v-if="aliasOn" class="pt-3 border-t">
        <Button variant="outline" size="sm" :disabled="regenerating" @click="onRegenerateAlias">
          <RefreshCw class="size-4" :class="{ 'animate-spin': regenerating }" />
          Regenerate alias
        </Button>
        <p class="text-xs text-muted-foreground mt-2">
          Once every 30 days. The old alias URL stops working.
        </p>
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
            <SelectItem
              v-for="v in VISIBILITY_ORDER"
              :key="v"
              :value="v"
              :disabled="isVisDisabled(v)"
            >
              {{ VISIBILITY_META[v].label }}{{ isVisDisabled(v) ? ' — not available for anonymous accounts' : '' }}
            </SelectItem>
          </SelectContent>
        </Select>
        <p class="text-xs text-muted-foreground">
          {{ VISIBILITY_META[defaultVisibility].description }}
          New requests use this unless you change them individually.
        </p>
      </div>

      <div class="space-y-2 pt-4 border-t">
        <Label for="default-collection">Default collection for new requests</Label>
        <div class="flex items-center gap-2">
          <Input
            id="default-collection"
            v-model="collectionDraft"
            placeholder="None"
            class="sm:max-w-xs"
            @keyup.enter="onCollectionSave"
          />
          <Button
            variant="outline"
            size="sm"
            :disabled="savingCollection || collectionDraft.trim() === defaultCollection"
            @click="onCollectionSave"
          >
            Save
          </Button>
        </div>
        <p class="text-xs text-muted-foreground">
          New requests are added to this collection (created on first use).
          Leave empty for none.
        </p>
      </div>

      <div class="flex items-start justify-between gap-4 pt-4 border-t">
        <div class="min-w-0">
          <Label for="public-profile-switch">{{ isAnonymous ? 'Unlisted profile' : 'Public profile' }}</Label>
          <p class="text-xs text-muted-foreground mt-1">
            When off, your profile at
            <span class="font-mono">/{{ handle || 'you' }}</span>
            is hidden from everyone, regardless of individual request visibility.
            <template v-if="isAnonymous">
              Your profile is never listed anywhere — only people you give the
              link to can find it.
            </template>
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
