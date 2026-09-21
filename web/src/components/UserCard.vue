<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { followUser, unfollowUser } from '@/api/follows'
import { useAuthStore } from '@/stores/auth'
import type { User } from '@/types'
import UserAvatar from './UserAvatar.vue'

const props = defineProps<{ user: User; following?: boolean }>()
const auth = useAuthStore()
const router = useRouter()

const isFollowing = ref(!!props.following)
const pending = ref(false)

async function toggleFollow() {
  if (pending.value) return
  pending.value = true
  const prev = isFollowing.value
  isFollowing.value = !prev
  try {
    if (prev) await unfollowUser(props.user.id)
    else await followUser(props.user.id)
  } catch (e) {
    isFollowing.value = prev
    ElMessage.error(e instanceof Error ? e.message : '操作失败')
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <div class="user-card" @click="router.push(`/user/${user.id}`)">
    <UserAvatar :name="user.username" :size="44" />
    <div class="meta">
      <div class="name">{{ user.username }}</div>
      <div class="bio text-2">{{ user.bio || '这个人很懒，什么都没写' }}</div>
    </div>
    <el-button
      v-if="auth.user?.id !== user.id"
      size="small"
      round
      :type="isFollowing ? 'default' : 'primary'"
      :plain="isFollowing"
      :loading="pending"
      @click.stop="toggleFollow"
    >
      {{ isFollowing ? '已关注' : '关注' }}
    </el-button>
  </div>
</template>

<style scoped>
.user-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 22px;
  border-bottom: 1px solid var(--line-soft);
  cursor: pointer;
  transition: background 0.16s;
}

.user-card:hover {
  background: var(--paper-2);
}

.meta {
  flex: 1;
  min-width: 0;
}

.name {
  font-weight: 600;
  font-size: 14.5px;
}

.bio {
  font-size: 12.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
