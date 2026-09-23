import { getChatUnreadCount, streamChatEvents } from '@/api/chats'
import { useUiStore } from '@/stores/ui'

/**
 * 全局私信 SSE 订阅（在 MainLayout 里与通知流并排启动）。
 * 收消息时：刷新私信未读数（以后端为准）+ 广播 window 事件给聊天窗口。
 * 断线指数退避重连（3s→6s→…→30s），与服务端 15s 心跳配合。
 */
export function useChatStream() {
  const ui = useUiStore()
  let controller: AbortController | null = null
  let stopped = false
  let retryMs = 3000

  async function refreshUnread() {
    try {
      const { unread_count } = await getChatUnreadCount()
      ui.setChatUnread(unread_count)
    } catch {
      /* 忽略，下一轮再同步 */
    }
  }

  async function connect() {
    controller = new AbortController()
    try {
      await streamChatEvents({
        signal: controller.signal,
        onEvent: (e) => {
          if (e.type === 'message.new') {
            window.dispatchEvent(new CustomEvent('chat:message', { detail: e.message }))
            refreshUnread()
          }
        },
      })
    } catch {
      /* 断线：走重连 */
    }
    if (!stopped) {
      window.setTimeout(connect, retryMs)
      retryMs = Math.min(retryMs * 2, 30000)
    }
  }

  return {
    start() {
      if (controller) return
      stopped = false
      retryMs = 3000
      refreshUnread()
      void connect()
    },
    stop() {
      stopped = true
      controller?.abort()
      controller = null
    },
    refreshUnread,
  }
}
