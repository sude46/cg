import { http, unwrap } from './http'
import type { NotificationItem, NotificationListData } from '@/types'

/** 通知列表：data 里带 unread_count（未读数暂从这里取，后端补 unread-count 接口后可换轻量轮询） */
export function listNotifications(params: {
  page?: number
  per_page?: number
  unread_only?: boolean
}) {
  return unwrap(http.get('/notifications', { params })) as Promise<NotificationListData>
}

export function markNotificationRead(notificationId: number) {
  return unwrap(http.patch(`/notifications/${notificationId}/read`)) as Promise<NotificationItem>
}

export function markAllNotificationsRead() {
  return unwrap(http.patch('/notifications/read-all')) as Promise<Record<string, never>>
}
