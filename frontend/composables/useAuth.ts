import { useAuthStore } from '~/stores/auth'

interface User {
  email: string
  is_staff: boolean
  is_active: boolean
  is_superuser: boolean
  profile_setup_complete: boolean
  github_login: string | null
  api_token: string
  routing_preference: 'ANY' | 'PREFER_OWN' | 'ONLY_OWN'
  default_request_visibility: 'PUBLIC' | 'UNLISTED' | 'PRIVATE' | 'SECRET'
  default_collection_name: string
  public_profile_enabled: boolean
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

  const updateAccount = async (
    payload: Partial<
      Pick<
        User,
        | 'routing_preference'
        | 'default_request_visibility'
        | 'default_collection_name'
        | 'public_profile_enabled'
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
    user: computed(() => authStore.user),
    isAuthenticated: computed(() => authStore.isAuthenticated)
  }
}