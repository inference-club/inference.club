<script setup lang="ts">
// Responsive card grid for landing / section-index pages. Usage:
//   ::doc-cards
//   :::doc-card{title="Quickstart" to="/docs/quickstart" icon="rocket"}
//   Make your first request in five minutes.
//   :::
//   ::
</script>

<template>
  <div class="not-prose my-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
    <slot />
  </div>
</template>
