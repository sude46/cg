<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { updateProfile } from '@/api/users'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const profile = reactive({
  username: auth.user?.username || '',
  email: auth.user?.email || '',
  bio: auth.user?.bio || '',
  avatar_url: auth.user?.avatar_url || '',
})
const savingProfile = ref(false)

async function saveProfile() {
  savingProfile.value = true
  try {
    const payload: {
      username?: string
      email?: string
      bio?: string | null
      avatar_url?: string | null
    } = {
      bio: profile.bio || null,
      avatar_url: profile.avatar_url || null,
    }
    if (profile.username && profile.username !== auth.user?.username) {
      payload.username = profile.username
    }
    if (profile.email && profile.email !== auth.user?.email) {
      payload.email = profile.email
    }
    const res = await updateProfile(payload)
    if (res.user) auth.user = res.user
    ElMessage.success('资料已更新')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '更新失败')
  } finally {
    savingProfile.value = false
  }
}

const pwd = reactive({ old_password: '', new_password: '', confirm: '' })
const savingPwd = ref(false)

async function savePassword() {
  if (pwd.new_password !== pwd.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  savingPwd.value = true
  try {
    await auth.changePassword(pwd.old_password, pwd.new_password)
    // changePassword 内部会清空本地 token 并跳回登录页
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '修改失败')
  } finally {
    savingPwd.value = false
  }
}
</script>

<template>
  <div class="settings">
    <header class="page-head">
      <h1 class="serif">设置</h1>
    </header>

    <section class="card">
      <h2 class="card-title">个人资料</h2>
      <el-form label-position="top" class="form">
        <el-form-item label="用户名">
          <el-input v-model="profile.username" maxlength="50" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="profile.email" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="profile.bio" type="textarea" :rows="2" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="头像链接">
          <el-input v-model="profile.avatar_url" placeholder="https://…" />
        </el-form-item>
        <el-button type="primary" round :loading="savingProfile" @click="saveProfile">
          保存资料
        </el-button>
      </el-form>
    </section>

    <section class="card">
      <h2 class="card-title">修改密码</h2>
      <p class="hint text-3">改密后所有设备需重新登录。</p>
      <el-form label-position="top" class="form">
        <el-form-item label="原密码">
          <el-input v-model="pwd.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwd.new_password" type="password" show-password
                    placeholder="8-20 位，含大小写字母和数字" />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="pwd.confirm" type="password" show-password />
        </el-form-item>
        <el-button type="primary" round :loading="savingPwd" @click="savePassword">
          修改密码
        </el-button>
      </el-form>
    </section>
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

.card {
  padding: 18px 22px;
  border-bottom: 1px solid var(--line-soft);
}

.card-title {
  margin: 0 0 12px;
  font-size: 16px;
  letter-spacing: 0.04em;
}

.hint {
  margin: -4px 0 10px;
  font-size: 12px;
}

.form {
  max-width: 420px;
}
</style>
