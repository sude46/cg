import { ApiError, API_BASE_URL, getAccessToken, http, unwrap } from './http'
import type {
  ChatMessage,
  ChatMessageData,
  ChatStreamEvent,
  ConversationItem,
  PageResult,
} from '@/types'

/** 发起（或复用）会话：同对端永远只有一个会话，幂等 */
export function createConversation(peerId: number) {
  return unwrap(http.post('/chats', { peer_id: peerId })) as Promise<{
    conversation_id: number
    peer_id: number
  }>
}

/** 会话列表（分页，按最近消息倒序） */
export function listConversations(params: { page?: number; per_page?: number }) {
  return unwrap(http.get('/chats', { params })) as Promise<PageResult<ConversationItem>>
}

/** 历史消息（游标分页；返回"最新在前"的倒序数组） */
export function listMessages(
  conversationId: number,
  params: { cursor?: string | null; limit?: number },
) {
  return unwrap(http.get(`/chats/${conversationId}/messages`, { params })) as Promise<ChatMessageData>
}

/** 发消息：返回落库后的完整消息对象 */
export function sendMessage(conversationId: number, content: string) {
  return unwrap(http.post(`/chats/${conversationId}/messages`, { content })) as Promise<ChatMessage>
}

/** 把整个会话标记为已读（进入聊天窗口时调用） */
export function markConversationRead(conversationId: number) {
  return unwrap(
    http.patch('/chats/messages/read', { conversation_id: conversationId }),
  ) as Promise<{ conversation_id: number; marked: number; last_read_id: number | null }>
}

export function getChatUnreadCount() {
  return unwrap(http.get('/chats/unread-count')) as Promise<{ unread_count: number }>
}

/**
 * 实时私信流（SSE）。
 * 与 streamNotifications 同套路：EventSource 带不了 Authorization 头，
 * 用 fetch + ReadableStream 手动解析 SSE（data: xxx\n\n）。
 */
export async function streamChatEvents(opts: {
  signal: AbortSignal
  onEvent: (e: ChatStreamEvent) => void
}) {
  const token = getAccessToken()
  const res = await fetch(`${API_BASE_URL}/chats/stream`, {
    headers: {
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal: opts.signal,
  })
  if (res.status === 401) throw new ApiError('未登录', 401)
  if (!res.ok || !res.body) throw new Error(`私信流连接失败 (${res.status})`)

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
          opts.onEvent(JSON.parse(line.slice(5).trim()) as ChatStreamEvent)
        } catch {
          /* 心跳行与非法负载忽略 */
        }
      }
    }
  }
}
