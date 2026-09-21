/** 统一响应信封（与后端 utils/response.py 对齐） */
export interface ApiEnvelope<T = unknown> {
  code: number
  data: T
  message?: string
}

/** 失败响应体（注意：失败字段是 error 不是 message，429 多 retry_after） */
export interface ApiErrorBody {
  code: number
  error: string
  request_id?: string
  retry_after?: number
}

export interface Pagination {
  page: number
  per_page: number
  total: number
  pages: number
  has_next: boolean
  has_prev: boolean
}

export interface User {
  id: number
  username: string
  email?: string
  bio?: string
  avatar_url?: string | null
  follower_count?: number
  following_count?: number
  post_count?: number
  created_at?: string
  is_following?: boolean
  is_me?: boolean
}

export interface Post {
  id: number
  user_id: number
  username: string
  avatar_url?: string | null
  content: string
  image_url?: string | null
  like_count: number
  comment_count: number
  created_at: string
  is_liked?: boolean
}

export interface Comment {
  id: number
  post_id: number
  user_id: number
  username: string
  avatar_url?: string | null
  content: string
  like_count: number
  created_at: string
}

export type NotificationType = 'like' | 'comment' | 'follow' | 'system'

export interface NotificationItem {
  id: number
  user_id: number
  actor_id: number
  actor_name?: string
  type: NotificationType | string
  resource_id: number
  resource_type: string
  content: string
  is_read: boolean
  created_at: string
}

/** 后端列表 data 形状：{ items, pagination, liked_post_ids } */
export interface PostListData {
  items: Post[]
  pagination: Pagination
  liked_post_ids: number[]
}

export interface TimelineData {
  items: Post[]
  source: 'cache' | 'db' | 'empty'
  next_cursor: string | null
  has_more: boolean
}

export interface CommentListData {
  items: Comment[]
  pagination: Pagination
}

export interface NotificationListData {
  items: NotificationItem[]
  pagination: Pagination
  unread_count: number
}

export interface PageResult<T> {
  items: T[]
  pagination: Pagination
}

export interface LoginData {
  access_token: string
  refresh_token: string
}

export interface HotSearch {
  rank: number
  keyword: string
  heat?: number
}
