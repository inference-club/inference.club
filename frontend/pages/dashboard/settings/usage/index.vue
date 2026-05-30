<script setup lang="ts">
import { Gauge } from 'lucide-vue-next'

definePageMeta({
  layout: 'app',
})
</script>

<template>
  <div class="container mx-auto py-6 max-w-3xl">
    <div class="mb-6">
      <h1 class="text-2xl font-bold flex items-center gap-2">
        <Gauge class="h-6 w-6" />
        Usage
      </h1>
      <p class="text-sm text-muted-foreground mt-1">
        Your current rate-limit headroom. Limits are per-user and reset on a
        rolling window; you'll get an HTTP 429 with a <code>Retry-After</code>
        if you exceed them.
      </p>
    </div>

    <RateLimitMeter />
  </div>
</template>
