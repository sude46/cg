<script setup lang="ts">
import { computed } from 'vue'

/** 文字头像：用户名首字 + 由 id/名字派生的稳定底色，零外部图片依赖 */
const props = withDefaults(
  defineProps<{ name: string; size?: number; src?: string | null }>(),
  { size: 40, src: null },
)

const PALETTE = ['#c05b34', '#7a6c5d', '#4a6fa5', '#6d8b74', '#a26769', '#8a7ca8', '#5b7f8c']

const bg = computed(() => {
  let h = 0
  for (const ch of props.name || '?') h = (h * 31 + ch.charCodeAt(0)) % 997
  return PALETTE[h % PALETTE.length]
})

const initial = computed(() => (props.name || '?').slice(0, 1))
</script>

<template>
  <img v-if="src" class="avatar" :src="src" :alt="name" :style="{ width: size + 'px', height: size + 'px' }">
  <span
    v-else
    class="avatar initial"
    :style="{ width: size + 'px', height: size + 'px', background: bg, fontSize: size * 0.42 + 'px' }"
  >{{ initial }}</span
  >
</template>

<style scoped>
.avatar {
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}

.initial {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-family: var(--font-serif);
  font-weight: 600;
  user-select: none;
}
</style>
