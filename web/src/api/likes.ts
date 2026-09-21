import { http, unwrap } from './http'

/** 点赞：POST /posts/<id>/likes（挂在 likes 命名空间下） */
export function likePost(postId: number) {
  return unwrap(http.post(`/likes/posts/${postId}/likes`)) as Promise<Record<string, never>>
}

/**
 * 取消点赞：DELETE /posts/<id>/likes
 * 后端 P0-2 已修复：按 (user_id, post_id) 幂等删除，不需要 like_id。
 */
export function unlikePost(postId: number) {
  return unwrap(http.delete(`/likes/posts/${postId}/likes`)) as Promise<Record<string, never>>
}
