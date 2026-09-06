<script setup>
// 顶部「场景域分类」快捷条（P9 scenario-templates，spec 验收：UI 顶部出现 12 个域分类）。
// 数据源 GET /api/scenarios（固定十二域序 + 装配摘要）；点击一个域 = 打开「新建任务」
// 并预选该域 → 建任务即自动套用该域预设（挂载 MCP/专家等，见 TaskCreateDialog）。
// 替换了早期 P3「常用任务/提示词模板」快捷条（其注入未落地，域条承担同类快速入口）。
// 接口失败降级为轻量空态并给重试，不阻塞会话区。
import { RefreshRight } from '@element-plus/icons-vue'
import { computed } from 'vue'

import { useScenarioStore } from '../../stores/scenario'
import { useUiStore } from '../../stores/ui'

const scenario = useScenarioStore()
const ui = useUiStore()

const ready = computed(() => scenario.loaded && scenario.domains.length > 0)
const failed = computed(() => scenario.loaded && !scenario.domains.length)

function reload() {
  scenario.ensureLoaded({ force: true })
}

// 装配摘要 → 工具提示里的短描述（例：「MCP 3 · 专家 1」；空域不显示）
function presetHint(d) {
  const p = d.preset || {}
  const parts = []
  if (p.skills) parts.push(`技能 ${p.skills}`)
  if (p.mcps) parts.push(`MCP ${p.mcps}`)
  if (p.kbs) parts.push(`知识库 ${p.kbs}`)
  if (p.experts) parts.push(`专家 ${p.experts}`)
  return parts.length ? `预设装配：${parts.join(' · ')}` : '预设为空，可手动挂载'
}
</script>

<template>
  <div class="tb">
    <span class="tb-label">场景域</span>

    <div v-loading="scenario.loading" class="tb-chips">
      <button
        v-for="d in scenario.domains"
        :key="d.domain"
        type="button"
        class="tb-chip"
        :class="{ active: ui.taskDialogOpen && ui.taskDialogDomain === d.domain }"
        :title="`${d.name}：${presetHint(d)}\n点击新建任务并套用该域预设`"
        @click="ui.openCreateTask(d.domain)"
      >
        {{ d.name }}
      </button>

      <span v-if="failed" class="tb-fallback text-dim">场景域暂不可用</span>
    </div>

    <div class="tb-side">
      <el-button v-if="failed" link :icon="RefreshRight" class="tb-retry" @click="reload">重试</el-button>
      <span v-else-if="ready" class="tb-hint text-dim">点场景域 → 建任务自动装配预设能力</span>
    </div>
  </div>
</template>

<style scoped>
.tb {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 42px;
  padding: 0 16px;
  border-bottom: 1px solid var(--ls-border);
  background: var(--ls-panel);
  min-width: 0;
}
.tb-label {
  flex: none;
  font-size: 12px;
  color: var(--ls-fg-dim);
  letter-spacing: 0.5px;
}
.tb-chips {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  overflow-x: auto; /* 十二域超宽时横向滚动，不换行挤高 */
  scrollbar-width: thin;
  scrollbar-color: var(--ls-border) transparent;
  padding-bottom: 1px;
}
.tb-chip {
  flex: none;
  padding: 3px 12px;
  border: 1px solid var(--ls-border);
  border-radius: 999px;
  background: transparent;
  color: var(--ls-fg);
  font-size: 12.5px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.tb-chip:hover {
  border-color: var(--ls-accent);
  color: var(--ls-accent);
}
.tb-chip.active {
  background: var(--ls-accent);
  border-color: var(--ls-accent);
  color: #fff;
}
.tb-fallback {
  font-size: 12px;
}
.tb-side {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  min-width: 0;
}
.tb-hint {
  font-size: 11px;
  white-space: nowrap;
}
.tb-retry {
  padding: 0;
}
</style>
