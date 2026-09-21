<template>
  <div class="auth-wrap">
    <div class="auth-brand">
      <div class="brand-mark serif">司厄</div>
      <p class="brand-sub">网文读者的树洞，作者的案头。</p>
    </div>
    <div class="auth-panel">
      <router-view />
    </div>
    <p class="auth-foot mono">SAYER · EVERY STORY DESERVES A TELLER</p>
  </div>
</template>

<style scoped>
.auth-wrap {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 28px;
  padding: 48px 20px;
  background:
    radial-gradient(1000px 500px at 20% 10%, rgba(192, 91, 52, 0.05), transparent 60%),
    var(--paper);
}

.auth-brand {
  text-align: center;
}

.brand-mark {
  font-size: 44px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--ink);
}

.brand-sub {
  margin: 10px 0 0;
  color: var(--ink-2);
  font-size: 14px;
  letter-spacing: 0.06em;
}

.auth-panel {
  width: 400px;
  max-width: 100%;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  padding: 28px 32px 32px;
}

.auth-foot {
  color: var(--ink-3);
  letter-spacing: 0.14em;
}
</style>
