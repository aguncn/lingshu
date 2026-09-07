// 模型（design D3/D8）：供应商 CRUD（设置抽屉「模型供应商」区）+ 当前任务 ModelConfig 绑定。
// 供应商密钥只出掩码（****+末4位）；create/update 提交明文、回读仅掩码，任何出口不下行明文。
// GET 未绑定(404)属预期态 → 静默置 null；绑定/调参失败由 http 拦截器弹错并上抛。
import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import { bindTaskModel, getTaskModelConfig, patchTaskModel } from '../api/modelConfig'
import {
  createProvider as apiCreateProvider,
  deleteProvider as apiDeleteProvider,
  listProviders,
  updateProvider as apiUpdateProvider,
} from '../api/modelProviders'

export const useModelStore = defineStore('model', {
  state: () => ({
    providers: [],
    providersLoading: false,
    providersLoaded: false,
    config: null, // 当前任务 ModelConfig；null=未绑定
    configLoading: false,
    saving: false,
  }),
  getters: {
    providerById: (state) => (id) =>
      state.providers.find((p) => p.id === Number(id)) ?? null,
  },
  actions: {
    async fetchProviders({ force = false } = {}) {
      if (this.providersLoaded && !force) return
      this.providersLoading = true
      try {
        this.providers = await listProviders()
        this.providersLoaded = true
      } catch {
        this.providers = []
      } finally {
        this.providersLoading = false
      }
    },
    // —— 供应商 CRUD（设置抽屉模型区）：改完 force 重拉，让细节栏供应商下拉/已绑信息同步 ——
    async createProvider(data) {
      const row = await apiCreateProvider(data)
      await this.fetchProviders({ force: true })
      return row
    },
    async updateProvider(id, data) {
      const row = await apiUpdateProvider(id, data)
      await this.fetchProviders({ force: true })
      return row
    },
    async removeProvider(id) {
      await apiDeleteProvider(id)
      await this.fetchProviders({ force: true })
    },
    // 读当前任务绑定；404(未绑定)静默，网络类失败也只当未绑定处理
    async loadConfig(taskId) {
      if (!taskId) {
        this.config = null
        return
      }
      this.configLoading = true
      try {
        this.config = await getTaskModelConfig(taskId)
      } catch {
        this.config = null
      } finally {
        this.configLoading = false
      }
    },
    // 保存：未绑定走 POST（首次 201/替换 200），已绑定走 PATCH 调参/换供应商。
    // opts.quiet=true 时由调用方自弹更精确的提示（如顶栏「已切换模型：…」），避免双 toast。
    async saveConfig(taskId, payload, opts = {}) {
      this.saving = true
      try {
        const saved = this.config
          ? await patchTaskModel(taskId, payload)
          : await bindTaskModel(taskId, payload)
        this.config = saved
        if (!opts.quiet) ElMessage.success('模型配置已保存')
        return saved
      } finally {
        this.saving = false
      }
    },
  },
})
