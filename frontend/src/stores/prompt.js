// 提示词/任务预设（design D3）：顶部模板条消费 category=task-preset。
import { defineStore } from 'pinia'

import { listPrompts } from '../api/prompts'

export const usePromptStore = defineStore('prompt', {
  state: () => ({
    presets: [],
    loading: false,
    loaded: false,
    selectedId: null, // 顶部点选的一个模板 → 输入框「选中上下文」
  }),
  getters: {
    selectedPreset(state) {
      return state.presets.find((p) => p.id === state.selectedId) ?? null
    },
  },
  actions: {
    async fetchPresets({ force = false } = {}) {
      if (this.loaded && !force) return
      this.loading = true
      try {
        this.presets = await listPrompts({ category: 'task-preset' })
        this.loaded = true
      } catch {
        this.presets = [] // 失败降级空态，不阻塞会话区（spec R4）
      } finally {
        this.loading = false
      }
    },
    toggleSelect(id) {
      this.selectedId = this.selectedId === id ? null : id
    },
    clear() {
      this.selectedId = null
    },
  },
})
