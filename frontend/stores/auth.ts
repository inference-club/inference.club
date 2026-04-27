import { defineStore } from 'pinia'

interface User {
  email: string
  is_staff: boolean
  is_active: boolean
  is_superuser: boolean
  profile_setup_complete: boolean
  github_login: string | null
}

interface AuthState {
  user: User | null
  isAuthenticated: boolean
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    isAuthenticated: false
  }),

  actions: {
    setUser(user: User | null) {
      this.user = user
      this.isAuthenticated = !!user
    },

    logout() {
      this.user = null
      this.isAuthenticated = false
    }
  }
})