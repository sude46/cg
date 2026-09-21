<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const tab = ref<'login' | 'register'>('login')
const loading = ref(false)

const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', email: '', password: '', confirm: '' })

async function onLogin() {
  if (!loginForm.username || !loginForm.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await auth.login(loginForm.username, loginForm.password)
    router.push('/')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '登录失败')
  } finally {
    loading.value = false
  }
}

async function onRegister() {
  const { username, email, password, confirm } = registerForm
  if (!username || !email || !password) {
    ElMessage.warning('请填写完整信息')
    return
  }
  if (password.length < 8 || password.length > 20 || !/[a-z]/.test(password) || !/[A-Z]/.test(password) || !/\d/.test(password)) {
    ElMessage.warning('密码需 8-20 位，且包含大小写字母和数字')
    return
  }
  if (password !== confirm) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }
  loading.value = true
  try {
    await auth.register({ username, email, password })
    ElMessage.success('注册成功，欢迎来到这里')
    router.push('/')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <div class="tabs">
      <button class="tab" :class="{ active: tab === 'login' }" @click="tab = 'login'">登录</button>
      <button class="tab" :class="{ active: tab === 'register' }" @click="tab = 'register'">注册</button>
    </div>

    <div v-if="tab === 'login'" class="form">
      <el-input v-model="loginForm.username" size="large" placeholder="用户名" />
      <el-input
        v-model="loginForm.password"
        size="large"
        type="password"
        placeholder="密码"
        show-password
        @keyup.enter="onLogin"
      />
      <el-button class="submit" type="primary" size="large" round :loading="loading" @click="onLogin">
        登录
      </el-button>
      
    </div>

    <div v-else class="form">
      <el-input v-model="registerForm.username" size="large" placeholder="用户名（4-50 字符）" />
      <el-input v-model="registerForm.email" size="large" placeholder="邮箱" />
      <el-input v-model="registerForm.password" size="large" type="password" placeholder="密码（8-20 位，含大小写和数字）" show-password />
      <el-input v-model="registerForm.confirm" size="large" type="password" placeholder="确认密码" show-password @keyup.enter="onRegister" />
      <el-button class="submit" type="primary" size="large" round :loading="loading" @click="onRegister">
        创建账号
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.tabs {
  display: flex;
  gap: 24px;
  margin-bottom: 22px;
  border-bottom: 1px solid var(--line-soft);
}

.tab {
  border: none;
  background: none;
  padding: 4px 2px 12px;
  font-size: 16px;
  font-family: var(--font-serif);
  color: var(--ink-3);
  cursor: pointer;
  position: relative;
}

.tab.active {
  color: var(--ink);
  font-weight: 700;
}

.tab.active::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 2px;
  background: var(--accent);
}

.form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.submit {
  margin-top: 6px;
  letter-spacing: 0.2em;
}

.hint {
  text-align: center;
  font-size: 11px;
  color: var(--ink-3);
  margin: 4px 0 0;
}
</style>
