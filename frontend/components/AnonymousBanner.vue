<script setup lang="ts">
// One-time (dismissible, per-account) welcome banner for guest/passcode
// sessions: says who you are, what's stored, and how to keep the account.
// The persistent affordance is the "Anon" chip in NavUser — this banner is
// the only other messaging, deliberately (informative, not nagging).
import { computed, onMounted, ref } from 'vue'
import { VenetianMask, X, Github } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useAuth, type AuthOptions } from '@/composables/useAuth'

const { user, isAnonymous, fetchAuthOptions } = useAuth()
const config = useRuntimeConfig()

const dismissKey = computed(() => `anon-banner-dismissed:${user.value?.handle ?? ''}`)
const dismissed = ref(true)
const guestMessage = ref('')

onMounted(async () => {
  if (!isAnonymous.value) return
  dismissed.value = !!localStorage.getItem(dismissKey.value)
  if (!dismissed.value) {
    const options: AuthOptions = await fetchAuthOptions()
    guestMessage.value = options.guest_message
  }
})

const dismiss = () => {
  localStorage.setItem(dismissKey.value, '1')
  dismissed.value = true
}

const keepAccount = () => {
  window.location.href = `${config.public.apiBase}/oauth/login/github/`
}

const isGuest = computed(() => user.value?.account_type === 'GUEST')
</script>

<template>
  <div
    v-if="isAnonymous && !dismissed"
    class="relative rounded-lg border bg-muted/40 p-4 pr-10 text-sm"
  >
    <button
      type="button"
      class="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
      aria-label="Dismiss"
      @click="dismiss"
    >
      <X class="size-4" />
    </button>
    <div class="flex items-start gap-3">
      <VenetianMask class="mt-0.5 size-5 shrink-0 text-muted-foreground" />
      <div class="space-y-2 min-w-0">
        <p>
          You're anonymous as
          <span class="font-mono font-medium">{{ user?.handle }}</span>.
          Your generations are saved under this random name — no email, nothing
          that identifies you — and stay unlisted (never public).
        </p>
        <p class="text-muted-foreground">
          <template v-if="isGuest">
            This account lives in this browser: log out or clear cookies and
            it's gone.
          </template>
          <template v-else>
            Your passcode is the key to this account — re-enter it to sign in
            from anywhere.
          </template>
          Want to keep everything under a real account?
        </p>
        <p v-if="guestMessage" class="text-muted-foreground italic">
          {{ guestMessage }}
        </p>
        <Button variant="outline" size="sm" @click="keepAccount">
          <Github class="size-4" />
          Keep this account — sign in with GitHub
        </Button>
      </div>
    </div>
  </div>
</template>
