<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { listConversations } from '@/api/chats'
import { fromNow } from '@/utils/time'
import UserAvatar from '@/components/UserAvatar.vue'

const { data, isLoading } = useQuery({
  queryKey: ['chat-conversations'],
  queryFn: () => listConversations({ page: 1, per_page: 50 }),
})
</script>

<template>
  <div>
    <header class="page-head">
      <h1 class="serif">私信</h1>
    </header>

    <el-skeleton v-if="isLoading" :rows="4" animated style="padding: 24px 22px" />

    <template v-else>
      <router-link
        v-for="c in data?.items || []"
        :key="c.conversation_id"
        class="conv"
        :to="`/chats/${c.conversation_id}`"
      >
        <UserAvatar :name="c.peer_username || String(c.peer_id)" :size="40" />
        <div class="c-body">
          <div class="c-top">
            <span class="c-name">{{ c.peer_username || `用户#${c.peer_id}` }}</span>
            <span class="mono text-3 c-time">{{ c.last_message_at ? fromNow(c.last_message_at) : '' }}</span>
          </div>
          <p class="c-preview">{{ c.last_message_preview || '（暂无消息）' }}</p>
        </div>
      </router-link>
      <el-empty
        v-if="!data?.items?.length"
        description="还没有私信，去用户主页找个人聊聊吧"
        :image-size="80"
      />
    </template>
  </div>
</template>

<style scoped>
.page-head {
  padding: 20px 22px 14px;
  border-bottom: 1px solid var(--line-soft);
}
.page-head h1 {
  margin: 0;
  font-size: 20px;
  letter-spacing: 0.08em;
}
.conv {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 22px;
  border-bottom: 1px solid var(--line-soft);
  transition: background 0.15s;
}
.conv:hover {
  background: var(--paper-2);
}
.c-body {
  flex: 1;
  min-width: 0;
}
.c-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}
.c-name {
  font-size: 14px;
  font-weight: 600;
}
.c-time {
  font-size: 11.5px;
  flex-shrink: 0;
}
.c-preview {
  margin: 2px 0 0;
  font-size: 13.5px;
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
