<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Star, StarFilled, Delete } from '@element-plus/icons-vue'
import { likePost, unlikePost } from '@/api/likes'
import { deletePost } from '@/api/posts'
import { useAuthStore } from '@/stores/auth'
import { fromNow, fullTime } from '@/utils/time'
import type { Post } from '@/types'
import UserAvatar from './UserAvatar.vue'

const props = defineProps<{ post: Post }>()
const emit = defineEmits<{ (e: 'deleted', id: number): void }>()

const router = useRouter()
const auth = useAuthStore()

/* 乐观更新：本地副本先行，失败回滚（后端点赞本就是先写 Redis 异步落库） */
const liked = ref(!!props.post.is_liked)
const likeCount = ref(props.post.like_count)
watch(
  () => props.post,
  (p) => {
    liked.value = !!p.is_liked
    likeCount.value = p.like_count
  },
)

let liking = false
async function toggleLike() {
  if (liking) return
  liking = true
  const prevLiked = liked.value
  const prevCount = likeCount.value
  liked.value = !prevLiked
  likeCount.value = prevLiked ? prevCount - 1 : prevCount + 1
  try {
    if (prevLiked) await unlikePost(props.post.id)
    else await likePost(props.post.id)
  } catch (e) {
    liked.value = prevLiked
    likeCount.value = prevCount
    ElMessage.error(e instanceof Error ? e.message : '操作失败')
  } finally {
    liking = false
  }
}

async function onDelete() {
  try {
    await deletePost(props.post.id)
    ElMessage.success('已删除')
    emit('deleted', props.post.id)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

function openDetail() {
  router.push(`/post/${props.post.id}`)
}

function openUser() {
  router.push(`/user/${props.post.user_id}`)
}
</script>

<template>
  <article class="post" @click="openDetail">
    <div @click.stop="openUser"><UserAvatar :name="post.username" :size="42" /></div>

    <div class="body">
      <header class="head">
        <span class="name" @click.stop="openUser">{{ post.username }}</span>
        <span class="time mono text-3" :title="fullTime(post.created_at)">{{ fromNow(post.created_at) }}</span>
      </header>

      <p class="content">{{ post.content }}</p>

      <el-image
        v-if="post.image_url"
        :src="post.image_url"
        fit="cover"
        class="image"
        lazy
        @click.stop
      >
        <template #error><div class="image-fallback">图片加载失败</div></template>
      </el-image>

      <footer class="actions" @click.stop>
        <button class="action" :class="{ liked }" @click="toggleLike">
          <el-icon :size="17" :class="{ pop: liked }">
            <StarFilled v-if="liked" />
            <Star v-else />
          </el-icon>
          <span class="mono">{{ likeCount }}</span>
        </button>

        <button class="action" @click="openDetail">
          <el-icon :size="17"><ChatDotRound /></el-icon>
          <span class="mono">{{ post.comment_count }}</span>
        </button>

        <el-popconfirm
          v-if="auth.user?.id === post.user_id"
          title="删除这条帖子？"
          confirm-button-text="删除"
          cancel-button-text="取消"
          @confirm="onDelete"
        >
          <template #reference>
            <button class="action danger"><el-icon :size="17"><Delete /></el-icon></button>
          </template>
        </el-popconfirm>
      </footer>
    </div>
  </article>
</template>

<style scoped>
.post {
  display: flex;
  gap: 12px;
  padding: 20px 22px;
  cursor: pointer;
  border-bottom: 1px solid var(--line-soft);
  transition: background 0.16s ease;
}

.post:hover {
  background: var(--paper-2);
}

.body {
  flex: 1;
  min-width: 0;
}

.head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 2px;
}

.name {
  font-weight: 600;
  font-size: 14.5px;
}

.name:hover {
  color: var(--accent);
}

.time {
  font-size: 12px;
}

.content {
  margin: 4px 0 0;
  font-size: 15px;
  line-height: 1.78;
  white-space: pre-wrap;
  word-break: break-word;
}

.image {
  margin-top: 12px;
  border-radius: var(--radius-md);
  max-height: 340px;
  width: 100%;
  border: 1px solid var(--line-soft);
}

.image-fallback {
  height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ink-3);
  background: var(--paper-2);
  border-radius: var(--radius-md);
  font-size: 13px;
}

.actions {
  display: flex;
  gap: 36px;
  margin-top: 10px;
}

.action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: none;
  padding: 4px 0;
  color: var(--ink-3);
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s ease;
}

.action:hover {
  color: var(--accent);
}

.action.liked {
  color: var(--like);
}

.action.danger:hover {
  color: var(--like);
}

.pop {
  animation: pop 0.28s ease;
}

@keyframes pop {
  0% { transform: scale(1); }
  45% { transform: scale(1.35); }
  100% { transform: scale(1); }
}
</style>
