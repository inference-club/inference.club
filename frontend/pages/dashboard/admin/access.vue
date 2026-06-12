<script setup lang="ts">
// Staff-only anonymous-access control panel (PRD 08): the live policy knobs,
// passcode minting/revocation, and guest account management. Everything here
// takes effect immediately — no deploy.
import { onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import {
  Copy, KeyRound, Loader2, Plus, RefreshCw, ShieldOff, Trash2, VenetianMask,
} from 'lucide-vue-next'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  useAdmin,
  type AccessCode,
  type AnonAccessPolicy,
  type GuestAccount,
} from '@/composables/useAdmin'

definePageMeta({
  layout: 'app',
  middleware: 'staff',
})

const {
  loading, error,
  getAccessPolicy, updateAccessPolicy,
  listAccessCodes, createAccessCode, updateAccessCode,
  listGuests, revokeGuest, purgeGuest,
} = useAdmin()

const policy = ref<AnonAccessPolicy | null>(null)
const codes = ref<AccessCode[]>([])
const guests = ref<GuestAccount[]>([])

const load = async () => {
  try {
    const [p, c, g] = await Promise.all([
      getAccessPolicy(),
      listAccessCodes(),
      listGuests(),
    ])
    policy.value = p
    codes.value = c.codes
    guests.value = g.guests
  } catch {
    // surfaced via `error`
  }
}
onMounted(load)

// --- policy ---------------------------------------------------------------

const savePolicy = async (payload: Partial<AnonAccessPolicy>) => {
  try {
    policy.value = await updateAccessPolicy(payload)
    toast.success('Policy updated')
  } catch {
    toast.error('Failed to update policy — check the values')
  }
}

// Draft fields saved on blur/button (rates, cap, message); switches save live.
const saveDrafts = () => {
  if (!policy.value) return
  savePolicy({
    max_active_guests: policy.value.max_active_guests,
    guest_creation_rate: policy.value.guest_creation_rate,
    passcode_attempt_rate: policy.value.passcode_attempt_rate,
    anon_inference_rate: policy.value.anon_inference_rate,
    anon_models_rate: policy.value.anon_models_rate,
    guest_message: policy.value.guest_message,
  })
}

// --- passcodes ---------------------------------------------------------------

const newLabel = ref('')
const creating = ref(false)

const onCreateCode = async () => {
  creating.value = true
  try {
    const code = await createAccessCode({ label: newLabel.value.trim() })
    codes.value = [code, ...codes.value]
    newLabel.value = ''
    await copyCode(code)
    toast.success(`Code for ${code.handle} created and copied`)
  } catch {
    toast.error('Failed to create code')
  } finally {
    creating.value = false
  }
}

const copyCode = async (code: AccessCode) => {
  try {
    await navigator.clipboard.writeText(code.code)
    toast.success('Code copied')
  } catch {
    toast.error('Could not copy')
  }
}

const toggleCode = async (code: AccessCode) => {
  const revoking = code.is_active
  if (
    revoking &&
    !confirm(`Revoke "${code.label || code.handle}"? Their session ends immediately; content stays.`)
  ) return
  try {
    const updated = await updateAccessCode(code.id, { is_active: !code.is_active })
    codes.value = codes.value.map((c) => (c.id === code.id ? updated : c))
    toast.success(revoking ? 'Code revoked' : 'Code reactivated')
  } catch {
    toast.error('Failed to update code')
  }
}

// --- guests --------------------------------------------------------------------

const onRevokeGuest = async (g: GuestAccount) => {
  if (!confirm(`Revoke guest ${g.handle}? Their session ends immediately; content stays.`)) return
  try {
    const updated = await revokeGuest(g.id)
    guests.value = guests.value.map((x) => (x.id === g.id ? updated : x))
    toast.success('Guest revoked')
  } catch {
    toast.error('Failed to revoke guest')
  }
}

const onPurgeGuest = async (g: GuestAccount) => {
  if (
    !confirm(
      `PURGE guest ${g.handle}? This permanently deletes the account and its ${g.request_count} generation(s). This cannot be undone.`,
    )
  ) return
  try {
    await purgeGuest(g.id)
    guests.value = guests.value.filter((x) => x.id !== g.id)
    toast.success('Guest purged')
  } catch {
    toast.error('Failed to purge guest')
  }
}

const fmtDate = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '—')
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-3 sm:px-6 py-6 space-y-8">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">Anonymous access</h1>
        <p class="text-muted-foreground text-sm mt-1">
          Guest sign-in, passcodes, and the live rollout knobs. Changes apply immediately.
        </p>
      </div>
      <Button variant="outline" size="sm" :disabled="loading" @click="load">
        <RefreshCw class="size-4" :class="{ 'animate-spin': loading }" />
        Refresh
      </Button>
    </div>

    <div v-if="error" class="p-4 bg-destructive/10 text-destructive rounded">
      {{ error }}
    </div>

    <!-- Policy -->
    <Card v-if="policy" class="p-6 space-y-5">
      <h2 class="text-lg font-semibold">Policy</h2>

      <div class="flex items-start justify-between gap-4">
        <div>
          <Label for="guest-switch">Guest sign-in</Label>
          <p class="text-xs text-muted-foreground mt-1">
            Shows the "Try anonymously" button on the login page.
          </p>
        </div>
        <Switch
          id="guest-switch"
          :model-value="policy.guest_signin_enabled"
          @update:model-value="(v: boolean) => savePolicy({ guest_signin_enabled: v })"
        />
      </div>

      <div class="flex items-start justify-between gap-4 pt-4 border-t">
        <div>
          <Label for="passcode-switch">Passcode sign-in</Label>
          <p class="text-xs text-muted-foreground mt-1">
            Shows the passcode field on the login page (existing sessions are unaffected).
          </p>
        </div>
        <Switch
          id="passcode-switch"
          :model-value="policy.passcode_signin_enabled"
          @update:model-value="(v: boolean) => savePolicy({ passcode_signin_enabled: v })"
        />
      </div>

      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 pt-4 border-t">
        <div class="space-y-1.5">
          <Label>Max active guests (0 = unlimited)</Label>
          <Input v-model.number="policy.max_active_guests" type="number" min="0" />
        </div>
        <div class="space-y-1.5">
          <Label>Guest creation rate (per IP)</Label>
          <Input v-model="policy.guest_creation_rate" placeholder="5/hour" class="font-mono" />
        </div>
        <div class="space-y-1.5">
          <Label>Passcode attempts (per IP)</Label>
          <Input v-model="policy.passcode_attempt_rate" placeholder="10/hour" class="font-mono" />
        </div>
        <div class="space-y-1.5">
          <Label>Anon inference rate</Label>
          <Input v-model="policy.anon_inference_rate" placeholder="15/min" class="font-mono" />
        </div>
        <div class="space-y-1.5">
          <Label>Anon models rate</Label>
          <Input v-model="policy.anon_models_rate" placeholder="60/min" class="font-mono" />
        </div>
        <div class="space-y-1.5 sm:col-span-2 lg:col-span-1">
          <Label>Banner for anonymous users</Label>
          <Input v-model="policy.guest_message" placeholder="(none)" />
        </div>
      </div>
      <div>
        <Button size="sm" :disabled="loading" @click="saveDrafts">Save limits</Button>
      </div>
    </Card>

    <!-- Passcodes -->
    <Card class="p-6 space-y-4">
      <div class="flex items-center gap-2">
        <KeyRound class="size-5 text-muted-foreground" />
        <h2 class="text-lg font-semibold">Passcodes</h2>
        <Badge variant="secondary">{{ codes.length }}</Badge>
      </div>
      <p class="text-sm text-muted-foreground">
        Each code is the login credential for one persistent anonymous account —
        hand it to a friend, revoke it any time. Revoking ends their sessions
        immediately; their content stays (unlisted) unless you purge in Django admin.
      </p>

      <form class="flex items-center gap-2" @submit.prevent="onCreateCode">
        <Input v-model="newLabel" placeholder='Label, e.g. "for Max"' class="max-w-xs" />
        <Button type="submit" size="sm" :disabled="creating">
          <Loader2 v-if="creating" class="size-4 animate-spin" />
          <Plus v-else class="size-4" />
          Create code
        </Button>
      </form>

      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-left text-xs text-muted-foreground">
              <th class="py-2 pr-3 font-medium">Code</th>
              <th class="py-2 pr-3 font-medium">Label</th>
              <th class="py-2 pr-3 font-medium">Account</th>
              <th class="py-2 pr-3 font-medium">Status</th>
              <th class="py-2 pr-3 font-medium">Last used</th>
              <th class="py-2 pr-3 font-medium text-right">Logins</th>
              <th class="py-2 pr-3 font-medium text-right">Requests</th>
              <th class="py-2 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="code in codes" :key="code.id" class="border-b last:border-0">
              <td class="py-2 pr-3">
                <button
                  type="button"
                  class="inline-flex items-center gap-1.5 font-mono text-xs hover:text-primary"
                  title="Copy code"
                  @click="copyCode(code)"
                >
                  {{ code.code }}
                  <Copy class="size-3" />
                </button>
              </td>
              <td class="py-2 pr-3">{{ code.label || '—' }}</td>
              <td class="py-2 pr-3">
                <NuxtLink :to="`/${code.handle}`" class="font-mono text-xs underline underline-offset-2">
                  {{ code.handle }}
                </NuxtLink>
              </td>
              <td class="py-2 pr-3">
                <Badge :variant="code.is_active ? 'secondary' : 'destructive'">
                  {{ code.is_active ? 'active' : 'revoked' }}
                </Badge>
              </td>
              <td class="py-2 pr-3 text-xs text-muted-foreground">{{ fmtDate(code.last_used_at) }}</td>
              <td class="py-2 pr-3 text-right tabular-nums">{{ code.use_count }}</td>
              <td class="py-2 pr-3 text-right tabular-nums">{{ code.request_count }}</td>
              <td class="py-2 text-right">
                <Button variant="ghost" size="sm" @click="toggleCode(code)">
                  <ShieldOff class="size-4" />
                  {{ code.is_active ? 'Revoke' : 'Reactivate' }}
                </Button>
              </td>
            </tr>
            <tr v-if="codes.length === 0">
              <td colspan="8" class="py-6 text-center text-muted-foreground">
                No passcodes yet — create one and hand it to a friend.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>

    <!-- Guests -->
    <Card class="p-6 space-y-4">
      <div class="flex items-center gap-2">
        <VenetianMask class="size-5 text-muted-foreground" />
        <h2 class="text-lg font-semibold">Guest accounts</h2>
        <Badge variant="secondary">{{ guests.length }}</Badge>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-left text-xs text-muted-foreground">
              <th class="py-2 pr-3 font-medium">Account</th>
              <th class="py-2 pr-3 font-medium">Status</th>
              <th class="py-2 pr-3 font-medium">Joined</th>
              <th class="py-2 pr-3 font-medium">Last login</th>
              <th class="py-2 pr-3 font-medium text-right">Requests</th>
              <th class="py-2 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in guests" :key="g.id" class="border-b last:border-0">
              <td class="py-2 pr-3">
                <NuxtLink :to="`/${g.handle}`" class="font-mono text-xs underline underline-offset-2">
                  {{ g.handle }}
                </NuxtLink>
              </td>
              <td class="py-2 pr-3">
                <Badge :variant="g.is_active ? 'secondary' : 'destructive'">
                  {{ g.is_active ? 'active' : 'revoked' }}
                </Badge>
              </td>
              <td class="py-2 pr-3 text-xs text-muted-foreground">{{ fmtDate(g.date_joined) }}</td>
              <td class="py-2 pr-3 text-xs text-muted-foreground">{{ fmtDate(g.last_login) }}</td>
              <td class="py-2 pr-3 text-right tabular-nums">{{ g.request_count }}</td>
              <td class="py-2 text-right whitespace-nowrap">
                <Button v-if="g.is_active" variant="ghost" size="sm" @click="onRevokeGuest(g)">
                  <ShieldOff class="size-4" />
                  Revoke
                </Button>
                <Button variant="ghost" size="sm" class="text-destructive" @click="onPurgeGuest(g)">
                  <Trash2 class="size-4" />
                  Purge
                </Button>
              </td>
            </tr>
            <tr v-if="guests.length === 0">
              <td colspan="6" class="py-6 text-center text-muted-foreground">
                No guest accounts yet.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>
