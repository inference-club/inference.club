<script setup lang="ts">
definePageMeta({
  layout: 'default'
})
</script>

<template>
  <div class="container mx-auto p-6">
    <h1 class="text-2xl font-bold mb-6">Models</h1>
    <div class="grid gap-6">
      <div class="p-6 bg-card rounded-lg border">
        <h2 class="text-xl font-semibold mb-4">Genesis</h2>
        <p class="text-muted-foreground">Explore the Genesis model collection.</p>
      </div>
      <div class="p-6 bg-card rounded-lg border">
        <h2 class="text-xl font-semibold mb-4">Explorer</h2>
        <p class="text-muted-foreground">Discover and experiment with different models.</p>
      </div>
      <div class="p-6 bg-card rounded-lg border">
        <h2 class="text-xl font-semibold mb-4">Quantum</h2>
        <p class="text-muted-foreground">Advanced quantum computing models.</p>
      </div>
    </div>
  </div>
</template>