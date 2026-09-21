<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { ArrowLeft } from '@element-plus/icons-vue'
import { getPost } from '@/api/posts'
import PostCard from '@/components/PostCard.vue'
import CommentList from '@/components/CommentList.vue'

const route = useRoute()
const router = useRouter()
const postId = computed(() => Number(route.params.id))

const { data: post, isLoading, refetch } = useQuery({
  queryKey: ['post', postId],
  queryFn: () => getPost(postId.value),
})
</script>

<template>
  <div>
    <header class="page-head">
      <button class="back" @click="router.back()">
        <el-icon :size="18"><ArrowLeft /></el-icon>
      </button>
      <h1 class="serif">帖子</h1>
    </header>

    <el-skeleton v-if="isLoading" :rows="5" animated style="padding: 24px 22px" />

    <template v-else-if="post">
      <PostCard :post="post" @deleted="router.push('/')" />
      <CommentList :post-id="postId" @changed="refetch" />
    </template>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 22px;
  position: sticky;
  top: 0;
  background: rgba(251, 251, 249, 0.92);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--line-soft);
  z-index: 5;
}

.page-head h1 {
  margin: 0;
  font-size: 18px;
  letter-spacing: 0.08em;
}

.back {
  border: none;
  background: none;
  color: var(--ink-2);
  cursor: pointer;
  padding: 6px;
  border-radius: 50%;
  transition: background 0.15s;
}

.back:hover {
  background: var(--paper-2);
  color: var(--ink);
}
</style>
