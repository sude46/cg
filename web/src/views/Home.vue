<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useInfiniteQuery } from '@tanstack/vue-query'
import { getTimeline } from '@/api/feeds'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PostCard from '@/components/PostCard.vue'
import UserAvatar from '@/components/UserAvatar.vue'

const auth = useAuthStore()
const ui = useUiStore()
const PER_PAGE = 10

const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading, refetch } = useInfiniteQuery({
  queryKey: ['timeline'],
  queryFn: ({ pageParam }) => getTimeline({ cursor: pageParam, limit: PER_PAGE }),
  initialPageParam: null as string | null,
  getNextPageParam: (last) => (last.has_more ? last.next_cursor ?? undefined : undefined),
})

/* 无限滚动：哨兵元素进入视口即加载下一页 */
const sentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

onMounted(() => {
  observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && hasNextPage.value && !isFetchingNextPage.value) {
      fetchNextPage()
    }
  })
  if (sentinel.value) observer.observe(sentinel.value)
})

onBeforeUnmount(() => observer?.disconnect())

function onPublished() {
  refetch()
}

function onDeleted() {
  refetch()
}
</script>

<template>
  <div>
    <header class="page-head">
      <h1 class="serif">首页</h1>
      <span class="mono text-3 sub">TIMELINE</span>
    </header>

    <!-- 迷你 composer：点击进入发帖弹窗 -->
    <div class="mini-composer" @click="ui.openComposer()">
      <UserAvatar :name="auth.user?.username || '?'" :size="38" />
      <span class="placeholder">安利一本正在追的书吧…</span>
      <el-button type="primary" round size="small" disabled>发布</el-button>
    </div>

    <el-skeleton v-if="isLoading" :rows="4" animated style="padding: 24px 22px" />

    <template v-else>
      <template v-for="(page, idx) in data?.pages || []" :key="idx">
        <PostCard v-for="p in page.items" :key="p.id" :post="p" @deleted="onDeleted" />
      </template>

      <div ref="sentinel" class="sentinel">
        <span v-if="isFetchingNextPage" class="mono text-3">加载中…</span>
        <span v-else-if="!hasNextPage && (data?.pages?.length ?? 0) > 0" class="end mono text-3">
          · 到底啦 ·
        </span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 20px 22px 14px;
  position: sticky;
  top: 0;
  background: rgba(251, 251, 249, 0.92);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--line-soft);
  z-index: 5;
}

.page-head h1 {
  margin: 0;
  font-size: 20px;
  letter-spacing: 0.08em;
}

.sub {
  font-size: 11px;
  letter-spacing: 0.18em;
}

.mini-composer {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 22px;
  border-bottom: 1px solid var(--line-soft);
  cursor: pointer;
}

.placeholder {
  flex: 1;
  color: var(--ink-3);
  font-size: 14.5px;
}

.sentinel {
  text-align: center;
  padding: 22px;
  font-size: 12px;
}

.end {
  letter-spacing: 0.3em;
}
</style>
