import { useAuth } from '@/composables/useAuth'

// Guards staff-only dashboard pages. The auth store is rehydrated client-side by
// plugins/auth.ts (which awaits checkAuth before route middleware runs), so we
// only enforce on the client and let the server render pass through. The API is
// the real gate — this just keeps non-staff out of the admin UI.
export default defineNuxtRouteMiddleware((to) => {
  if (import.meta.server) return

  const { user } = useAuth()
  if (!user.value?.is_staff) {
    return navigateTo(useLocalePath()('/dashboard'))
  }
})
