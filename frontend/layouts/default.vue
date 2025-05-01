<template>
  <div class="min-h-screen flex flex-col">
    <TopBar />
    <main class="flex-1">
      <slot />
    </main>
    <Footer />
  </div>
</template>

<script setup lang="ts">
import TopBar from '@/components/TopBar.vue'
import Footer from '@/components/Footer.vue'
</script>