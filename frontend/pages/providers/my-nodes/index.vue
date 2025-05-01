<script setup lang="ts">
definePageMeta({
  layout: 'app'
})
</script>

<template>
  <div class="container mx-auto p-6">
    <h1 class="text-2xl font-bold mb-6">Inference Providers</h1>
    <div class="grid gap-6">
      <div class="p-6 bg-card rounded-lg border">
        <h2 class="text-xl font-semibold mb-4">My Nodes</h2>
        <p class="text-muted-foreground">Manage your inference nodes here.</p>
      </div>
      <div class="p-6 bg-card rounded-lg border">
        <h2 class="text-xl font-semibold mb-4">All Nodes</h2>
        <p class="text-muted-foreground">Browse all available inference nodes.</p>
      </div>
    </div>
  </div>
</template>