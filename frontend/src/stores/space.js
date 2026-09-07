// 空间（design D3）：spaces 列表 + 选中空间过滤。任何失败置空态，不让单接口拖垮整页。
import { defineStore } from 'pinia'

import {
  createSpace as apiCreateSpace,
  deleteSpace as apiDeleteSpace,
  listSpaces,
  updateSpace as apiUpdateSpace,
} from '../api/spaces'

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
    // 改名/改描述/改可见性：PATCH 返回权威 dict，就地合并避免整列闪烁
    async updateSpace(id, payload) {
      const updated = await apiUpdateSpace(id, payload) // 失败上抛（拦截器已提示）
      const idx = this.spaces.findIndex((s) => s.id === id)
      if (idx !== -1) this.spaces[idx] = { ...this.spaces[idx], ...updated }
      return updated
    },
    // 删除空间：DB 级联删其任务/挂载/消息/文件记录，磁盘目录由后端清理。
    // 前端需同步 task 缓存：经动态 import 调 task.dropSpace（避免与 task store 顶层互相引用的环）。
    async deleteSpace(id) {
      const sp = this.byId[id] ?? null
      await apiDeleteSpace(id) // 失败上抛（拦截器已提示）
      this.spaces = this.spaces.filter((s) => s.id !== id)
      if (this.activeSpaceId === id) this.activeSpaceId = null
      const { useTaskStore } = await import('./task')
      useTaskStore().dropSpace(id)
      return sp
    },
  },
})
