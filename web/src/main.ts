import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import { setAuthFailureHandler } from './api/http'
import { useAuthStore } from './stores/auth'
import './styles/tokens.css'
import './styles/main.css'

// mock 模式：仅开发/演示期使用，联调真实后端时把 VITE_USE_MOCK 置为 false
async function bootstrap() {
  if (import.meta.env.VITE_USE_MOCK === 'true') {
    const { setupMock } = await import('./api/mock')
    setupMock()
  }

  const app = createApp(App)
  const pinia = createPinia()
  app.use(pinia)
  // 认证失效（refresh 失败）时清空登录态，否则守卫会把 /login 弹回首页
  setAuthFailureHandler(() => {
    useAuthStore().user = null
  })
  app.use(VueQueryPlugin, {
    queryClientConfig: {
      defaultOptions: {
        queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
      },
    },
  })
  app.use(router)
  app.use(ElementPlus, { locale: zhCn })
  app.mount('#app')
}

bootstrap()
