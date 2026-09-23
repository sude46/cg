<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useInfiniteQuery } from '@tanstack/vue-query'
import { ElMessage } from 'element-plus'
import { getChatUnreadCount, listMessages, markConversationRead, sendMessage } from '@/api/chats'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import type { ChatMessage } from '@/types'

const route = useRoute()
const auth = useAuthStore()
const ui = useUiStore()
const conversationId = Number(route.params.id)
const PER_PAGE = 20

const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } = useInfiniteQuery({
  queryKey: ['chat-messages', conversationId],
  queryFn: ({ pageParam }) => listMessages(conversationId, { cursor: pageParam, limit: PER_PAGE }),
  initialPageParam: null as string | null,
  getNextPageParam: (last) => (last.has_more ? last.next_cursor ?? undefined : undefined),
})

/** 历史消息：各页内部"最新在前"，整体按 id 升序还原为聊天正序 */
const history = computed<ChatMessage[]>(() => {
  const all = (data.value?.pages || []).flatMap((p) => p.items)
  return all.slice().sort((a, b) => a.id - b.id)
})

/** 实时收到 + 本地发出（按 id 去重，避免和历史页重叠） */
const live = ref<ChatMessage[]>([])
const historyIds = computed(() => new Set(history.value.map((m) => m.id)))
const messages = computed(() => [
  ...history.value,
  ...live.value.filter((m) => !historyIds.value.has(m.id)),
])

async function markRead() {
  try {
    await markConversationRead(conversationId)
    const { unread_count } = await getChatUnreadCount()
    ui.setChatUnread(unread_count)
  } catch {
    /* 已读失败不阻塞聊天 */
  }
}

function onIncoming(evt: Event) {
  const m = (evt as CustomEvent<ChatMessage>).detail
  if (!m || m.conversation_id !== conversationId) return
  if (!live.value.some((x) => x.id === m.id)) live.value.push(m)
  scrollToBottom()
  void markRead() // 正在看该会话 → 标已读并同步 badge
}

onMounted(() => {
  window.addEventListener('chat:message', onIncoming)
  void markRead()
  scrollToBottom()
})
onUnmounted(() => window.removeEventListener('chat:message', onIncoming))

const draft = ref('')
const sending = ref(false)
async function onSend() {
  const content = draft.value.trim()
  if (!content || sending.value) return
  sending.value = true
  try {
    const saved = await sendMessage(conversationId, content)
    if (!live.value.some((x) => x.id === saved.id)) live.value.push(saved)
    draft.value = ''
    scrollToBottom()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '发送失败')
  } finally {
    sending.value = false
  }
}

const scroller = ref<HTMLElement | null>(null)
function scrollToBottom() {
  nextTick(() => {
    scroller.value?.scrollTo({ top: scroller.value.scrollHeight })
  })
}
watch(() => messages.value.length, scrollToBottom)
</script>

<template>
  <div class="room">
    <header class="page-head">
      <h1 class="serif">私信</h1>
    </header>

    <div ref="scroller" class="msgs">
      <div v-if="hasNextPage" class="more" @click="fetchNextPage()">
        <span v-if="isFetchingNextPage">加载中…</span>
        <span v-else>加载更早的消息</span>
      </div>
      <el-skeleton v-if="isLoading" :rows="4" animated style="padding: 16px" />

      <div
        v-for="m in messages"
        :key="m.id"
        class="bubble-row"
        :class="{ mine: m.sender_id === auth.user?.id }"
      >
        <div class="bubble">{{ m.content }}</div>
      </div>

      <el-empty v-if="!isLoading && !messages.length" description="开始聊天吧" :image-size="70" />
    </div>

    <footer class="composer">
      <el-input
        v-model="draft"
        type="textarea"
        :rows="2"
        resize="none"
        placeholder="说点什么…（Enter 发送）"
        @keydown.enter.exact.prevent="onSend"
      />
      <el-button type="primary" :loading="sending" :disabled="!draft.trim()" @click="onSend">
        发送
      </el-button>
    </footer>
  </div>
</template>

<style scoped>
.room {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.page-head {
  padding: 16px 22px;
  border-bottom: 1px solid var(--line-soft);
}
.page-head h1 {
  margin: 0;
  font-size: 18px;
}
.msgs {
  flex: 1;
  overflow-y: auto;
  padding: 16px 22px;
}
.more {
  text-align: center;
  font-size: 12px;
  color: var(--ink-3);
  cursor: pointer;
  padding: 8px;
}
.bubble-row {
  display: flex;
  margin-bottom: 10px;
}
.bubble-row.mine {
  justify-content: flex-end;
}
.bubble {
  max-width: 70%;
  padding: 9px 13px;
  border-radius: 14px;
  background: var(--paper-2);
  font-size: 14px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}
.bubble-row.mine .bubble {
  background: var(--accent);
  color: #fff;
}
.composer {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding: 12px 22px;
  border-top: 1px solid var(--line-soft);
}
</style>
