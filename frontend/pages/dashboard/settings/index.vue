<script setup lang="ts">
definePageMeta({
  layout: 'app'
})
</script>

<template>
  <div class="container mx-auto p-6">
    <h1 class="text-2xl font-bold mb-6">Settings</h1>
    <div class="grid gap-6">
      <div class="p-6 bg-card rounded-lg border">
        <h2 class="text-xl font-semibold mb-4">General</h2>
        <p class="text-muted-foreground">Configure your general settings.</p>
      </div>
      <div class="p-6 bg-card rounded-lg border">
        <h2 class="text-xl font-semibold mb-4">Team</h2>
        <p class="text-muted-foreground">Manage your team settings and members.</p>
      </div>
      <div class="p-6 bg-card rounded-lg border">
        <h2 class="text-xl font-semibold mb-4">Billing</h2>
        <p class="text-muted-foreground">View and manage your billing information.</p>
      </div>
      <div class="p-6 bg-card rounded-lg border">
        <h2 class="text-xl font-semibold mb-4">Limits</h2>
        <p class="text-muted-foreground">Configure your usage limits and quotas.</p>
      </div>
    </div>
  </div>
</template>