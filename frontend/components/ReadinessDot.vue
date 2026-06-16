<script setup lang="ts">
// Small liveness indicator: a pulsing green dot when a service/model is
// reachable and ready, a static gray dot when it isn't. Reusable across the
// playground model pickers, the catalog, and provider listings.
withDefaults(
  defineProps<{
    online?: boolean
    label?: string
    /** Tailwind size class for the dot, e.g. 'size-2' (default) or 'size-2.5'. */
    size?: string
  }>(),
  { online: true, label: '', size: 'size-2' },
)
</script>

<template>
  <span class="inline-flex items-center gap-1.5">
    <span class="relative flex" :class="size" aria-hidden="true">
      <span
        v-if="online"
        class="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-500 opacity-75"
      />
      <span
        class="relative inline-flex rounded-full"
        :class="[size, online ? 'bg-green-500' : 'bg-muted-foreground/40']"
      />
    </span>
    <span
      v-if="label"
      class="text-2xs font-medium uppercase tracking-wide"
      :class="online ? 'text-green-600 dark:text-green-500' : 'text-muted-foreground'"
    >{{ label }}</span>
  </span>
</template>
