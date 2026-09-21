<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { Bell, HomeFilled, Search, EditPen, User, SwitchButton, Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { useNotificationStream } from '@/composables/useNotificationStream'
import PostEditor from '@/components/PostEditor.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import HotSearches from '@/components/HotSearches.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const stream = useNotificationStream()

onMounted(() => {
  if (auth.user) stream.start()
})
watch(
  () => auth.user,
  (u) => (u ? stream.start() : stream.stop()),
)
onUnmounted(() => stream.stop())

const active = computed(() => {
  if (route.path === '/') return 'home'
  if (route.path.startsWith('/search')) return 'search'
  if (route.path.startsWith('/notifications')) return 'notifications'
  if (route.path.startsWith('/settings')) return 'settings'
  if (route.path.startsWith('/user/')) return 'me'
  return ''
})

const navs = [
  { key: 'home', label: '首页', icon: HomeFilled, to: '/' },
  { key: 'search', label: '搜索', icon: Search, to: '/search' },
  { key: 'notifications', label: '通知', icon: Bell, to: '/notifications' },
  { key: 'settings', label: '设置', icon: Setting, to: '/settings' },
]

function goMe() {
  if (auth.user) router.push(`/user/${auth.user.id}`)
}

async function onLogout() {
  await ElMessageBox.confirm('确定退出登录吗？', '退出', {
    confirmButtonText: '退出',
    cancelButtonText: '取消',
    type: 'warning',
  })
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="shell">
    <!-- 左栏：导航 -->
    <aside class="rail">
      <router-link to="/" class="brand serif">司厄</router-link>

      <nav class="nav">
        <router-link
          v-for="n in navs"
          :key="n.key"
          :to="n.to"
          class="nav-item"
          :class="{ active: active === n.key }"
        >
          <el-badge
            v-if="n.key === 'notifications'"
            :value="ui.unreadCount"
            :hidden="ui.unreadCount === 0"
            :max="99"
          >
            <el-icon :size="20"><component :is="n.icon" /></el-icon>
          </el-badge>
          <el-icon v-else :size="20"><component :is="n.icon" /></el-icon>
          <span>{{ n.label }}</span>
        </router-link>

        <a class="nav-item" :class="{ active: active === 'me' }" @click="goMe">
          <el-icon :size="20"><User /></el-icon>
          <span>我的</span>
        </a>
      </nav>

      <el-button class="compose-btn" type="primary" size="large" round @click="ui.openComposer()">
        <el-icon style="margin-right: 6px"><EditPen /></el-icon>发帖
      </el-button>

      <div v-if="auth.user" class="me-card">
        <UserAvatar :name="auth.user.username" :size="38" />
        <div class="me-meta">
          <div class="me-name">{{ auth.user.username }}</div>
          <div class="me-sub mono text-3">@{{ auth.user.id }}</div>
        </div>
        <el-tooltip content="退出登录" placement="top">
          <el-icon class="logout" :size="17" @click="onLogout"><SwitchButton /></el-icon>
        </el-tooltip>
      </div>
    </aside>

    <!-- 中栏：内容 -->
    <main class="main">
      <router-view />
    </main>

    <!-- 右栏：发现 -->
    <aside class="side">
      <div class="side-search" @click="router.push('/search')">
        <el-icon :size="15"><Search /></el-icon>
        <span>搜索帖子</span>
      </div>
      <HotSearches />
      <div class="side-foot mono text-3">SAYER · 讲故事的人都在这儿</div>
    </aside>

    <PostEditor v-model="ui.composerVisible" />
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 232px minmax(0, 640px) 300px;
  justify-content: center;
  gap: 32px;
  max-width: 1280px;
  margin: 0 auto;
  min-height: 100%;
}

/* 左栏 */
.rail {
  position: sticky;
  top: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  padding: 28px 12px 20px 0;
}

.brand {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 0.1em;
  padding: 4px 14px;
  margin-bottom: 22px;
  width: fit-content;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 11px 14px;
  border-radius: 999px;
  font-size: 15px;
  color: var(--ink-2);
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease;
  width: fit-content;
  min-width: 128px;
}

.nav-item:hover {
  background: var(--paper-2);
  color: var(--ink);
}

.nav-item.active {
  color: var(--ink);
  font-weight: 600;
}

.compose-btn {
  margin-top: 22px;
  width: 150px;
  font-size: 15px;
  letter-spacing: 0.1em;
}

.me-card {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  border: 1px solid var(--line);
  background: #fff;
  box-shadow: var(--shadow-sm);
}

.me-meta {
  flex: 1;
  min-width: 0;
}

.me-name {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.me-sub {
  font-size: 11px;
}

.logout {
  color: var(--ink-3);
  cursor: pointer;
  transition: color 0.16s;
}

.logout:hover {
  color: var(--accent);
}

/* 中栏 */
.main {
  border-left: 1px solid var(--line-soft);
  border-right: 1px solid var(--line-soft);
  min-height: 100vh;
  padding-bottom: 60px;
}

/* 右栏 */
.side {
  position: sticky;
  top: 0;
  height: 100vh;
  padding: 20px 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.side-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 16px;
  border-radius: 999px;
  background: var(--paper-2);
  border: 1px solid var(--line-soft);
  color: var(--ink-3);
  font-size: 14px;
  cursor: pointer;
  transition: border-color 0.16s;
}

.side-search:hover {
  border-color: var(--accent);
}

.side-foot {
  font-size: 11px;
  letter-spacing: 0.12em;
  padding-left: 6px;
}

@media (max-width: 1100px) {
  .shell {
    grid-template-columns: 88px minmax(0, 640px);
  }
  .side {
    display: none;
  }
  .nav-item span,
  .brand {
    display: none;
  }
  .nav-item {
    min-width: 0;
    padding: 11px;
  }
  .compose-btn {
    width: auto;
  }
}
</style>
