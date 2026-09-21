import { http, unwrap } from './http'
import type { HotSearch, PageResult, Pagination, Post, PostListData } from '@/types'

/**
 * posts 模块的 data 形状：{ items, pagination, liked_post_ids }
 * 在这里归一化成 { items, pagination }，并把 liked_post_ids 折叠进 post.is_liked。
 */
function normalizePost(raw: Record<string, unknown>, likedIds?: Set<number>): Post {
  const p = raw as unknown as Post & { user_name?: string }
  return {
    ...p,
    // 后端列表项带扁平 username；事件载荷里叫 user_name，做一层兼容
    username: p.username ?? p.user_name ?? '未知用户',
    is_liked: likedIds ? likedIds.has(p.id) : p.is_liked,
  }
}

function normalizePage(data: PostListData): PageResult<Post> {
  const liked = new Set(data.liked_post_ids || [])
  return {
    items: (data.items || []).map((p) => normalizePost(p as never, liked)),
    pagination: data.pagination,
  }
}

export async function listPosts(params: {
  page?: number
  per_page?: number
  user_id?: number | string
}): Promise<PageResult<Post>> {
  const data = (await unwrap(http.get('/posts', { params }))) as PostListData
  return normalizePage(data)
}

export async function getPost(postId: number): Promise<Post> {
  const data = await unwrap(http.get(`/posts/${postId}`)) as { post: Post; has_liked: boolean }
  return normalizePost({ ...data.post, is_liked: data.has_liked } as never)
}

export function createPost(payload: { content: string; image_url?: string | null }) {
  return unwrap(http.post('/posts', payload)) as Promise<Post>
}

export function updatePost(postId: number, payload: { content?: string; image_url?: string | null }) {
  return unwrap(http.put(`/posts/${postId}`, payload)) as Promise<Post>
}

export function deletePost(postId: number) {
  return unwrap(http.delete(`/posts/${postId}`)) as Promise<Record<string, never>>
}

export async function searchPosts(params: {
  q: string
  page?: number
  per_page?: number
  sort?: 'relevance' | 'time' | 'hot'
}): Promise<PageResult<Post>> {
  const data = (await unwrap(http.get('/posts/search', { params }))) as PostListData
  return normalizePage(data)
}

export async function getSearchSuggestions(q: string, size = 8): Promise<string[]> {
  const data = (await unwrap(http.get('/posts/search/suggestions', { params: { q, size } }))) as {
    items: string[]
  }
  return data.items || []
}

export async function getHotSearches(size = 10): Promise<HotSearch[]> {
  const data = (await unwrap(http.get('/posts/hot-searches', { params: { size } }))) as {
    items: HotSearch[]
  }
  return data.items || []
}

export type { Pagination }
