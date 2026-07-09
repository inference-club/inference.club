<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { onMounted, ref } from 'vue'
import { VenetianMask, KeyRound, ArrowRight, Mail, Lock } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useAuth, type AuthOptions } from '@/composables/useAuth'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()

const { t } = useI18n()
const localePath = useLocalePath()
const config = useRuntimeConfig()
const { fetchAuthOptions, guestLogin, passcodeLogin, login, resendConfirmation } = useAuth()

const githubLogin = () => {
  window.location.href = `${config.public.apiBase}/oauth/login/github/`
}

// Which pathways the admin has live right now; defaults render GitHub-only
// until the options load (no layout jump for the common case).
const options = ref<AuthOptions>({ github: true, email: false, guest: false, passcode: false, guest_message: '' })
onMounted(async () => {
  options.value = await fetchAuthOptions()
})

const busy = ref(false)
const errorMessage = ref('')
const infoMessage = ref('')
const passcode = ref('')

// Email + password sign-in (home-lab auth path).
const email = ref('')
const password = ref('')
const needsConfirm = ref(false)

const onEmailLogin = async () => {
  if (!email.value.trim() || !password.value) return
  busy.value = true
  errorMessage.value = ''
  infoMessage.value = ''
  needsConfirm.value = false
  const result = await login({ email: email.value.trim(), password: password.value })
  busy.value = false
  if (result.success) return navigateTo(localePath('/dashboard'))
  if (result.code === 'email_unconfirmed') needsConfirm.value = true
  errorMessage.value = result.error || ''
}

const onResend = async () => {
  busy.value = true
  const result = await resendConfirmation(email.value.trim())
  busy.value = false
  needsConfirm.value = false
  errorMessage.value = ''
  infoMessage.value = result.success ? result.detail || '' : result.error || ''
}

const onGuest = async () => {
  busy.value = true
  errorMessage.value = ''
  const result = await guestLogin()
  busy.value = false
  if (result.success) return navigateTo(localePath('/dashboard'))
  errorMessage.value = result.error
}

const onPasscode = async () => {
  if (!passcode.value.trim()) return
  busy.value = true
  errorMessage.value = ''
  const result = await passcodeLogin(passcode.value.trim())
  busy.value = false
  if (result.success) return navigateTo(localePath('/dashboard'))
  errorMessage.value = result.error
}
</script>

<template>
  <div :class="cn('flex flex-col gap-6', props.class)">
    <Card class="overflow-hidden p-0">
      <CardContent class="grid p-0 md:grid-cols-2">
        <div class="p-6 md:p-8 md:min-h-[26rem] flex items-center">
          <div class="flex flex-col gap-6 w-full">
            <div class="flex flex-col items-center text-center">
              <AppLogo class="size-10 text-primary mb-2" />
              <h1 class="text-2xl font-bold">
                {{ t('auth.welcomeTitle') }}
              </h1>
              <p class="text-muted-foreground text-balance">
                {{ t('auth.welcomeSubtitle') }}
              </p>
            </div>
            <Button v-if="options.github" type="button" class="w-full" :disabled="busy" @click="githubLogin">
              <svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" fill="currentColor" class="bi bi-github" viewBox="0 0 16 16">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8"/>
              </svg>
              {{ t('auth.continueWithGithub') }}
            </Button>

            <!-- Email + password sign-in (home-lab auth path). -->
            <template v-if="options.email">
              <div v-if="options.github" class="flex items-center gap-3 text-xs text-muted-foreground">
                <div class="h-px flex-1 bg-border" />
                {{ t('auth.or') }}
                <div class="h-px flex-1 bg-border" />
              </div>

              <form class="flex flex-col gap-3" @submit.prevent="onEmailLogin">
                <div class="relative">
                  <Mail class="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    v-model="email"
                    type="email"
                    placeholder="you@example.com"
                    class="pl-8"
                    autocomplete="email"
                  />
                </div>
                <div class="relative">
                  <Lock class="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    v-model="password"
                    type="password"
                    placeholder="Password"
                    class="pl-8"
                    autocomplete="current-password"
                  />
                </div>
                <Button type="submit" class="w-full" :disabled="busy || !email.trim() || !password">
                  Sign in
                </Button>
              </form>

              <p class="text-xs text-muted-foreground text-center">
                New here?
                <NuxtLink :to="localePath('/register')" class="underline underline-offset-4 hover:text-primary">
                  Create an account
                </NuxtLink>
              </p>

              <div v-if="needsConfirm" class="text-center">
                <Button type="button" variant="outline" size="sm" :disabled="busy" @click="onResend">
                  Resend confirmation email
                </Button>
              </div>
              <p v-if="infoMessage" class="text-xs text-muted-foreground text-center">
                {{ infoMessage }}
              </p>
              <p v-if="errorMessage" class="text-xs text-destructive text-center">
                {{ errorMessage }}
              </p>
            </template>

            <template v-if="options.guest || options.passcode">
              <div class="flex items-center gap-3 text-xs text-muted-foreground">
                <div class="h-px flex-1 bg-border" />
                {{ t('auth.or') }}
                <div class="h-px flex-1 bg-border" />
              </div>

              <Button
                v-if="options.guest"
                type="button"
                variant="outline"
                class="w-full"
                :disabled="busy"
                @click="onGuest"
              >
                <VenetianMask class="size-4" />
                {{ t('auth.tryAnonymously') }}
              </Button>

              <form v-if="options.passcode" class="flex items-center gap-2" @submit.prevent="onPasscode">
                <div class="relative flex-1">
                  <KeyRound class="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    v-model="passcode"
                    :placeholder="t('auth.passcodePlaceholder')"
                    class="pl-8 font-mono"
                    autocomplete="off"
                    spellcheck="false"
                  />
                </div>
                <Button type="submit" variant="outline" size="icon" :disabled="busy || !passcode.trim()" :aria-label="t('auth.passcodeSubmit')">
                  <ArrowRight class="size-4" />
                </Button>
              </form>

              <p class="text-xs text-muted-foreground text-center text-balance">
                {{ t('auth.anonymousHint') }}
              </p>

              <p v-if="errorMessage" class="text-xs text-destructive text-center">
                {{ errorMessage }}
              </p>
            </template>
          </div>
        </div>
        <div class="bg-muted relative hidden md:block">
          <img
            src="/images/inference-club.png"
            alt="Image"
            class="absolute inset-0 h-full w-full object-cover"
          >
        </div>
      </CardContent>
    </Card>
    <i18n-t
      keypath="auth.termsAgreement"
      tag="div"
      scope="global"
      class="text-muted-foreground *:[a]:hover:text-primary text-center text-xs text-balance *:[a]:underline *:[a]:underline-offset-4"
    >
      <template #terms>
        <NuxtLink :to="localePath('/terms-of-service')">{{ t('auth.termsLink') }}</NuxtLink>
      </template>
      <template #privacy>
        <NuxtLink :to="localePath('/privacy-policy')">{{ t('auth.privacyLink') }}</NuxtLink>
      </template>
    </i18n-t>
  </div>
</template>
