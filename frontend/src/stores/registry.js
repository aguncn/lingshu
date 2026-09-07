// 能力登记数据（P5 registry-center / C5）：技能/MCP/知识库/运维专家 四列表 + byId 名称索引。
// 能力广场各整页（技能/MCP/知识库/运维专家 center）+ 细节栏挂载 tile 用 byId 把 caps 的 id join 成可读行。
// 每类单独隔离失败（try/catch 置空），不让一个接口拖垮其余三类；loadCategory 供变更后局部刷新。
import { defineStore } from 'pinia'

import { listExperts } from '../api/experts'
import { listKbs } from '../api/kbs'
import { listMcps } from '../api/mcps'
import { listSkills } from '../api/skills'

const LOADERS = {
  skills: listSkills,
  mcps: listMcps,
  kbs: listKbs,
  experts: listExperts,
}

function indexById(list) {
  const m = {}
  for (const x of list) m[x.id] = x
  return m
}

export const useRegistryStore = defineStore('registry', {
  state: () => ({
    skills: [],
    mcps: [],
    kbs: [],
    experts: [],
    loaded: false,
    loading: false,
  }),
  getters: {
    bySkillId: (s) => indexById(s.skills),
    byMcpId: (s) => indexById(s.mcps),
    byKbId: (s) => indexById(s.kbs),
    byExpertId: (s) => indexById(s.experts),
  },
  actions: {
    // 冷启动懒加载一次；force 用于手动「刷新」保一致
    async ensureLoaded({ force = false } = {}) {
      if (this.loaded && !force) return
      this.loading = true
      try {
        const [skills, mcps, kbs, experts] = await Promise.all([
          listSkills(),
          listMcps(),
          listKbs(),
          listExperts(),
        ])
        this.skills = skills || []
        this.mcps = mcps || []
        this.kbs = kbs || []
        this.experts = experts || []
        this.loaded = true
      } catch {
        // 某一类失败时保留已成功的部分，未命中的置空，避免整页崩
        this.loaded = true
      } finally {
        this.loading = false
      }
    },
    // 变更单类后局部重拉：注册中心/挂载面板做完增删改即调用，列表立即一致
    async loadCategory(cat) {
      try {
        const loader = LOADERS[cat]
        const rows = await loader()
        this[cat] = rows || []
        this.loaded = true
      } catch {
        this[cat] = []
      }
    },
  },
})
