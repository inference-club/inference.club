import { defineNuxtPlugin } from '#app'
import { useAuth } from '~/composables/useAuth'

export default defineNuxtPlugin(async (_nuxtApp) => {
  // Only run on client side
  if (import.meta.client) {
    const { checkAuth } = useAuth()
    console.log('Checking auth status from plugin...')
    await checkAuth()
  }
})