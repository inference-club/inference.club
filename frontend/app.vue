<template>
  <div :class="{ dark: isDark }">
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useTheme } from '@/composables/useTheme'
import { useAuth } from '@/composables/useAuth'

const { isDark } = useTheme()
const { checkAuth } = useAuth()

// Check authentication status when app loads
onMounted(async () => {
  console.log('Checking auth status...')
  await checkAuth()
})
</script>