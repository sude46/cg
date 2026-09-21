<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useInfiniteQuery, useQuery } from '@tanstack/vue-query'
import { Search as SearchIcon } from '@element-plus/icons-vue'
import { getHotSearches, getSearchSuggestions, searchPosts } from '@/api/posts'
import { searchUsers } from '@/api/users'
import PostCard from '@/components/PostCard.vue'
import UserCard from '@/components/UserCard.vue'

const route = useRoute()
const router = useRouter()

const keyword = ref(String(route.query.q || ''))
const committed = ref(keyword.value)
const sort = ref<'relevance' | 'time' | 'hot'>('relevance')
const type = ref<'posts' | 'users'>('posts')

watch(
  () => route.query.q,
  (q) => {
    keyword.value = String(q || '')
    committed.value = keyword.value
  },
)

async function suggest(q: string, cb: (list: { value: string }[]) => void) {
  if (!q.trim()) return cb([])
  try {
    const items = await getSearchSuggestions(q.trim())
    cb(items.map((value) => ({ value })))
  } catch {
    cb([])
  }
}

function commit(q?: string) {
  const kw = (q ?? keyword.value).trim()
  if (!kw) return
  router.replace({ path: '/search', query: { q: kw } })
  committed.value = kw
}

const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading, refetch } = useInfiniteQuery({
  queryKey: ['search', committed, sort],
  queryFn: ({ pageParam }) =>
    searchPosts({ q: committed.value, page: pageParam, per_page: 10, sort: sort.value }),
  initialPageParam: 1,
  enabled: () => !!committed.value,
})

const { data: hot } = useQuery({ queryKey: ['hot-searches'], queryFn: () => getHotSearches(10) })

const {
  data: userPages,
  fetchNextPage: fetchMoreUsers,
  hasNextPage: hasMoreUsers,
  isFetchingNextPage: isFetchingMoreUsers,
  isLoading: isLoadingUsers,
} = useInfiniteQuery({
  queryKey: ['user-search', committed],
  queryFn: ({ pageParam }) => searchUsers({ q: committed.value, page: pageParam, per_page: 10 }),
  initialPageParam: 1,
  getNextPageParam: (last) => (last.pagination.has_next ? last.pagination.page + 1 : undefined),
  enabled: () => !!committed.value && type.value === 'users',
})
</script>

<template>
  <div>
    <header class="page-head">
      <el-autocomplete
        v-model="keyword"
        :fetch-suggestions="suggest"
        placeholder="搜书名、搜梗、搜同好"
        size="large"
        class="input"
        clearable
        @select="(item: { value: string }) => commit(item.value)"
        @keyup.enter="commit()"
      >
        <template #prefix><el-icon><SearchIcon /></el-icon></template>
      </el-autocomplete>
    </header>

    <!-- 未搜索：热搜 -->
    <section v-if="!committed" class="landing">
      <h2 class="serif landing-title">此刻书友都在聊</h2>
      <div class="hot-list">
        <span v-for="h in hot || []" :key="h.rank" class="chip" @click="commit(h.keyword)">
          {{ h.keyword }}
        </span>
      </div>
    </section>

    <template v-else>
      <div class="type-bar">
        <button
          v-for="t in [
            { key: 'posts', label: '帖子' },
            { key: 'users', label: '用户' },
          ]"
          :key="t.key"
          class="sort"
          :class="{ active: type === t.key }"
          @click="type = t.key as typeof type"
        >
          {{ t.label }}
        </button>
      </div>

      <!-- 帖子结果 -->
      <template v-if="type === 'posts'">
        <div class="sort-bar">
          <button
            v-for="s in [
              { key: 'relevance', label: '综合' },
              { key: 'time', label: '最新' },
              { key: 'hot', label: '最热' },
            ]"
            :key="s.key"
            class="sort"
            :class="{ active: sort === s.key }"
            @click="sort = s.key as typeof sort"
          >
            {{ s.label }}
          </button>
          <span class="mono text-3 count">{{ data?.pages?.[0]?.pagination.total ?? 0 }} 条结果</span>
        </div>

        <el-skeleton v-if="isLoading" :rows="4" animated style="padding: 24px 22px" />

        <template v-else>
          <template v-for="page in data?.pages || []" :key="page.pagination.page">
            <PostCard v-for="p in page.items" :key="p.id" :post="p" @deleted="refetch()" />
          </template>
          <el-empty
            v-if="!data?.pages?.[0]?.items.length"
            :description="`没有找到与「${committed}」相关的内容`"
            :image-size="80"
          />
          <div v-if="hasNextPage" class="more">
            <el-button text size="small" :loading="isFetchingNextPage" @click="fetchNextPage()">
              加载更多
            </el-button>
          </div>
        </template>
      </template>

      <!-- 用户结果 -->
      <template v-else>
        <el-skeleton v-if="isLoadingUsers" :rows="3" animated style="padding: 24px 22px" />
        <template v-else>
          <template v-for="(page, idx) in userPages?.pages || []" :key="idx">
            <UserCard
              v-for="u in page.items"
              :key="u.id"
              :user="u"
              :following="!!u.is_following"
            />
          </template>
          <el-empty
            v-if="!userPages?.pages?.[0]?.items.length"
            :description="`没有找到与「${committed}」相关的用户`"
            :image-size="80"
          />
          <div v-if="hasMoreUsers" class="more">
            <el-button text size="small" :loading="isFetchingMoreUsers" @click="fetchMoreUsers()">
              加载更多
            </el-button>
          </div>
        </template>
      </template>
    </template>
  </div>
</template>

<style scoped>
.page-head {
  padding: 16px 22px;
  border-bottom: 1px solid var(--line-soft);
  position: sticky;
  top: 0;
  background: rgba(251, 251, 249, 0.92);
  backdrop-filter: blur(12px);
  z-index: 5;
}

.input {
  width: 100%;
}

.input :deep(.el-input__wrapper) {
  border-radius: 999px;
}

.landing {
  padding: 36px 26px;
}

.landing-title {
  margin: 0 0 18px;
  font-size: 20px;
  letter-spacing: 0.06em;
}

.hot-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.chip {
  padding: 7px 16px;
  border: 1px solid var(--line);
  border-radius: 999px;
  font-size: 13.5px;
  color: var(--ink-2);
  cursor: pointer;
  background: #fff;
  transition: border-color 0.15s, color 0.15s;
}

.chip:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.type-bar {
  display: flex;
  gap: 6px;
  padding: 10px 22px;
  border-bottom: 1px solid var(--line-soft);
}

.sort-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 22px;
  border-bottom: 1px solid var(--line-soft);
}

.sort {
  border: none;
  background: none;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 13.5px;
  color: var(--ink-2);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.sort.active {
  background: var(--accent-tint);
  color: var(--accent);
  font-weight: 600;
}

.count {
  margin-left: auto;
  font-size: 12px;
}

.more {
  text-align: center;
  padding: 14px;
}
</style>
