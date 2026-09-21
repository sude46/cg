import { ApiError, API_BASE_URL, getAccessToken, http, unwrap } from './http'
import type { NotificationItem, NotificationListData } from '@/types'

/** 通知列表：data 里带 unread_count */
export function listNotifications(params: {
  page?: number
  per_page?: number
  unread_only?: boolean
}) {
  return unwrap(http.get('/notifications', { params })) as Promise<NotificationListData>
}

/** 轻量未读数（SSE 降级轮询用） */
export function getUnreadCount() {
  return unwrap(http.get('/notifications/unread-count')) as Promise<{ unread_count: number }>
}

export function markNotificationRead(notificationId: number) {
  return unwrap(http.patch(`/notifications/${notificationId}/read`)) as Promise<NotificationItem>
}

export function markAllNotificationsRead() {
  return unwrap(http.patch('/notifications/read-all')) as Promise<Record<string, never>>
}

export interface NotificationStreamEvent {
  type: string
  unread_count: number
  notification?: NotificationItem
}

/**
 * 实时通知流（SSE）。
 * 不用 EventSource：它无法携带 Authorization 头，而 access token 存内存。
 * fetch + ReadableStream 可带 Bearer，后端中间件照常校验。
 */
export async function streamNotifications(opts: {
  signal: AbortSignal
  onEvent: (e: NotificationStreamEvent) => void
  onOpen?: () => void
}) {
  const token = getAccessToken()
  const res = await fetch(`${API_BASE_URL}/notifications/stream`, {
    headers: {
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal: opts.signal,
  })
  if (res.status === 401) throw new ApiError('未登录', 401)
  if (!res.ok || !res.body) throw new Error(`通知流连接失败 (${res.status})`)

  opts.onOpen?.()
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data:')) continue
        try {
          opts.onEvent(JSON.parse(line.slice(5).trim()) as NotificationStreamEvent)
        } catch {
          /* 忽略非法负载 */
        }
      }
    }
  }
}
