// 空间（design D3）：spaces 列表 + 选中空间过滤。任何失败置空态，不让单接口拖垮整页。
import { defineStore } from 'pinia'

import { createSpace as apiCreateSpace, listSpaces } from '../api/spaces'

export const useSpaceStore = defineStore('space', {
  state: () => ({
    spaces: [],
    activeSpaceId: null, // null = 全部空间
    loading: false,
    loaded: false,
  }),
  getters: {
    byId(state) {
      const m = {}
      for (const s of state.spaces) m[s.id] = s
      return m
    },
    activeSpace(state) {
      return state.activeSpaceId ? state.byId[state.activeSpaceId] ?? null : null
    },
  },
  actions: {
    // 拉空间列表；已加载则跳过，force=true 用于增删后重拉保一致（design D8）
    async fetchSpaces({ force = false } = {}) {
      if (this.loaded && !force) return
      this.loading = true
      try {
        this.spaces = await listSpaces()
        this.loaded = true
      } catch {
        this.spaces = [] // 拦截器已弹错，这里只保证空态不崩
      } finally {
        this.loading = false
      }
    },
    ensureLoaded() {
      return this.fetchSpaces()
    },
    selectSpace(id) {
      this.activeSpaceId = id
    },
    async createSpace(payload) {
      const sp = await apiCreateSpace(payload) // 失败向上抛（拦截器已提示）
      await this.fetchSpaces({ force: true }) // 成功后重拉：新空间出现在列表/分组头
      this.activeSpaceId = sp.id
      return sp
    },
  },
})
