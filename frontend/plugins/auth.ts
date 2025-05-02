import { defineNuxtPlugin } from '#app'
import { useAuth } from '~/composables/useAuth'

export default defineNuxtPlugin(async () => {
  const { checkAuth } = useAuth()
  await checkAuth()
})