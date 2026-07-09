<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Loader2, CircleCheck, CircleX } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useAuth } from '@/composables/useAuth'

definePageMeta({
  layout: 'auth',
  title: 'Confirm email',
  description: 'Confirm your inference.club email address',
})

const route = useRoute()
const localePath = useLocalePath()
const { confirmEmail } = useAuth()

const state = ref<'loading' | 'success' | 'error'>('loading')
const message = ref('')

onMounted(async () => {
  const token = String(route.query.token || '')
  if (!token) {
    state.value = 'error'
    message.value = 'No confirmation token was provided.'
    return
  }
  const result = await confirmEmail(token)
  if (result.success) {
    state.value = 'success'
    message.value = result.detail || 'Email confirmed. You can now sign in.'
  } else {
    state.value = 'error'
    message.value = result.error || ''
  }
})
</script>

<template>
  <div class="bg-muted flex min-h-svh flex-col items-center justify-center p-6 md:p-10">
    <div class="w-full max-w-sm">
      <Card>
        <CardContent class="flex flex-col items-center gap-4 p-8 text-center">
          <template v-if="state === 'loading'">
            <Loader2 class="size-10 animate-spin text-muted-foreground" />
            <p class="text-muted-foreground">Confirming your email…</p>
          </template>
          <template v-else-if="state === 'success'">
            <CircleCheck class="size-10 text-primary" />
            <h1 class="text-xl font-bold">You're all set</h1>
            <p class="text-muted-foreground text-balance">{{ message }}</p>
            <Button as-child class="w-full">
              <NuxtLink :to="localePath('/login')">Sign in</NuxtLink>
            </Button>
          </template>
          <template v-else>
            <CircleX class="size-10 text-destructive" />
            <h1 class="text-xl font-bold">Confirmation failed</h1>
            <p class="text-muted-foreground text-balance">{{ message }}</p>
            <Button as-child variant="outline" class="w-full">
              <NuxtLink :to="localePath('/login')">Back to sign in</NuxtLink>
            </Button>
          </template>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
