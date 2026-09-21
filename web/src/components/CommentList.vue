<script setup lang="ts">
import { ref } from 'vue'
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { ElMessage } from 'element-plus'
import { createComment, deleteComment, listComments } from '@/api/comments'
import { useAuthStore } from '@/stores/auth'
import { fromNow } from '@/utils/time'
import UserAvatar from './UserAvatar.vue'

const props = defineProps<{ postId: number }>()
const auth = useAuthStore()
const qc = useQueryClient()

const PER_PAGE = 20
const queryKey = ['comments', props.postId]

const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } = useInfiniteQuery({
  queryKey,
  queryFn: ({ pageParam }) => listComments(props.postId, { page: pageParam, per_page: PER_PAGE }),
  initialPageParam: 1,
  getNextPageParam: (last) => (last.pagination.has_next ? last.pagination.page + 1 : undefined),
})

const draft = ref('')
const publish = useMutation({
  mutationFn: () => createComment({ post_id: props.postId, content: draft.value.trim() }),
  onSuccess: () => {
    draft.value = ''
    qc.invalidateQueries({ queryKey })
    ElMessage.success('评论成功')
  },
  onError: (e) => ElMessage.error(e instanceof Error ? e.message : '评论失败'),
})

async function onDelete(id: number) {
  try {
    await deleteComment(id)
    qc.invalidateQueries({ queryKey })
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <section class="comments">
    <div class="composer">
      <UserAvatar :name="auth.user?.username || '?'" :size="34" />
      <el-input
        v-model="draft"
        class="input"
        placeholder="写下你的评论"
        maxlength="500"
        @keyup.enter="draft.trim() && publish.mutate()"
      />
      <el-button
        type="primary"
        round
        size="small"
        :disabled="!draft.trim()"
        :loading="publish.isPending.value"
        @click="publish.mutate()"
      >
        评论
      </el-button>
    </div>

    <el-skeleton v-if="isLoading" :rows="3" animated style="padding: 16px 22px" />

    <template v-else>
      <div v-for="page in data?.pages || []" :key="page.pagination.page">
        <div v-for="c in page.items" :key="c.id" class="comment">
          <UserAvatar :name="c.username" :size="34" />
          <div class="c-body">
            <div class="c-head">
              <span class="c-name">{{ c.username }}</span>
              <span class="mono text-3 c-time">{{ fromNow(c.created_at) }}</span>
            </div>
            <p class="c-content">{{ c.content }}</p>
          </div>
          <el-popconfirm
            v-if="auth.user?.id === c.user_id"
            title="删除这条评论？"
            confirm-button-text="删除"
            cancel-button-text="取消"
            @confirm="onDelete(c.id)"
          >
            <template #reference><button class="c-del">删除</button></template>
          </el-popconfirm>
        </div>
      </div>

      <el-empty
        v-if="!data?.pages?.[0]?.items.length"
        description="还没有评论，来抢沙发"
        :image-size="80"
      />

      <div v-if="hasNextPage" class="more">
        <el-button text size="small" :loading="isFetchingNextPage" @click="fetchNextPage()">
          加载更多评论
        </el-button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.composer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 22px;
  border-bottom: 1px solid var(--line-soft);
}

.input :deep(.el-input__wrapper) {
  border-radius: 999px;
  background: var(--paper-2);
  box-shadow: none;
}

.comment {
  display: flex;
  gap: 10px;
  padding: 14px 22px;
  border-bottom: 1px solid var(--line-soft);
}

.c-body {
  flex: 1;
  min-width: 0;
}

.c-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.c-name {
  font-weight: 600;
  font-size: 13.5px;
}

.c-time {
  font-size: 11.5px;
}

.c-content {
  margin: 2px 0 0;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.c-del {
  border: none;
  background: none;
  color: var(--ink-3);
  font-size: 12px;
  cursor: pointer;
  align-self: flex-start;
  padding: 2px 0;
}

.c-del:hover {
  color: var(--like);
}

.more {
  text-align: center;
  padding: 12px;
}
</style>
