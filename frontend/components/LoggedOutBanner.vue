<script setup lang="ts">
// Slim, dismissible welcome banner for LOGGED-OUT visitors browsing the open
// showcase surfaces (music, watch, gallery, leaderboard, models, cluster…).
// Subtle by design — it explains what they're looking at and offers the sign-in
// funnel without nagging. Mirrors AnonymousBanner.vue's dismiss/localStorage
// pattern. Renders nothing for signed-in users.
import { onMounted, ref } from 'vue'
import { Sparkles, X, Github } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { NuxtLink } from '#components'
import { useAuth } from '@/composables/useAuth'

const { isAuthenticated } = useAuth()
const config = useRuntimeConfig()

const DISMISS_KEY = 'logged-out-banner-dismissed'
const dismissed = ref(true)

onMounted(() => {
  dismissed.value = !!localStorage.getItem(DISMISS_KEY)
})

const dismiss = () => {
  localStorage.setItem(DISMISS_KEY, '1')
  dismissed.value = true
}

const signIn = () => {
  window.location.href = `${config.public.apiBase}/oauth/login/github/`
}
</script>

<template>
  <div
    v-if="!isAuthenticated && !dismissed"
    class="relative rounded-lg border bg-muted/40 p-4 pr-10 text-sm"
  >
    <button
      type="button"
      class="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
      :aria-label="$t('loggedOutBanner.dismiss')"
      @click="dismiss"
    >
      <X class="size-4" />
    </button>
    <div class="flex items-start gap-3">
      <Sparkles class="mt-0.5 size-5 shrink-0 text-muted-foreground" />
      <div class="min-w-0 space-y-2">
        <p>{{ $t('loggedOutBanner.body') }}</p>
        <div class="flex flex-wrap items-center gap-2">
          <Button size="sm" @click="signIn">
            <Github class="size-4" />
            {{ $t('gate.continueGithub') }}
          </Button>
          <NuxtLink to="/login" class="text-xs text-muted-foreground underline hover:text-foreground">
            {{ $t('loggedOutBanner.otherOptions') }}
          </NuxtLink>
        </div>
      </div>
    </div>
  </div>
</template>
