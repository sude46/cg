import { defineStore } from 'pinia'
import {
  changePassword as apiChangePassword,
  getMe,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
} from '@/api/users'
import { getRefreshToken, setAccessToken, setRefreshToken, http } from '@/api/http'
import type { User } from '@/types'

/**
 * token 策略：access 放内存（Pinia），refresh 放 localStorage。
 * 已知风险：localStorage 有 XSS 面——缓解靠全站禁 v-html（ESLint 强制）+ 输入转义。
 */
export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as User | null,
    ready: false, // 启动时是否已尝试恢复会话
  }),
  getters: {
    isLoggedIn: (s) => !!s.user,
  },
  actions: {
    async login(username: string, password: string) {
      const data = await apiLogin({ username, password })
      setAccessToken(data.access_token)
      setRefreshToken(data.refresh_token)
      this.user = await getMe()
    },
    async register(payload: { username: string; email: string; password: string }) {
      const data = await apiRegister(payload)
      setAccessToken(data.access_token)
      setRefreshToken(data.refresh_token)
      this.user = await getMe()
    },
    async changePassword(oldPassword: string, newPassword: string) {
      await apiChangePassword({ old_password: oldPassword, new_password: newPassword })
      // 改密后旧 access/refresh 全部失效：清空本地 token 并回登录页
      setAccessToken(null)
      setRefreshToken(null)
      this.user = null
      if (!window.location.hash.includes('/login')) {
        window.location.hash = '#/login'
      }
    },
    async logout() {
      try {
        await apiLogout()
      } finally {
        setAccessToken(null)
        setRefreshToken(null)
        this.user = null
      }
    },
    /** 启动恢复：有 refresh token 就静默换新 access（刷新逻辑在 http 拦截器里，这里借助 /users/me 触发） */
    async tryRestore() {
      if (this.ready) return
      try {
        if (getRefreshToken()) {
          // 无 access token 时 /users/me 会 401 → 拦截器自动刷新并重放
          this.user = await getMe()
        }
      } catch {
        // 恢复失败保持未登录态
      } finally {
        this.ready = true
      }
    },
  },
})

// 避免未使用告警（http 在拦截器中已接线）
void http
