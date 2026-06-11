<script setup lang="ts">
// The one page-header pattern for dashboard pages: 2xl semibold title,
// muted one-line description, actions on the right (wraps on mobile).
defineProps<{ title: string; description?: string }>()
</script>

<template>
  <div class="flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
    <div class="min-w-0">
      <h1 class="text-2xl font-semibold tracking-tight">{{ title }}</h1>
      <p v-if="description" class="mt-1 text-sm text-muted-foreground">{{ description }}</p>
    </div>
    <div v-if="$slots.default" class="flex flex-wrap items-center gap-2">
      <slot />
    </div>
  </div>
</template>
