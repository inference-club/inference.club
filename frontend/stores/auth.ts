import { defineStore } from 'pinia'

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
  default_request_visibility: 'PUBLIC' | 'UNLISTED' | 'PRIVATE' | 'SECRET'
  default_collection_name: string
  public_profile_enabled: boolean
}

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  // True once the initial session rehydration (plugins/auth.ts → checkAuth)
  // has settled. Lets gated surfaces wait instead of flashing a sign-in gate
  // at a user who is actually logged in.
  ready: boolean
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    isAuthenticated: false,
    ready: false
  }),

  actions: {
    setUser(user: User | null) {
      this.user = user
      this.isAuthenticated = !!user
    },

    setReady() {
      this.ready = true
    },

    logout() {
      this.user = null
      this.isAuthenticated = false
    }
  }
})