<script setup lang="ts">
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { ElMessage } from 'element-plus'
import { Bell, ChatDotRound, Star, User } from '@element-plus/icons-vue'
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '@/api/notifications'
import { useUiStore } from '@/stores/ui'
import { fromNow } from '@/utils/time'
import UserAvatar from '@/components/UserAvatar.vue'
import type { NotificationItem, NotificationListData } from '@/types'

const router = useRouter()
const ui = useUiStore()
const qc = useQueryClient()

const { data, isLoading, refetch } = useQuery({
  queryKey: ['notifications'],
  queryFn: () => listNotifications({ page: 1, per_page: 50 }),
})

// 同步未读数到左栏 badge
watch(
  () => data.value?.unread_count,
  (n) => {
    if (typeof n === 'number') ui.setUnread(n)
  },
  { immediate: true },
)

const typeIcon = (t: string) => (t === 'like' ? Star : t === 'comment' ? ChatDotRound : t === 'follow' ? User : Bell)

/** 乐观标记若干条为已读：列表项红点立即消失 + badge 同步递减（组件卸载也不影响） */
function markReadLocally(ids: number[]) {
  const set = new Set(ids)
  qc.setQueryData<NotificationListData>(['notifications'], (old) =>
    old
      ? {
          ...old,
          items: old.items.map((i) => (set.has(i.id) ? { ...i, is_read: true } : i)),
          unread_count: Math.max(0, old.unread_count - ids.length),
        }
      : old,
  )
  ui.setUnread(ui.unreadCount - ids.length)
}

/** 标记失败时回滚乐观更新 */
function revertReadLocally(ids: number[]) {
  const set = new Set(ids)
  qc.setQueryData<NotificationListData>(['notifications'], (old) =>
    old
      ? {
          ...old,
          items: old.items.map((i) => (set.has(i.id) ? { ...i, is_read: false } : i)),
          unread_count: old.unread_count + ids.length,
        }
      : old,
  )
  ui.setUnread(ui.unreadCount + ids.length)
}

async function open(n: NotificationItem) {
  const wasUnread = !n.is_read
  if (wasUnread) markReadLocally([n.id]) // 本地先行，弱网也不卡
  if (n.resource_type === 'post') router.push(`/post/${n.resource_id}`)
  else if (n.resource_type === 'user') router.push(`/user/${n.actor_id}`)
  if (wasUnread) {
    try {
      await markNotificationRead(n.id)
    } catch (e) {
      revertReadLocally([n.id])
      ElMessage.error(e instanceof Error ? e.message : '标记已读失败')
    }
  }
}

async function readAll() {
  const hadUnread = (data.value?.unread_count ?? 0) > 0
  if (hadUnread) {
    // 乐观：当前页全部置已读、badge 归零（未读数可能含未加载的更多页，故直接归零）
    qc.setQueryData<NotificationListData>(['notifications'], (old) =>
      old
        ? { ...old, items: old.items.map((i) => ({ ...i, is_read: true })), unread_count: 0 }
        : old,
    )
    ui.setUnread(0)
  }
  try {
    await markAllNotificationsRead()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败')
    refetch() // 回滚：拉服务端真值
  }
}
</script>

<template>
  <div>
    <header class="page-head">
      <h1 class="serif">通知</h1>
      <el-button text size="small" :disabled="!data?.unread_count" @click="readAll">
        全部已读
      </el-button>
    </header>

    <el-skeleton v-if="isLoading" :rows="4" animated style="padding: 24px 22px" />

    <template v-else>
      <div
        v-for="n in data?.items || []"
        :key="n.id"
        class="notice"
        :class="{ unread: !n.is_read }"
        @click="open(n)"
      >
        <span class="type-icon" :class="`t-${n.type}`">
          <el-icon :size="15"><component :is="typeIcon(n.type)" /></el-icon>
        </span>
        <UserAvatar :name="n.actor_name || '?'" :size="36" />
        <div class="n-body">
          <p class="n-text">{{ n.content }}</p>
          <span class="mono text-3 n-time">{{ fromNow(n.created_at) }}</span>
        </div>
        <span v-if="!n.is_read" class="dot" />
      </div>

      <el-empty v-if="!data?.items?.length" description="还没有通知" :image-size="80" />
    </template>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px 12px;
  border-bottom: 1px solid var(--line-soft);
}

.page-head h1 {
  margin: 0;
  font-size: 20px;
  letter-spacing: 0.08em;
}

.notice {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 15px 22px;
  border-bottom: 1px solid var(--line-soft);
  cursor: pointer;
  transition: background 0.15s;
}

.notice:hover {
  background: var(--paper-2);
}

.notice.unread {
  background: var(--accent-tint);
}

.notice.unread:hover {
  background: #f4e3d8;
}

.type-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}

.t-like { background: var(--like); }
.t-comment { background: #4a6fa5; }
.t-follow { background: #6d8b74; }
.t-system { background: var(--ink-3); }

.n-body {
  flex: 1;
  min-width: 0;
}

.n-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
}

.n-time {
  font-size: 11.5px;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
}
</style>
