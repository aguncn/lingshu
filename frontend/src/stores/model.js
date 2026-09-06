// 模型绑定（design D3/D8）：供应商下拉 + 当前任务 ModelConfig。
// GET 未绑定(404)属预期态 → 静默置 null；绑定/调参失败由 http 拦截器弹错并上抛。
import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import { bindTaskModel, getTaskModelConfig, patchTaskModel } from '../api/modelConfig'
import { listProviders } from '../api/modelProviders'

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
    // 保存：未绑定走 POST（首次 201/替换 200），已绑定走 PATCH 调参/换供应商
    async saveConfig(taskId, payload) {
      this.saving = true
      try {
        const saved = this.config
          ? await patchTaskModel(taskId, payload)
          : await bindTaskModel(taskId, payload)
        this.config = saved
        ElMessage.success('模型配置已保存')
        return saved
      } finally {
        this.saving = false
      }
    },
  },
})
