<script setup>
// 助手回复「独立成行摘要行 + 就地可展开过程」（session-trace-ui，spec workbench 场景一/二/四）。
// 只消费气泡上已归一化的 steps（live 与历史同构），摘要/分类集中在本组件与 utils/trace：
//   顶部一行紧凑呈现「真实已调用」聚合摘要 + 可展开「过程明细」入口；
//   「已装配（技能/知识库/MCP）」以弱化标记分开展示，绝不与「已调用」混同（spec 场景四）。
//   skill-kb-callable：技能/知识库可被调用后，弱化标记须「扣除本次已调用」才不为双计——被真实调用的
//   技能只出现在摘要「技能」桶（技能工具 1:1 对应技能，去重工具名数 = 已调用技能数）；知识库检索为
//   聚合工具，一次 knowledge_search 调用即视为该回合已用知识库能力、弱化标记收起（spec R 场景一二）。
// 展开态是组件本地 state（按气泡实例隔离）：切任务/历史刷新会重建组件 → 不残留上次展开态。
import { computed, ref } from 'vue'

import { summarizeSteps } from '../../utils/trace'

const props = defineProps({
  bubble: { type: Object, required: true }, // { steps:[{kind,name,args,decision?,text,ok,summary}], live }
  assembled: { type: Object, default: () => ({ skills: 0, kbs: 0, mcps: 0 }) }, // 任务已装配计数
  mcpKeys: { type: Array, default: () => [] }, // 已挂载连接器 key（MCP 工具名前缀匹配用）
})

const steps = computed(() => (props.bubble.steps || []))
const meta = computed(() => summarizeSteps(steps.value, { mcpKeys: props.mcpKeys }))
const hasThinking = computed(() => steps.value.some((s) => s && s.kind === 'thinking'))
// 有步骤才渲染追溯区（纯文本旧消息无步骤 → 整块不出现，向后兼容 spec 场景三）
const visible = computed(() => steps.value.length > 0)

// 弱化「已装配」标记口径 = 任务装配计数 − 本次回复真实已调用（不双计）：
//   - 技能：每个被调用的技能工具去重为一个已调用技能，从装配技能数中扣除；
//   - 知识库：knowledge_search 一旦被调用即视为本回合已用知识库能力 → 弱化标记收起；
//   - MCP：沿既有口径（MCP 一连接器多工具，装配计数不因单次调用扣减，保持稳定可读）。
const assembledText = computed(() => {
  const a = props.assembled
  const calledSkills = new Set()
  let kbCalled = false
  for (const g of meta.value.groups || []) {
    if (g.kind === 'skill') for (const n of g.names) calledSkills.add(n)
    if (g.kind === 'kb' && g.names.length) kbCalled = true
  }
  const parts = []
  const skillsLeft = Math.max(0, (a.skills || 0) - calledSkills.size)
  if (skillsLeft) parts.push(`技能×${skillsLeft}`)
  if (!kbCalled && a.kbs) parts.push(`RAG×${a.kbs}`)
  if (a.mcps) parts.push(`MCP×${a.mcps}`)
  return parts.join('·')
})

const expanded = ref(false)

function argsText(s) {
  if (s.args == null) return ''
  // 对象参数（服务端已解析）→ 紧凑 JSON；字符串（历史旧格式容错）原样
  if (typeof s.args === 'string') return s.args
  try {
    return JSON.stringify(s.args, null, 2)
  } catch {
    return String(s.args)
  }
}
</script>

<template>
  <div v-if="visible" class="at">
    <!-- 摘要行：独立一行，不与正文粘连 -->
    <div class="at-bar">
      <span class="at-summary">
        <template v-if="meta.has">{{ meta.text }}</template>
        <template v-else-if="hasThinking">思考过程</template>
      </span>
      <span v-if="assembledText" class="at-assembled" title="任务已装配但本次回复未调用这些能力">已装配 {{ assembledText }}</span>
      <button
        type="button"
        class="at-toggle"
        :class="{ open: expanded }"
        @click="expanded = !expanded"
      >{{ expanded ? '收起过程 ▴' : '查看过程 ▾' }}</button>
    </div>

    <!-- 就地展开的有序过程明细（thinking / 调用决策 / 结果成败） -->
    <ol v-if="expanded" class="at-steps">
      <li v-for="(s, i) in steps" :key="i" class="at-step" :class="s.kind">
        <template v-if="s.kind === 'thinking'">
          <span class="at-kind">思考</span>
          <p class="at-thinking">{{ s.text }}</p>
        </template>
        <template v-else-if="s.kind === 'tool_call'">
          <span class="at-kind">调用</span>
          <code class="at-name">{{ s.name || '?' }}</code>
          <span v-if="s.decision === 'allow'" class="at-decision allow">已放行</span>
          <span v-else-if="s.decision === 'deny'" class="at-decision deny">已拒绝</span>
          <pre v-if="argsText(s)" class="at-args">{{ argsText(s) }}</pre>
        </template>
        <template v-else-if="s.kind === 'tool_result'">
          <span class="at-kind">结果</span>
          <code class="at-name">{{ s.name || '?' }}</code>
          <span class="at-badge" :class="s.ok ? 'ok' : 'fail'">{{ s.ok ? '成功' : '失败' }}</span>
          <p v-if="s.summary" class="at-summary-text">{{ s.summary }}</p>
        </template>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.at {
  margin: -2px 0 6px; /* 收拢气泡内边距，摘要自成一行后与正文留出界线 */
  white-space: normal; /* 复位气泡 pre-wrap，避免模板换行空白的多余空格入摘要 */
}
.at-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  line-height: 1.5;
}
.at-summary {
  font-weight: 500;
  color: var(--ls-fg);
}
.at-assembled {
  color: var(--ls-fg-dim);
  font-size: 11px;
  opacity: 0.8;
}
.at-toggle {
  margin-left: auto;
  border: none;
  background: transparent;
  padding: 0;
  font-size: 11px;
  color: var(--ls-accent);
  cursor: pointer;
  flex: none;
  white-space: nowrap;
}
.at-toggle:hover {
  text-decoration: underline;
}
.at-steps {
  margin: 6px 0 0;
  padding: 8px 10px;
  list-style: none;
  border: 1px solid var(--ls-border);
  border-radius: 8px;
  background: rgba(127, 140, 160, 0.06);
  font-size: 12px;
  max-height: 280px;
  overflow: auto;
}
.at-step {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px;
  padding: 3px 0;
}
.at-step + .at-step {
  border-top: 1px dashed var(--ls-border);
}
.at-kind {
  flex: none;
  font-size: 11px;
  color: var(--ls-fg-dim);
  border: 1px solid var(--ls-border);
  border-radius: 4px;
  padding: 0 4px;
}
.at-name {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  color: var(--ls-accent);
}
.at-decision,
.at-badge {
  flex: none;
  font-size: 11px;
  border-radius: 4px;
  padding: 0 5px;
}
.at-decision.allow,
.at-badge.ok {
  color: #2e9e5b;
  background: rgba(46, 158, 91, 0.12);
}
.at-decision.deny,
.at-badge.fail {
  color: #f56c6c;
  background: rgba(245, 108, 108, 0.12);
}
.at-args {
  width: 100%;
  margin: 2px 0 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11px;
  color: var(--ls-fg-dim);
  background: rgba(0, 0, 0, 0.04);
  border-radius: 4px;
  padding: 4px 6px;
}
html.dark .at-args {
  background: rgba(255, 255, 255, 0.05);
}
.at-thinking,
.at-summary-text {
  width: 100%;
  margin: 1px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--ls-fg-dim);
  font-size: 12px;
}
</style>
