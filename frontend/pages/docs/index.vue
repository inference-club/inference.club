<script setup lang="ts">
definePageMeta({
  layout: 'app'
})
</script>

<template>
  <div class="container mx-auto p-6">
    <h1 class="text-2xl font-bold mb-6">Documentation</h1>
    <div class="grid gap-6">
      <div class="p-6 bg-card rounded-lg border">
        <h2 class="text-xl font-semibold mb-4">Introduction</h2>
        <p class="text-muted-foreground">Welcome to the inference.club documentation.</p>
      </div>
      <div class="p-6 bg-card rounded-lg border">
        <h2 class="text-xl font-semibold mb-4">Get Started</h2>
        <p class="text-muted-foreground">Learn how to get started with inference.club.</p>
      </div>
      <div class="p-6 bg-card rounded-lg border">
        <h2 class="text-xl font-semibold mb-4">Tutorials</h2>
        <p class="text-muted-foreground">Step-by-step guides and tutorials.</p>
      </div>
      <div class="p-6 bg-card rounded-lg border">
        <h2 class="text-xl font-semibold mb-4">Changelog</h2>
        <p class="text-muted-foreground">Recent updates and changes to the platform.</p>
      </div>
    </div>
  </div>
</template>