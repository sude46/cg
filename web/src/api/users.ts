import { http, unwrap } from './http'
import type { LoginData, PageResult, User } from '@/types'

export function login(payload: { username: string; password: string }) {
  return unwrap(http.post('/users/login', payload)) as Promise<LoginData>
}

export function register(payload: { username: string; email: string; password: string }) {
  return unwrap(http.post('/users/register', payload)) as Promise<LoginData>
}

export function logout() {
  return unwrap(http.post('/users/logout')) as Promise<Record<string, never>>
}

export async function getMe() {
  
  const data = (await unwrap(http.get('/users/me'))) as { user: User }
  return data.user
}

/** 公开资料：GET /users/<id>（未登录也可，登录态带 is_following/is_me） */
export async function getUserProfile(userId: number) {
  const data = (await unwrap(http.get(`/users/${userId}`))) as { user: User }
  return data.user
}

/** 更新当前用户资料（可改 username/email/bio/avatar_url） */
export function updateProfile(payload: {
  username?: string
  email?: string
  bio?: string | null
  avatar_url?: string | null
}) {
  return unwrap(http.put('/users/me', payload)) as Promise<{ user: User }>
}

/** 修改密码：成功会使所有旧 token 失效（前端需清空并回登录页） */
export function changePassword(payload: { old_password: string; new_password: string }) {
  return unwrap(http.put('/users/me/password', payload)) as Promise<Record<string, unknown>>
}

/** 按用户名搜索用户（脱敏，不含 email） */
export function searchUsers(params: { q: string; page?: number; per_page?: number }) {
  return unwrap(http.get('/users/search', { params })) as Promise<PageResult<User>>
}
