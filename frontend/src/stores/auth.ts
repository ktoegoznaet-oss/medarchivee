import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  authApi,
  type LoginPayload,
  type RegisterPayload,
  type UserPublic,
  type VerifyEmailPayload,
} from '@/api/auth'
import { attachAuthHooks } from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  // Access-токен живёт только в памяти — никогда не пишем в localStorage,
  // иначе XSS-эксплойт сможет его извлечь.
  const accessToken = ref<string | null>(null)
  const user = ref<UserPublic | null>(null)
  const initialised = ref(false)

  const isAuthenticated = computed(() => accessToken.value !== null && user.value !== null)
  const isAdmin = computed(() => user.value?.role === 'admin')

  function setAccessToken(token: string | null): void {
    accessToken.value = token
    if (!token) {
      user.value = null
    }
  }

  let onAuthLostCallback: (() => void) | null = null

  function registerAuthLostHandler(cb: () => void): void {
    onAuthLostCallback = cb
  }

  attachAuthHooks({
    getAccessToken: () => accessToken.value,
    setAccessToken,
    onAuthLost: () => onAuthLostCallback?.(),
  })

  async function register(payload: RegisterPayload): Promise<UserPublic> {
    const { data } = await authApi.register(payload)
    return data.user
  }

  async function verifyEmail(payload: VerifyEmailPayload): Promise<UserPublic> {
    const { data } = await authApi.verifyEmail(payload)
    return data.user
  }

  async function login(payload: LoginPayload): Promise<UserPublic> {
    const { data } = await authApi.login(payload)
    accessToken.value = data.access_token
    user.value = data.user
    return data.user
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } finally {
      accessToken.value = null
      user.value = null
    }
  }

  async function fetchMe(): Promise<UserPublic | null> {
    if (!accessToken.value) return null
    const { data } = await authApi.me()
    user.value = data
    return data
  }

  // Тихая попытка восстановить сессию по refresh-cookie при загрузке SPA.
  async function tryRestoreSession(): Promise<void> {
    if (initialised.value) return
    initialised.value = true
    try {
      const { data } = await authApi.refresh()
      accessToken.value = data.access_token
      await fetchMe()
    } catch {
      accessToken.value = null
      user.value = null
    }
  }

  return {
    accessToken,
    user,
    isAuthenticated,
    isAdmin,
    register,
    verifyEmail,
    login,
    logout,
    fetchMe,
    tryRestoreSession,
    registerAuthLostHandler,
  }
})
