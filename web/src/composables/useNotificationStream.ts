import { useQueryClient } from '@tanstack/vue-query'
import { getMe } from '@/api/users'
import { getUnreadCount, streamNotifications } from '@/api/notifications'
import { useUiStore } from '@/stores/ui'

/**
 * 通知实时流：登录后连接 SSE，收事件更新未读角标并刷新通知列表。
 * 断线退避重连；401 借 /users/me 触发 axios 静默刷新；
 * 长连不可用时降级为 unread-count 轮询。
 */
export function useNotificationStream() {
  const ui = useUiStore()
  const qc = useQueryClient()
  let controller: AbortController | null = null
  let stopped = false
  let backoff = 1000
  let pollTimer: number | null = null

  function stopPolling() {
    if (pollTimer !== null) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function startPolling() {
    if (pollTimer !== null) return
    pollTimer = window.setInterval(async () => {
      try {
        const d = await getUnreadCount()
        if (typeof d.unread_count === 'number') ui.setUnread(d.unread_count)
      } catch {
        /* 轮询失败忽略，下一轮再试 */
      }
    }, 15000)
  }

  async function loop() {
    while (!stopped) {
      controller = new AbortController()
      try {
        await streamNotifications({
          signal: controller.signal,
          onOpen: () => {
            backoff = 1000
            stopPolling()
          },
          onEvent: (e) => {
            if (typeof e.unread_count === 'number') ui.setUnread(e.unread_count)
            qc.invalidateQueries({ queryKey: ['notifications'] })
          },
        })
      } catch {
        if (stopped) return
        // 会话失效或 token 过期：借 /users/me 走 axios 静默刷新；失败则停止
        try {
          await getMe()
        } catch {
          stopped = true
          break
        }
      }
      if (stopped) return
      startPolling()
      await new Promise((r) => window.setTimeout(r, backoff))
      backoff = Math.min(backoff * 2, 15000)
    }
  }

  function start() {
    stopped = false
    backoff = 1000
    void loop()
  }

  function stop() {
    stopped = true
    controller?.abort()
    controller = null
    stopPolling()
  }

  return { start, stop }
}
