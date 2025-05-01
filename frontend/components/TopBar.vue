<template>
  <header class="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
    <div class="flex h-14 items-center px-4 sm:px-6 lg:px-8">
      <div class="mr-4 flex">
        <NuxtLink to="/" class="mr-6 flex items-center space-x-2">
          <span class="font-bold text-xl">inference.club</span>
        </NuxtLink>
      </div>
      <div class="flex flex-1 items-center justify-end space-x-2">
        <Button variant="ghost" size="sm" @click="toggleTheme">
          <Sun v-if="isDark" class="h-5 w-5" />
          <Moon v-else class="h-5 w-5" />
          <span class="sr-only">Toggle theme</span>
        </Button>
        <Button variant="ghost" size="sm">
          <NuxtLink to="/login">Login</NuxtLink>
        </Button>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { Sun, Moon } from 'lucide-vue-next'
import { useTheme } from '@/composables/useTheme'

const { isDark, toggleTheme } = useTheme()
</script>