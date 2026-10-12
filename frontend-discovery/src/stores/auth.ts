import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
export interface UserInfo { userId: string; tenantId: string; username?: string }
export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('studio-agent-token'))
  const user = ref<UserInfo | null>((() => { try { return JSON.parse(localStorage.getItem('studio-agent-user') ?? 'null') } catch { return null } })())
  const isLoggedIn = computed(() => !!token.value)
  function login(accessToken: string, userInfo: UserInfo) { token.value=accessToken; user.value=userInfo; localStorage.setItem('studio-agent-token',accessToken); localStorage.setItem('studio-agent-user',JSON.stringify(userInfo)) }
  function logout() { token.value=null; user.value=null; localStorage.removeItem('studio-agent-token'); localStorage.removeItem('studio-agent-user') }
  return { token, user, isLoggedIn, login, logout }
})

