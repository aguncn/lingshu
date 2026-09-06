// 场景域（P9 scenario-templates）：顶部域分类条与建任务对话框共用同一份域清单。
// 数据源 GET /api/scenarios（后端按 SCENARIO_DOMAINS 固定序返回十二域，name 即展示名，
// preset 为装配摘要计数）。域清单由左栏冷启动编排装载；这里不做选中状态管理——
// 「点哪个域建任务」是瞬时动作，落在 ui.taskDialogDomain（新建对话框预选值）上。
import { defineStore } from 'pinia'

import { listScenarios } from '../api/scenarios'

export const useScenarioStore = defineStore('scenario', {
  state: () => ({
    domains: [], // [{ domain, name, task_template, preset:{skills,mcps,kbs,experts} }]
    loading: false,
    loaded: false,
  }),
  getters: {
    // domain 键 → 域条目（name/装配摘要）：细节栏/对话框把键翻译成可读名用
    byDomain(state) {
      const m = {}
      for (const d of state.domains) m[d.domain] = d
      return m
    },
  },
  actions: {
    // 键 → 展示名；清单未装载/键未知时原样返回键，不空白
    labelOf(key) {
      if (!key) return ''
      const d = this.byDomain[key]
      return d ? d.name : key
    },
    async ensureLoaded({ force = false } = {}) {
      if (this.loaded && !force) return
      this.loading = true
      try {
        this.domains = (await listScenarios()) || []
        this.loaded = true
      } catch {
        // 拉取失败给空态；不置已加载，顶部条/对话框会各自降级并允许重试
        this.domains = []
      } finally {
        this.loading = false
      }
    },
  },
})
