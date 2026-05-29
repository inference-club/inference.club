<script setup lang="ts">
import { Github } from 'lucide-vue-next'

// Computed once at render; stable across SSR/hydration within a render window.
const year = new Date().getFullYear()
</script>

<template>
  <footer class="mt-auto border-t px-4 py-6 text-sm text-muted-foreground">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex items-center gap-2">
        <NuxtLink to="/" class="font-semibold text-foreground hover:text-primary transition-colors">
          inference.club
        </NuxtLink>
        <span class="text-xs">&copy; {{ year }}</span>
      </div>

      <nav class="flex flex-wrap items-center gap-x-4 gap-y-2">
        <NuxtLink to="/" class="hover:text-primary transition-colors">Home</NuxtLink>
        <NuxtLink to="/models" class="hover:text-primary transition-colors">Models</NuxtLink>
        <NuxtLink to="/docs" class="hover:text-primary transition-colors">Docs</NuxtLink>
        <NuxtLink to="/blog" class="hover:text-primary transition-colors">Blog</NuxtLink>
        <NuxtLink to="/terms-of-service" class="hover:text-primary transition-colors">Terms</NuxtLink>
        <NuxtLink to="/privacy-policy" class="hover:text-primary transition-colors">Privacy</NuxtLink>
        <a
          href="https://github.com/inference-club"
          target="_blank"
          rel="noopener noreferrer"
          class="inline-flex items-center gap-1 hover:text-primary transition-colors"
        >
          <Github class="size-3.5" /> GitHub
        </a>
      </nav>
    </div>
  </footer>
</template>
