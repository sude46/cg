import { http, unwrap } from './http'
import type { TimelineData } from '@/types'

/**
 * 首页时间线（游标分页）。
 * 注意：Feed 推送由后端订阅 post.created 事件自动完成，前端永不调用 /feeds/publish。
 */
export function getTimeline(params: { cursor?: string | null; limit?: number }) {
  return unwrap(http.get('/feeds/timeline', { params })) as Promise<TimelineData>
}

export function refreshTimeline() {
  return unwrap(http.post('/feeds/refresh')) as Promise<{ refreshed: boolean }>
}

/** 广场（全站帖子，游标分页，结构与 TimelineData 一致） */
export function getExplore(params: { cursor?: string | null; limit?: number }) {
  return unwrap(http.get('/feeds/explore', { params })) as Promise<TimelineData>
}
