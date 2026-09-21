<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
import { getHotSearches } from '@/api/posts'

const router = useRouter()
const { data } = useQuery({ queryKey: ['hot-searches'], queryFn: () => getHotSearches(8) })
</script>

<template>
  <section class="hot">
    <h3 class="title">书友热议</h3>
    <ol class="list">
      <li
        v-for="h in data || []"
        :key="h.rank"
        class="item"
        @click="router.push({ path: '/search', query: { q: h.keyword } })"
      >
        <span class="rank mono" :class="{ top: h.rank <= 3 }">{{ String(h.rank).padStart(2, '0') }}</span>
        <span class="kw">{{ h.keyword }}</span>
        <span v-if="h.heat" class="heat mono text-3">{{ (h.heat / 10000).toFixed(1) }}w</span>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.hot {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  padding: 16px 18px 8px;
  box-shadow: var(--shadow-sm);
}

.title {
  margin: 0 0 8px;
  font-family: var(--font-serif);
  font-size: 15px;
  letter-spacing: 0.08em;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.item {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 8px 0;
  font-size: 13.5px;
  cursor: pointer;
  border-top: 1px solid var(--line-soft);
}

.item:first-child {
  border-top: none;
}

.item:hover .kw {
  color: var(--accent);
}

.rank {
  font-size: 11px;
  color: var(--ink-3);
}

.rank.top {
  color: var(--accent);
  font-weight: 700;
}

.kw {
  flex: 1;
  transition: color 0.15s;
}

.heat {
  font-size: 11px;
}
</style>
