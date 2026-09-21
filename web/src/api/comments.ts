import { http, unwrap } from './http'
import type { Comment, CommentListData, PageResult } from '@/types'

/** 评论模块 data 形状：{ items, pagination }（与目标契约一致，直接透传） */
export async function listComments(
  postId: number,
  params: { page?: number; per_page?: number },
): Promise<PageResult<Comment>> {
  const data = (await unwrap(
    http.get(`/comments/posts/${postId}/comments`, { params }),
  )) as CommentListData
  return { items: data.items || [], pagination: data.pagination }
}

export function createComment(payload: { post_id: number; content: string }) {
  return unwrap(http.post('/comments', payload)) as Promise<Comment>
}

export function deleteComment(commentId: number) {
  return unwrap(http.delete(`/comments/${commentId}`)) as Promise<Record<string, never>>
}
