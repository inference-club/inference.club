<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()

const config = useRuntimeConfig()

const githubLogin = () => {
  window.location.href = `${config.public.apiBase}/oauth/login/github/`
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
                Welcome to inference.club
              </h1>
              <p class="text-muted-foreground text-balance">
                Sign in with GitHub to continue.
              </p>
            </div>
            <Button type="button" class="w-full" @click="githubLogin">
              <svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" fill="currentColor" class="bi bi-github" viewBox="0 0 16 16">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8"/>
              </svg>
              Continue with GitHub
            </Button>
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
    <div class="text-muted-foreground *:[a]:hover:text-primary text-center text-xs text-balance *:[a]:underline *:[a]:underline-offset-4">
      By continuing, you agree to our <a href="/terms-of-service">Terms of Service</a>
      and <a href="/privacy-policy">Privacy Policy</a>.
    </div>
  </div>
</template>
