import { http, unwrap } from './http'
import type { PageResult, User } from '@/types'

export function followUser(followedId: number) {
  return unwrap(http.post('/follows/following', { followed_id: followedId })) as Promise<
    Record<string, never>
  >
}

export function unfollowUser(followedId: number) {
  return unwrap(http.delete(`/follows/following/${followedId}`)) as Promise<Record<string, never>>
}

export function listFollowers(params: { page?: number; per_page?: number }) {
  return unwrap(http.get('/follows/followers', { params })) as Promise<PageResult<User>>
}

export function listFollowing(params: { page?: number; per_page?: number }) {
  return unwrap(http.get('/follows/following/list', { params })) as Promise<PageResult<User>>
}

export function listMutual(params: { page?: number; per_page?: number }) {
  return unwrap(http.get('/follows/following/mutual', { params })) as Promise<PageResult<User>>
}

/** 指定用户关注的人（他人主页） */
export function listUserFollowing(userId: number, params: { page?: number; per_page?: number }) {
  return unwrap(
    http.get(`/follows/users/${userId}/following`, { params }),
  ) as Promise<PageResult<User>>
}

/** 指定用户的粉丝（他人主页） */
export function listUserFollowers(userId: number, params: { page?: number; per_page?: number }) {
  return unwrap(
    http.get(`/follows/users/${userId}/followers`, { params }),
  ) as Promise<PageResult<User>>
}
