<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Mail, Lock, MailCheck } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/composables/useAuth'

const { register, fetchAuthOptions } = useAuth()
const localePath = useLocalePath()

// Email sign-up only exists where the deployment enables it (home lab). If a
// user reaches /register on a GitHub-only deployment, say so rather than
// present a form that will 403.
const emailEnabled = ref(true)
onMounted(async () => {
  emailEnabled.value = (await fetchAuthOptions()).email
})

const email = ref('')
const password = ref('')
const confirm = ref('')
const busy = ref(false)
const errorMessage = ref('')
const done = ref(false)
const sentTo = ref('')

const onSubmit = async () => {
  errorMessage.value = ''
  if (!email.value.trim() || !password.value) return
  if (password.value !== confirm.value) {
    errorMessage.value = 'Passwords do not match.'
    return
  }
  busy.value = true
  const result = await register({ email: email.value.trim(), password: password.value })
  busy.value = false
  if (result.success) {
    done.value = true
    sentTo.value = result.email || email.value.trim()
    return
  }
  errorMessage.value = result.error || ''
}
</script>

<template>
  <Card class="overflow-hidden">
    <CardContent class="p-6 md:p-8">
      <!-- Post-submit: confirmation email sent. -->
      <div v-if="done" class="flex flex-col items-center gap-4 text-center">
        <MailCheck class="size-10 text-primary" />
        <h1 class="text-2xl font-bold">Check your email</h1>
        <p class="text-muted-foreground text-balance">
          We sent a confirmation link to
          <span class="font-medium text-foreground">{{ sentTo }}</span>.
          Open it to activate your account, then sign in.
        </p>
        <NuxtLink
          :to="localePath('/login')"
          class="text-sm underline underline-offset-4 hover:text-primary"
        >
          Back to sign in
        </NuxtLink>
      </div>

      <div v-else class="flex flex-col gap-6">
        <div class="flex flex-col items-center text-center">
          <AppLogo class="size-10 text-primary mb-2" />
          <h1 class="text-2xl font-bold">Create your account</h1>
          <p class="text-muted-foreground text-balance">Sign up with your email address.</p>
        </div>

        <p v-if="!emailEnabled" class="text-sm text-muted-foreground text-center text-balance">
          Email sign-up isn't available on this deployment.
          <NuxtLink :to="localePath('/login')" class="underline underline-offset-4 hover:text-primary">
            Sign in instead
          </NuxtLink>.
        </p>

        <form v-else class="flex flex-col gap-3" @submit.prevent="onSubmit">
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
              autocomplete="new-password"
            />
          </div>
          <div class="relative">
            <Lock class="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              v-model="confirm"
              type="password"
              placeholder="Confirm password"
              class="pl-8"
              autocomplete="new-password"
            />
          </div>
          <Button type="submit" class="w-full" :disabled="busy || !email.trim() || !password || !confirm">
            Create account
          </Button>
          <p v-if="errorMessage" class="text-xs text-destructive text-center">{{ errorMessage }}</p>
        </form>

        <p class="text-xs text-muted-foreground text-center">
          Already have an account?
          <NuxtLink :to="localePath('/login')" class="underline underline-offset-4 hover:text-primary">
            Sign in
          </NuxtLink>
        </p>
      </div>
    </CardContent>
  </Card>
</template>
