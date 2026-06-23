<script setup lang="ts">
// Inviting in-page gate shown to LOGGED-OUT visitors on member-only tool pages
// (playground, workflows, queue, chats, settings, …). Rather than a broken
// shell or a hard redirect, we name the feature and offer the sign-in funnel —
// discoverability is the whole point of opening the dashboard to guests.
//
// Distinct from MemberOnlyGate.vue, which is the guest→full-member *upgrade*
// gate (different audience, different copy).
import { Lock, Github } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { NuxtLink } from '#components'

defineProps<{
  title: string
  description: string
}>()

const config = useRuntimeConfig()
const signIn = () => {
  window.location.href = `${config.public.apiBase}/oauth/login/github/`
}
</script>

<template>
  <Card class="mx-auto mt-4 flex max-w-md flex-col items-center gap-3 p-8 text-center">
    <div class="flex size-10 items-center justify-center rounded-full bg-muted">
      <Lock class="size-5 text-muted-foreground" />
    </div>
    <div class="space-y-1">
      <h2 class="font-semibold">{{ title }}</h2>
      <p class="max-w-md text-balance text-sm text-muted-foreground">
        {{ description }}
      </p>
    </div>
    <Button size="sm" class="mt-1" @click="signIn">
      <Github class="size-4" />
      {{ $t('gate.continueGithub') }}
    </Button>
    <p class="text-xs text-muted-foreground">
      {{ $t('gate.guestHintPrefix') }}
      <NuxtLink to="/login" class="underline hover:text-foreground">
        {{ $t('gate.guestHintLink') }}</NuxtLink>{{ $t('gate.guestHintSuffix') }}
    </p>
  </Card>
</template>
