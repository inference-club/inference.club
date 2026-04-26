import { defineNuxtPlugin } from '#app'
import { useAuth } from '~/composables/useAuth'

// Runs once on app init. Sets up the CSRF cookie (so any subsequent
// POST/DELETE through DRF's SessionAuthentication isn't rejected with 403)
// and rehydrates the auth store from the current session, if any.
export default defineNuxtPlugin(async () => {
  if (!import.meta.client) return
  const { setupCsrf, checkAuth } = useAuth()
  // The OAuth login flow doesn't go through any view decorated with
  // @ensure_csrf_cookie, so a freshly-logged-in user has sessionid but no
  // csrftoken until we ask for one explicitly.
  await setupCsrf()
  await checkAuth()
})