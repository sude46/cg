import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getRefreshToken } from '@/api/http'

// hash 路由：静态部署/预览时子路由直接访问不会 404
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/login',
      component: () => import('@/layouts/AuthLayout.vue'),
      children: [{ path: '', name: 'login', component: () => import('@/views/Login.vue') }],
    },
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        { path: '', name: 'home', component: () => import('@/views/Home.vue') },
        { path: 'post/:id', name: 'post-detail', component: () => import('@/views/PostDetail.vue') },
        { path: 'user/:id', name: 'profile', component: () => import('@/views/Profile.vue') },
        { path: 'notifications', name: 'notifications', component: () => import('@/views/Notifications.vue') },
        { path: 'search', name: 'search', component: () => import('@/views/Search.vue') },
        { path: 'settings', name: 'settings', component: () => import('@/views/Settings.vue') },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.ready) await auth.tryRestore()
  if (to.name === 'login') {
    return auth.isLoggedIn ? { name: 'home' } : true
  }
  if (!auth.isLoggedIn && !getRefreshToken()) {
    return { name: 'login' }
  }
  return true
})

export default router
