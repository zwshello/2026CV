import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, register as apiRegister, getProfile } from '@/api/user'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref<any>(null)

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function login(username: string, password: string) {
    const res = await apiLogin(username, password)
    token.value = res.data.token
    user.value = res.data.user
    localStorage.setItem('token', res.data.token)
    return res
  }

  async function register(data: any) {
    const res = await apiRegister(data)
    token.value = res.data.token
    user.value = res.data.user
    localStorage.setItem('token', res.data.token)
    return res
  }

  async function fetchProfile() {
    if (!token.value) return
    try {
      const res = await getProfile()
      user.value = res.data
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
  }

  return { token, user, isLoggedIn, isAdmin, login, register, fetchProfile, logout }
})
