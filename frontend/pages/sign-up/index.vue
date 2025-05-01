<script setup lang="ts">
definePageMeta({
  layout: 'auth',
  title: 'Sign Up',
  description: 'Sign up for an inference.club account',
})
</script>

<template>
  <div class="bg-muted flex min-h-svh flex-col items-center justify-center p-6 md:p-10">
    <div class="w-full max-w-sm md:max-w-3xl">
      <SignUpForm />
    </div>
  </div>
</template>
