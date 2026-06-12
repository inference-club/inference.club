<script setup lang="ts">
// Quiet locked state for features guest/passcode accounts can't use (API
// tokens, compute registration). Rendered instead of hiding the page —
// discoverability beats mystery, and the CTA doubles as the upgrade funnel.
import { Lock, Github } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

defineProps<{
  title: string
  description: string
}>()

const config = useRuntimeConfig()
const keepAccount = () => {
  window.location.href = `${config.public.apiBase}/oauth/login/github/`
}
</script>

<template>
  <Card class="p-8 flex flex-col items-center text-center gap-3">
    <div class="flex size-10 items-center justify-center rounded-full bg-muted">
      <Lock class="size-5 text-muted-foreground" />
    </div>
    <div class="space-y-1">
      <h2 class="font-semibold">{{ title }}</h2>
      <p class="text-sm text-muted-foreground max-w-md text-balance">
        {{ description }}
      </p>
    </div>
    <Button variant="outline" size="sm" class="mt-1" @click="keepAccount">
      <Github class="size-4" />
      Keep this account — sign in with GitHub
    </Button>
    <p class="text-xs text-muted-foreground">
      Your handle and everything you've generated come with you.
    </p>
  </Card>
</template>
