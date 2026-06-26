import { useAuthStore } from '~/stores/auth'

interface User {
  email: string
  is_staff: boolean
  is_active: boolean
  is_superuser: boolean
  profile_setup_complete: boolean
  github_login: string | null
  api_token: string | null
  handle: string | null
  account_type: 'GITHUB' | 'GUEST' | 'PASSCODE'
  is_anonymous_account: boolean
  anon_alias: string | null
  use_anon_alias: boolean
  alias_regenerated_at: string | null
  routing_preference: 'ANY' | 'PREFER_OWN' | 'ONLY_OWN'
  fallback_model: string
  default_request_visibility: 'PUBLIC' | 'UNLISTED' | 'PRIVATE' | 'SECRET'
  default_collection_name: string
  public_profile_enabled: boolean
}

export interface AuthOptions {
  github: boolean
  guest: boolean
  passcode: boolean
  guest_message: string
}

interface LoginCredentials {
  email: string
  password: string
}

interface RegisterCredentials extends LoginCredentials {
  name?: string
}

interface AuthResponse {
  user: User
}

export const useAuth = () => {
  const config = useRuntimeConfig()
  const authStore = useAuthStore()
  const router = useRouter()

  const checkAuth = async () => {
    try {
      const { data, error } = await useFetch<User>(`${config.public.apiBase}/api/account/`, {
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
        }
      })

      if (error.value) {
        console.error('Auth check failed:', error.value)
        authStore.setUser(null)
        return false
      }

      if (data.value) {
        console.log('User authenticated:', data.value)
        authStore.setUser(data.value)
        return true
      }

      console.log('No user data received')
      authStore.setUser(null)
      return false
    } catch (err) {
      console.error('Auth check error:', err)
      authStore.setUser(null)
      return false
    } finally {
      // The initial session check has resolved (one way or the other) — gated
      // surfaces can now safely decide whether to show their sign-in gate.
      authStore.setReady()
    }
  }

  const setupCsrf = async () => {
    try {
      const { error } = await useFetch(`${config.public.apiBase}/api/login-set-cookie/`, {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
        }
      })

      if (error.value) {
        throw error.value
      }

      return true
    } catch (error) {
      console.error('Failed to setup CSRF token:', error)
      return false
    }
  }

  const getCsrfToken = () => {
    // Get the CSRF token from the cookie
    const name = 'csrftoken'
    let cookieValue = null
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';')
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim()
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1))
          break
        }
      }
    }
    return cookieValue
  }

  const login = async (credentials: LoginCredentials) => {
    try {
      // First setup CSRF token
      const csrfSetup = await setupCsrf()
      if (!csrfSetup) {
        return { success: false, error: 'Failed to setup CSRF token' }
      }

      const csrfToken = getCsrfToken()
      if (!csrfToken) {
        return { success: false, error: 'CSRF token not found' }
      }

      const { data, error } = await useFetch<AuthResponse>(`${config.public.apiBase}/api/login/`, {
        method: 'POST',
        body: credentials,
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        }
      })

      if (error.value) {
        throw error.value
      }

      if (data.value) {
        // After successful login, fetch the user account details
        const { data: accountData, error: accountError } = await useFetch<User>(`${config.public.apiBase}/api/account/`, {
          credentials: 'include'
        })

        if (accountError.value) {
          throw accountError.value
        }

        if (accountData.value) {
          authStore.setUser(accountData.value)
          router.push('/')
          return { success: true }
        }
      }
    } catch (error) {
      return { success: false, error }
    }
  }

  const register = async (credentials: RegisterCredentials) => {
    try {
      // First setup CSRF token
      const csrfSetup = await setupCsrf()
      if (!csrfSetup) {
        return { success: false, error: 'Failed to setup CSRF token' }
      }

      const csrfToken = getCsrfToken()
      if (!csrfToken) {
        return { success: false, error: 'CSRF token not found' }
      }

      const { data, error } = await useFetch<AuthResponse>(`${config.public.apiBase}/api/register/`, {
        method: 'POST',
        body: credentials,
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        }
      })

      if (error.value) {
        throw error.value
      }

      if (data.value) {
        const { user } = data.value
        authStore.setUser(user)
        router.push('/')
        return { success: true }
      }
    } catch (error) {
      return { success: false, error }
    }
  }

  const logout = async () => {
    try {
      const csrfToken = getCsrfToken()
      if (!csrfToken) {
        return { success: false, error: 'CSRF token not found' }
      }

      await useFetch(`${config.public.apiBase}/api/logout/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        }
      })
      authStore.logout()
      router.push('/')
      return { success: true }
    } catch (error) {
      return { success: false, error }
    }
  }

  // Which sign-in pathways are live right now (admin-configurable; drives
  // the login page so enabling guests/passcodes needs no deploy).
  const fetchAuthOptions = async (): Promise<AuthOptions> => {
    try {
      return await $fetch<AuthOptions>(`${config.public.apiBase}/api/auth/options/`)
    } catch {
      return { github: true, guest: false, passcode: false, guest_message: '' }
    }
  }

  // One-click anonymous account. On success the session cookie is set and the
  // store holds the new guest user.
  const guestLogin = async () => {
    try {
      await setupCsrf()
      const csrfToken = getCsrfToken()
      const data = await $fetch<User>(`${config.public.apiBase}/api/auth/guest/`, {
        method: 'POST',
        credentials: 'include',
        headers: csrfToken ? { 'X-CSRFToken': csrfToken } : {},
      })
      authStore.setUser(data)
      return { success: true as const }
    } catch (error: any) {
      const detail = error?.data?.detail || 'Guest sign-in failed'
      return { success: false as const, error: detail }
    }
  }

  // Passcode login: the code is the credential for one persistent account.
  const passcodeLogin = async (code: string) => {
    try {
      await setupCsrf()
      const csrfToken = getCsrfToken()
      const data = await $fetch<User>(`${config.public.apiBase}/api/auth/passcode/`, {
        method: 'POST',
        credentials: 'include',
        headers: csrfToken ? { 'X-CSRFToken': csrfToken } : {},
        body: { code },
      })
      authStore.setUser(data)
      return { success: true as const }
    } catch (error: any) {
      const detail = error?.data?.detail || 'Invalid or revoked passcode.'
      return { success: false as const, error: detail }
    }
  }

  // Fresh anonymous alias (rate-limited server-side to once / 30 days).
  const regenerateAlias = async () => {
    const csrfToken = getCsrfToken()
    const data = await $fetch<User>(
      `${config.public.apiBase}/api/account/alias/regenerate/`,
      {
        method: 'POST',
        credentials: 'include',
        headers: csrfToken ? { 'X-CSRFToken': csrfToken } : {},
      },
    )
    authStore.setUser(data)
    return data
  }

  const updateAccount = async (
    payload: Partial<
      Pick<
        User,
        | 'routing_preference'
        | 'fallback_model'
        | 'default_request_visibility'
        | 'default_collection_name'
        | 'public_profile_enabled'
        | 'use_anon_alias'
      >
    >,
  ) => {
    const csrfToken = getCsrfToken()
    const data = await $fetch<User>(`${config.public.apiBase}/api/account/`, {
      method: 'PATCH',
      credentials: 'include',
      headers: csrfToken ? { 'X-CSRFToken': csrfToken } : {},
      body: payload,
    })
    authStore.setUser(data)
    return data
  }

  return {
    login,
    register,
    logout,
    checkAuth,
    setupCsrf,
    updateAccount,
    fetchAuthOptions,
    guestLogin,
    passcodeLogin,
    regenerateAlias,
    user: computed(() => authStore.user),
    isAuthenticated: computed(() => authStore.isAuthenticated),
    isAnonymous: computed(() => !!authStore.user?.is_anonymous_account),
    // Has the initial session check resolved yet? (see store + plugins/auth.ts)
    ready: computed(() => authStore.ready)
  }
}