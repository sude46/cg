<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useInfiniteQuery, useQuery } from '@tanstack/vue-query'
import { ElMessage } from 'element-plus'
import { listPosts } from '@/api/posts'
import { listUserFollowers, listUserFollowing, followUser, unfollowUser } from '@/api/follows'
import { getUserProfile } from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import PostCard from '@/components/PostCard.vue'
import UserCard from '@/components/UserCard.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import type { User } from '@/types'

const route = useRoute()
const auth = useAuthStore()
const userId = computed(() => Number(route.params.id))
const isSelf = computed(() => auth.user?.id === userId.value)
const tab = ref<'posts' | 'following' | 'followers'>('posts')

const { data: postsPage, fetchNextPage, hasNextPage, isFetchingNextPage, refetch } = useInfiniteQuery({
  queryKey: ['user-posts', userId],
  queryFn: ({ pageParam }) => listPosts({ page: pageParam, per_page: 10, user_id: userId.value }),
  initialPageParam: 1,
  getNextPageParam: (last) => (last.pagination.has_next ? last.pagination.page + 1 : undefined),
})

/* 公开资料：GET /users/<id>（登录态带 is_following/is_me） */
const { data: profile } = useQuery({
  queryKey: ['user-profile', userId],
  queryFn: () => getUserProfile(userId.value),
})

const profileUser = computed<Partial<User> | null>(() => {
  if (isSelf.value && auth.user) return auth.user
  return profile.value ?? null
})

const { data: followingData } = useQuery({
  queryKey: ['user-following', userId],
  queryFn: () => listUserFollowing(userId.value, { page: 1, per_page: 50 }),
  enabled: () => tab.value === 'following',
})

const { data: followerData } = useQuery({
  queryKey: ['user-followers', userId],
  queryFn: () => listUserFollowers(userId.value, { page: 1, per_page: 50 }),
  enabled: () => tab.value === 'followers',
})

const following = ref(false)
watch(
  profile,
  (p) => {
    if (p) following.value = !!p.is_following
  },
  { immediate: true },
)

async function toggleFollow() {
  const prev = following.value
  following.value = !prev
  try {
    if (prev) await unfollowUser(userId.value)
    else await followUser(userId.value)
  } catch (e) {
    following.value = prev
    ElMessage.error(e instanceof Error ? e.message : '操作失败')
  }
}
</script>

<template>
  <div>
    <header class="page-head">
      <h1 class="serif">{{ profileUser?.username || '主页' }}</h1>
    </header>

    <section class="profile-card">
      <div class="banner" />
      <div class="profile-body">
        <UserAvatar :name="profileUser?.username || '?'" :size="76" />
        <div class="profile-main">
          <h2 class="serif name">{{ profileUser?.username || '…' }}</h2>
          <p class="bio text-2">{{ profileUser?.bio || '这个人还没有签名' }}</p>
          <div class="stats mono text-3">
            <span><b>{{ profileUser?.post_count ?? '—' }}</b> 帖子</span>
            <span><b>{{ profileUser?.follower_count ?? '—' }}</b> 粉丝</span>
            <span><b>{{ profileUser?.following_count ?? '—' }}</b> 关注</span>
          </div>
        </div>
        <el-button
          v-if="!isSelf"
          round
          :type="following ? 'default' : 'primary'"
          :plain="following"
          @click="toggleFollow"
        >
          {{ following ? '已关注' : '关注' }}
        </el-button>
      </div>
    </section>

    <el-tabs v-model="tab" class="tabs">
      <el-tab-pane label="帖子" name="posts" />
      <el-tab-pane label="关注" name="following" />
      <el-tab-pane label="粉丝" name="followers" />
    </el-tabs>

    <div v-show="tab === 'posts'">
      <template v-for="page in postsPage?.pages || []" :key="page.pagination.page">
        <PostCard v-for="p in page.items" :key="p.id" :post="p" @deleted="refetch()" />
      </template>
      <el-empty
        v-if="!postsPage?.pages?.[0]?.items.length"
        description="还没有发布内容"
        :image-size="80"
      />
      <div v-if="hasNextPage" class="more">
        <el-button text size="small" :loading="isFetchingNextPage" @click="fetchNextPage()">
          加载更多
        </el-button>
      </div>
    </div>

    <div v-show="tab === 'following'">
      <UserCard v-for="u in followingData?.items || []" :key="u.id" :user="u" following />
      <el-empty v-if="!followingData?.items?.length" description="还没有关注任何人" :image-size="80" />
    </div>

    <div v-show="tab === 'followers'">
      <UserCard v-for="u in followerData?.items || []" :key="u.id" :user="u" />
      <el-empty v-if="!followerData?.items?.length" description="还没有粉丝" :image-size="80" />
    </div>
  </div>
</template>

<style scoped>
.page-head {
  padding: 18px 22px 12px;
  border-bottom: 1px solid var(--line-soft);
}

.page-head h1 {
  margin: 0;
  font-size: 20px;
  letter-spacing: 0.08em;
}

.profile-card {
  border-bottom: 1px solid var(--line-soft);
}

.banner {
  height: 110px;
  background:
    radial-gradient(600px 160px at 30% 120%, rgba(192, 91, 52, 0.16), transparent 70%),
    linear-gradient(180deg, var(--paper-3), var(--paper-2));
}

.profile-body {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  padding: 0 22px 18px;
}

.profile-body :deep(.avatar) {
  margin-top: -34px;
  border: 3px solid var(--paper);
}

.profile-main {
  flex: 1;
  min-width: 0;
  padding-top: 8px;
}

.name {
  margin: 0;
  font-size: 22px;
  letter-spacing: 0.04em;
}

.bio {
  margin: 6px 0 10px;
  font-size: 13.5px;
}

.stats {
  display: flex;
  gap: 18px;
  font-size: 12.5px;
}

.stats b {
  color: var(--ink);
  font-weight: 600;
}

.tabs {
  padding: 0 22px;
}

.more {
  text-align: center;
  padding: 14px;
}
</style>
