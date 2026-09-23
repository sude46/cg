import { defineStore } from 'pinia'

/** 全局 UI 状态：未读数、发帖弹窗。接口数据不进这里（归 Vue Query 管）。 */
export const useUiStore = defineStore('ui', {
  state: () => ({
    unreadCount: 0, // 通知未读
    chatUnreadCount: 0, // 私信未读（与通知分开，语义不同）
    composerVisible: false,
  }),
  actions: {
    setUnread(n: number) {
      this.unreadCount = Math.max(0, n)
    },
    setChatUnread(n: number) {
      this.chatUnreadCount = Math.max(0, n)
    },
    openComposer() {
      this.composerVisible = true
    },
    closeComposer() {
      this.composerVisible = false
    },
  },
})
