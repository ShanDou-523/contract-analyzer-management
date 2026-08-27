import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { bootstrapAdmin, getCurrentUser, login, logout } from '../api'
import type { AuthUser } from '../types'

const ACCESS_TOKEN_KEY = 'contract_analyzer_access_token'
const REFRESH_TOKEN_KEY = 'contract_analyzer_refresh_token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(ACCESS_TOKEN_KEY) || '')
  const refreshToken = ref(localStorage.getItem(REFRESH_TOKEN_KEY) || '')
  const user = ref<AuthUser | null>(null)
  const initialized = ref(false)
  const isAuthenticated = computed(() => Boolean(token.value))

  function saveSession(access: string, refresh: string, nextUser: AuthUser) {
    token.value = access
    refreshToken.value = refresh
    user.value = nextUser
    localStorage.setItem(ACCESS_TOKEN_KEY, access)
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh)
  }

  async function signIn(username: string, password: string) {
    const result = await login(username, password)
    saveSession(result.access_token, result.refresh_token, result.user)
  }

  async function bootstrap(payload: Parameters<typeof bootstrapAdmin>[0]) {
    const result = await bootstrapAdmin(payload)
    saveSession(result.access_token, result.refresh_token, result.user)
  }

  async function restore() {
    if (!token.value) {
      initialized.value = true
      return
    }
    try {
      user.value = await getCurrentUser()
    } catch {
      clearSession()
    } finally {
      initialized.value = true
    }
  }

  async function signOut() {
    try {
      if (refreshToken.value) await logout(refreshToken.value)
    } finally {
      clearSession()
    }
  }

  function clearSession() {
    token.value = ''
    refreshToken.value = ''
    user.value = null
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  }

  window.addEventListener('contract-analyzer-auth-expired', clearSession)

  return {
    token,
    refreshToken,
    user,
    initialized,
    isAuthenticated,
    signIn,
    bootstrap,
    restore,
    signOut,
    clearSession,
  }
})
