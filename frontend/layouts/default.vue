<template>
  <div class="min-h-screen flex flex-col">
    <TopBar />
    <main class="flex-1">
      <slot />
    </main>
    <Footer />
    <!-- Music playback works on public pages (profiles, shared links) too. -->
    <div v-if="player.hasQueue" class="h-20 shrink-0" />
    <GlobalPlayerBar />
  </div>
</template>

<script setup lang="ts">
import TopBar from '@/components/TopBar.vue'
import Footer from '@/components/Footer.vue'
import { usePlayerStore } from '@/stores/player'

const player = usePlayerStore()
</script>
