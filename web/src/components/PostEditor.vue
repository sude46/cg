<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture } from '@element-plus/icons-vue'
import { createPost } from '@/api/posts'
import { uploadImage } from '@/api/uploads'
import { useAuthStore } from '@/stores/auth'
import UserAvatar from './UserAvatar.vue'

const visible = defineModel<boolean>({ default: false })
const emit = defineEmits<{ (e: 'published'): void }>()

const auth = useAuthStore()
const content = ref('')
const imageUrl = ref('')
const showImageInput = ref(false)
const publishing = ref(false)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const remaining = computed(() => 1000 - content.value.length)
const canPublish = computed(
  () =>
    content.value.trim().length > 0 &&
    remaining.value >= 0 &&
    !publishing.value &&
    !uploading.value,
)

function pickFile() {
  fileInput.value?.click()
}

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // 允许重复选择同一文件
  if (!file) return
  if (file.size > 5 * 1024 * 1024) {
    ElMessage.error('图片不能超过 5MB')
    return
  }
  uploading.value = true
  try {
    const res = await uploadImage(file)
    imageUrl.value = res.url
    showImageInput.value = true
    ElMessage.success('图片已上传')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '上传失败')
  } finally {
    uploading.value = false
  }
}

async function publish() {
  if (!canPublish.value) return
  publishing.value = true
  try {
    await createPost({ content: content.value.trim(), image_url: imageUrl.value.trim() || null })
    ElMessage.success('发布成功')
    content.value = ''
    imageUrl.value = ''
    showImageInput.value = false
    visible.value = false
    emit('published')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '发布失败')
  } finally {
    publishing.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" width="560px" :show-close="false" class="composer-dialog" align-center>
    <div class="composer">
      <UserAvatar :name="auth.user?.username || '?'" :size="42" />
      <div class="editor">
        <textarea
          v-model="content"
          class="textarea serif-input"
          placeholder="安利一本书、吐个槽、或者催个更…"
          rows="6"
          maxlength="1200"
          autofocus
        />

        <input
          ref="fileInput"
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          hidden
          @change="onFileChange"
        >

        <div v-if="showImageInput" class="image-row">
          <el-input
            v-model="imageUrl"
            placeholder="图片链接（也可点左侧按钮上传本地图片）"
            size="small"
            clearable
          />
          <img v-if="imageUrl" :src="imageUrl" class="image-preview" alt="预览">
        </div>

        <div class="toolbar">
          <el-tooltip :content="uploading ? '上传中…' : '上传图片'" placement="top">
            <button class="tool" :disabled="uploading" @click="pickFile">
              <el-icon :size="18"><Picture /></el-icon>
            </button>
          </el-tooltip>

          <div class="spacer" />
          <span class="counter mono" :class="{ over: remaining < 0 }">{{ remaining }}</span>
          <el-button type="primary" round :disabled="!canPublish" :loading="publishing" @click="publish">
            发布
          </el-button>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.composer {
  display: flex;
  gap: 12px;
}

.editor {
  flex: 1;
  min-width: 0;
}

.textarea {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  font-family: var(--font-sans);
  font-size: 16px;
  line-height: 1.75;
  color: var(--ink);
  background: transparent;
  padding: 6px 0;
}

.textarea::placeholder {
  color: var(--ink-3);
}

.image-row {
  margin: 6px 0 10px;
}

.image-preview {
  display: block;
  max-width: 100%;
  max-height: 180px;
  border-radius: 8px;
  margin-top: 8px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  border-top: 1px solid var(--line-soft);
  padding-top: 12px;
  margin-top: 4px;
}

.tool {
  border: none;
  background: none;
  color: var(--accent);
  cursor: pointer;
  padding: 6px;
  border-radius: 50%;
  transition: background 0.15s;
}

.tool:hover {
  background: var(--accent-tint);
}

.tool:disabled {
  opacity: 0.5;
  cursor: default;
}

.spacer {
  flex: 1;
}

.counter {
  font-size: 12px;
  color: var(--ink-3);
}

.counter.over {
  color: var(--like);
  font-weight: 600;
}
</style>

<style>
.composer-dialog .el-dialog__header {
  display: none;
}
.composer-dialog .el-dialog__body {
  padding: 24px;
}
</style>
