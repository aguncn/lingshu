<script setup>
// 中部会话区（design D2 / spec R5、R6 + P8 agentscope-runtime）：纯会话主区。
// 会话为真会话：气泡来自 task store，用户/助手分列左右；助手气泡流式打字机渲染，
// 危险工具触发 confirm_request 时给「放行/拒绝」卡片（回执 POST /chat/decision）；
// 确认卡可来自本地 SSE 流，也可来自 /chat/status 采纳的后台 run（切走/刷新后返回的保活恢复点），
// 故独立于气泡渲染——历史未载入时确认卡仍须可见可操作。
// C3：无常驻右列文件树；头部「文件/时间线」按钮开同一右侧抽屉（FileTree bare / TimelinePanel），
// 时间线列本任务用户提问，点击定位滚动并高亮到对应气泡。
import { CaretBottom, Clock, Files } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import {
  metaOf,
  PERMISSION_MODE_META,
  PERMISSION_MODE_ORDER,
  PROVIDER_TYPE_META,
  TASK_TYPE_META,
} from '../../constants'
import { useModelStore } from '../../stores/model'
import { useRegistryStore } from '../../stores/registry'
import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import { useUiStore } from '../../stores/ui'
import EmptyState from '../common/EmptyState.vue'
import StatusTag from '../common/StatusTag.vue'
import { renderMd } from '../../utils/md'
import AssistantTrace from './AssistantTrace.vue'
import ChatSideDrawer from './ChatSideDrawer.vue'
import FileTree from './FileTree.vue'
import TimelinePanel from './TimelinePanel.vue'

const task = useTaskStore()
const space = useSpaceStore()
const reg = useRegistryStore()
const model = useModelStore()
const ui = useUiStore()

const activeTask = computed(() => task.activeTask)
const messages = computed(() => task.activeMessages)
const confirm = computed(() => task.confirm)
const confirming = ref(false) // 回执请求进行中（防双击）
const scroller = ref(null)

const taskTypeLabel = computed(() => metaOf(TASK_TYPE_META, activeTask.value?.task_type).label)

// —— 顶部任务行常驻控件（仅此一处常驻，去重个性设置/输入框）：挂载的运维专家 · 权限 · 模型 ——
// 权限/模型做成「彩色线框 + 下拉箭头」的就地切换控件并提示；运维专家仍是只读 tag。
// 模型 = 供应商级快捷切换：选中某供应商即绑定/换绑（model_name 清空 → 用其默认模型），
//       彩框颜色随供应商类型（openai 主色 / deepseek 成功色…）；未绑定时标危险色引导先绑。
const mountedExpertNames = computed(() =>
  (task.caps?.experts || [])
    .map((id) => reg.byExpertId[id]?.name || null)
    .filter(Boolean),
)
const permValue = computed(() => activeTask.value?.permission_mode || '')
const permMeta = computed(() => PERMISSION_MODE_META[permValue.value] || null)
const boundProvider = computed(() =>
  model.config ? model.providerById(model.config.provider_id) : null,
)
// 彩框类型：权限按模式（strict=危险 / limited=警告 / trusted=成功）；模型按供应商类型；未绑定用危险色
const modelPillType = computed(() =>
  boundProvider.value
    ? metaOf(PROVIDER_TYPE_META, boundProvider.value.type).type
    : model.config ? 'info' : 'danger',
)
const modelPillLabel = computed(() => {
  if (!model.config) return '未绑定模型'
  const p = boundProvider.value
  const m = model.config.model_name || p?.default_model || ''
  const base = p ? p.name : model.providersLoading ? '…' : '未知供应商'
  return m ? `${base} · ${m}` : base
})
const modelResolved = computed(() => !model.configLoading && !model.providersLoading)
onMounted(() => {
  reg.ensureLoaded() // 冷启动补拉一次，专家名/挂载 join 需要
})

// —— 权限：顶栏即时三档切换（PATCH 持久化；运行中的 run 不受影响，下次提问生效）——
async function switchPerm(v) {
  if (!activeTask.value || v === permValue.value) return
  try {
    await task.patchTask({ permission_mode: v })
    ElMessage.success(`已切换权限为「${PERMISSION_MODE_META[v].label}」模式，下次提问生效`)
  } catch { /* 拦截器已提示 */ }
}
// —— 模型：供应商级快捷切换（首个=绑定，后续=换绑到该供应商默认模型）——
// 运行中不换（配置在每次发送时读）；无供应商时命令走到设置抽屉去新建。
async function switchModel(pid) {
  if (pid === '__settings__') {
    ui.settingsOpen = true
    return
  }
  if (!activeTask.value || !task.activeTaskId) return
  if (Number(pid) === (model.config?.provider_id ?? null)) return
  if (task.busy) {
    ElMessage.info('当前会话运行中，结束或停止后再切换模型')
    return
  }
  const p = model.providerById(pid)
  if (!p) return
  try {
    await model.saveConfig(task.activeTaskId, { provider_id: pid, model_name: '' }, { quiet: true })
    ElMessage.success(`已切换模型：${p.name}${p.default_model ? ` · ${p.default_model}` : ''}`)
  } catch { /* 拦截器已提示 */ }
}

// —— C3：头部「文件 / 时间线」按钮 → 右侧抽屉；消息区不再常驻右列文件树 ——
const side = ref(null) // null | 'files' | 'timeline'
const sideOpen = computed({
  get: () => side.value !== null,
  set: (v) => {
    if (!v) side.value = null
  },
})
const sideTitle = computed(() => (side.value === 'files' ? '工作区文件' : '时间线'))

function openFiles() {
  if (!task.activeTaskId) return
  task.loadFiles(task.activeTaskId) // 打开即刷新，展示本轮新产物
  side.value = 'files'
}
function openTimeline() {
  if (task.activeTaskId) task.ensureHistory(task.activeTaskId) // 历史未载入先拉（用户问题来自权威气泡）
  side.value = 'timeline'
}

// —— session-trace-ui：当前任务的「已装配」计数（弱化标记）与挂载连接器 key（MCP 前缀匹配）——
// caps 与当前选中任务一一对应（selectTask 已 loadCaps），据此区分「已装配」与「已调用」。
const assembledMeta = computed(() => {
  const c = task.caps || {}
  return {
    skills: (c.skills || []).length,
    kbs: (c.kbs || []).length,
    mcps: (c.mcps || []).length,
  }
})
const mcpKeys = computed(() => (task.caps?.mcps || []).map((x) => String(x)))

// 换任务关闭侧抽屉（文件/时间线都跟随当前任务，切走即收，避免残留别的任务内容）
watch(() => task.activeTaskId, () => {
  side.value = null
})

// —— 时间线：当前任务「用户输入问题」气泡 → 点条定位滚动到对应气泡 ——
// 锚点取消息稳定标识：服务端消息用 m<id>；本地乐观气泡（尚未落库）按数组位置兜底。
function bubbleAnchor(m, i) {
  return m.id ? `m${m.id}` : `live-${i}`
}
const timelineItems = computed(() =>
  messages.value
    .map((m, i) => ({ anchor: bubbleAnchor(m, i), time: m.time, text: (m.content || '').trim() }))
    .filter((x) => x.text && x.text !== '…'), // 只列有实质内容的用户提问，跳过空/占位
)
function locateUserQuestion(item) {
  side.value = null // 收起抽屉，聚焦主区定位
  nextTick(() => {
    const row = scroller.value ? scroller.value.querySelector(`[data-anchor="${item.anchor}"]`) : null
    const target = (row && row.querySelector('.cp-bubble')) || row // 高亮气泡本体而非整行留白
    if (!target) return
    target.scrollIntoView({ block: 'center', behavior: 'smooth' })
    target.classList.remove('cp-flash')
    void target.offsetWidth // 重触发 CSS 动画（连点同一条也能再次高亮）
    target.classList.add('cp-flash')
  })
}

// 新气泡/流式文本/确认卡出现 → 滚到底。键覆盖：条数、末条长度、流式态、确认 id
const scrollKey = computed(() => {
  const arr = messages.value
  const last = arr[arr.length - 1]
  return [
    arr.length,
    last ? last.content.length : 0,
    task.streaming ? 1 : 0,
    task.confirm ? task.confirm.confirmId : '',
  ].join(':')
})
watch(scrollKey, async () => {
  await nextTick()
  const el = scroller.value
  if (el) el.scrollTop = el.scrollHeight
})

async function decide(allow) {
  confirming.value = true
  try {
    await task.decideConfirm(allow)
  } finally {
    confirming.value = false
  }
}
</script>

<template>
  <div class="cp">
    <!-- 未选中任务：整区空态引导 -->
    <EmptyState
      v-if="!activeTask"
      class="cp-nothing"
      description="从左侧选择一个任务开始"
      tip="任务的工作文件、模型绑定与会话上下文将随选中任务在此呈现"
    />

    <template v-else>
      <div class="cp-context">
        <span class="cp-context-space text-dim">{{ activeTask ? (space.byId[activeTask.space_id]?.name || '空间') : '' }}</span>
        <span class="cp-context-title ellipsis">{{ activeTask.title }}</span>
        <StatusTag :value="activeTask.status" />
        <span class="cp-context-type text-dim">{{ taskTypeLabel }}</span>

        <!-- 常驻控件：挂载的运维专家(tag) · 权限(彩框下拉) · 模型(彩框下拉)，仅此一处常驻 -->
        <div class="cp-info">
          <el-tag
            v-for="n in mountedExpertNames"
            :key="n"
            size="small"
            type="primary"
            effect="plain"
            class="cp-chip"
          ><span class="cp-chip-dot" />{{ n }}</el-tag>

          <!-- 权限：彩色线框随模式；下拉直接三档切换 + 提示 -->
          <el-dropdown v-if="permMeta" trigger="click" popper-class="cp-dd" @command="switchPerm">
            <button
              type="button"
              class="cf-box"
              :class="`cf-${permMeta.type}`"
              :title="`权限模式：${permMeta.label}（点击下拉切换）`"
            >
              <span class="cf-label">权限</span>
              <span class="cf-val ellipsis">{{ permMeta.label }}</span>
              <el-icon class="cf-caret"><CaretBottom /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="m in PERMISSION_MODE_ORDER"
                  :key="m"
                  :command="m"
                >
                  <span class="cf-dot" :class="`cf-${PERMISSION_MODE_META[m].type}`" />
                  <span class="cf-item">{{ PERMISSION_MODE_META[m].label }}</span>
                  <span v-if="m === permValue" class="cf-check">✓</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <!-- 模型：彩色线框随供应商类型；下拉 = 各模型供应商，选中即绑定/换绑其默认模型 -->
          <el-dropdown trigger="click" :disabled="!modelResolved" popper-class="cp-dd" @command="switchModel">
            <button
              type="button"
              class="cf-box"
              :class="model.config ? `cf-${modelPillType}` : 'cf-danger cf-unbound'"
              :title="model.config ? '已绑模型（点击下拉切换供应商）' : '未绑定模型（点击下拉选择模型供应商）'"
            >
              <span class="cf-label">模型</span>
              <span class="cf-val ellipsis">{{ model.config ? modelPillLabel : (modelResolved ? '未绑定模型' : '…') }}</span>
              <el-icon class="cf-caret"><CaretBottom /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="p in model.providers"
                  :key="p.id"
                  :command="p.id"
                  :disabled="Number(p.id) === Number(model.config?.provider_id)"
                >
                  <span class="cf-dot" :class="`cf-${metaOf(PROVIDER_TYPE_META, p.type).type}`" />
                  <span class="cf-item">{{ p.name }}<template v-if="p.default_model"> · {{ p.default_model }}</template></span>
                  <span v-if="Number(p.id) === Number(model.config?.provider_id)" class="cf-check">✓</span>
                </el-dropdown-item>
                <el-dropdown-item v-if="!model.providers.length" command="__settings__">
                  尚无模型供应商，去「设置」添加…
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="cp-actions">
          <el-tooltip content="本任务工作区生成的文件（抽屉展示/预览）" placement="bottom">
            <button type="button" class="cp-action-btn" @click="openFiles">
              <el-icon><Files /></el-icon>
              <span>文件</span>
            </button>
          </el-tooltip>
          <el-tooltip content="本任务输入问题的时间线，点击定位到聊天对应位置" placement="bottom">
            <button type="button" class="cp-action-btn" @click="openTimeline">
              <el-icon><Clock /></el-icon>
              <span>时间线</span>
            </button>
          </el-tooltip>
        </div>
      </div>

      <div class="cp-body">
        <!-- 主区：会话（无常驻右列文件树；文件/时间线改头部按钮开抽屉 C3） -->
        <div class="cp-main">
          <div ref="scroller" class="cp-scroll">
            <div class="cp-msgs">
              <!-- 确认卡独立于气泡渲染：远程恢复（刷新/切回）时可能历史尚未载入，确认卡仍须可见 -->
              <EmptyState
                v-if="!messages.length && !confirm"
                description="还没有会话内容"
                tip="在下方输入首条消息开始对话 —— 未绑定模型时用顶栏「模型」下拉选一个模型供应商即可（密钥在左下角「设置 → 模型供应商」维护，仅掩码回显）"
              />

              <template v-if="messages.length">
                <div
                  v-for="(m, i) in messages"
                  :key="m.id || `live-${i}`"
                  class="cp-msg"
                  :class="m.role"
                  :data-anchor="bubbleAnchor(m, i)"
                >
                  <div class="cp-bubble" :class="{ 'is-error': m.error }">
                    <!-- 助手回复：顶部独立成行的调用摘要（内嵌可展开过程），正文在下方不粘连 -->
                    <AssistantTrace
                      v-if="m.role === 'assistant' && !m.error"
                      :bubble="m"
                      :assembled="assembledMeta"
                      :mcp-keys="mcpKeys"
                    />
                    <!-- 助手正文：Markdown 渲染成富文本（标题/加粗/列表/代码/引用有排版）；
                         用户气泡与报错气泡保持纯文本原样（v-html 注入故 md-body 样式走 :deep） -->
                    <div
                      v-if="m.role === 'assistant' && !m.error && m.content"
                      class="cp-bubble-text md-body"
                      v-html="renderMd(m.content)"
                    />
                    <div v-else-if="m.content" class="cp-bubble-text">{{ m.content }}</div>
                    <!-- 助手正文尚未产出首段文本：动态 "…" 进行态（思考/回复/执行中） -->
                    <div
                      v-else-if="m.live && m.role === 'assistant' && !m.error"
                      class="cp-dots"
                      aria-hidden="true"
                    ><i></i><i></i><i></i></div>
                  </div>
                  <div class="cp-msg-meta text-dim">
                    <span v-if="m.time">{{ m.time }}</span>
                    <template v-if="m.role === 'assistant'">
                      <template v-if="m.model"><span> · {{ m.model }}</span></template>
                      <span v-if="m.error"> · 运行失败</span>
                    </template>
                    <span v-else-if="m.live"> · 已发出</span>
                  </div>
                </div>
              </template>

              <!-- 危险工具二次确认卡片：危险写/执行类工具需用户回执才能续跑 -->
              <div v-if="confirm" class="cp-confirm">
                <div class="cp-confirm-head">
                  <el-tag size="small" type="warning" effect="plain">需要确认</el-tag>
                  <span class="cp-confirm-name ellipsis">{{ confirm.name }}</span>
                </div>
                <div class="cp-confirm-action text-dim">{{ confirm.action }}</div>
                <div class="cp-confirm-reason text-dim">{{ confirm.reason }}</div>
                <div class="cp-confirm-btns">
                  <el-button size="small" type="danger" plain :loading="confirming" @click="decide(false)">拒绝</el-button>
                  <el-button size="small" type="primary" :loading="confirming" @click="decide(true)">放行</el-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- C3 右侧抽屉：文件 / 时间线共用一抽屉，内容按 side 切换 -->
      <ChatSideDrawer v-model="sideOpen" :title="sideTitle">
        <FileTree v-if="side === 'files'" bare />
        <TimelinePanel v-else :items="timelineItems" @locate="locateUserQuestion" />
      </ChatSideDrawer>
    </template>
  </div>
</template>

<style scoped>
.cp {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.cp-nothing {
  margin: auto;
}
.cp-context {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 16px;
  border-bottom: 1px solid var(--ls-border);
  background: var(--ls-panel);
  min-width: 0;
}
.cp-context-space {
  flex: none;
  font-size: 12px;
}
.cp-context-title {
  font-size: 14px;
  font-weight: 600;
  max-width: 300px;
}
.cp-context-type {
  font-size: 12px;
  flex: none;
}
/* 顶部常驻信息标签组：单行不换行，超出裁剪（专家名由 cp-actions 左侧起挤占剩余） */
.cp-info {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-right: 4px;
  min-width: 0;
  flex: none;
  overflow: hidden;
}
.cp-chip {
  flex: none;
}
.cp-chip-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 5px;
  border-radius: 50%;
  background: var(--ls-accent);
  vertical-align: 1px;
}
/* 顶栏 权限/模型 彩框下拉：像一枚可点开的小选择器（边框/文字/浅底同色，随类型变） */
.cf-box {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: none;
  max-width: 250px;
  height: 24px;
  padding: 0 8px;
  border: 1px solid var(--ls-border);
  border-radius: 6px;
  background: transparent;
  font-size: 12px;
  cursor: pointer;
  transition: filter 0.15s;
}
.cf-box:hover { filter: brightness(1.08); }
.cf-label { flex: none; opacity: 0.72; }
.cf-val { flex: 1 1 auto; min-width: 0; white-space: nowrap; }
.cf-caret { flex: none; font-size: 11px; opacity: 0.8; }
.cf-danger { border-color: var(--el-color-danger); color: var(--el-color-danger); background: var(--el-color-danger-light-9); }
.cf-warning { border-color: var(--el-color-warning); color: var(--el-color-warning); background: var(--el-color-warning-light-9); }
.cf-success { border-color: var(--el-color-success); color: var(--el-color-success); background: var(--el-color-success-light-9); }
.cf-primary { border-color: var(--el-color-primary); color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.cf-info { border-color: var(--el-color-info); color: var(--el-color-info); background: var(--el-color-info-light-9); }
/* 未绑定模型：虚线框警示，提示先去下拉里选供应商 */
.cf-unbound { border-style: dashed; }
.cp-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
  flex: none;
}
.cp-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 10px;
  border: 1px solid var(--ls-border);
  border-radius: 6px;
  background: var(--ls-bg);
  color: var(--ls-fg-dim);
  font-size: 12px;
  cursor: pointer;
}
.cp-action-btn:hover {
  color: var(--ls-accent);
  border-color: var(--ls-accent);
}
.cp-action-btn .el-icon {
  font-size: 14px;
}
.cp-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  min-width: 0;
}
.cp-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.cp-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}
/* C4.1 正式聊天区宽度：去掉窄中列（860px 居中）→ 消息区占满聊天面板，
   助手回复几乎全宽排版、用户输入靠右，两者「错落」区分身份 */
.cp-msgs {
  width: 100%;
  min-width: 0;
}
.cp-msg {
  display: flex;
  flex-direction: column;
  margin-bottom: 12px;
}
.cp-msg.user {
  align-items: flex-end;
}
.cp-bubble {
  max-width: 94%;
  padding: 9px 13px;
  border-radius: 10px;
  font-size: var(--ls-font-size-msg); /* 会话正文字号令牌（默认较改动前小一档，明暗一致） */
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--ls-panel);
  border: 1px solid var(--ls-border);
}
.cp-msg.user .cp-bubble {
  background: var(--ls-accent);
  border-color: var(--ls-accent);
  color: #fff;
  border-bottom-right-radius: 2px;
  /* 用户输入靠右、宽上限收窄，与几乎全宽的助手回复形成「错落」区分 */
  max-width: 86%;
}
/* 失败/错误类助手气泡：警示描边，与正常回答区分（如模型不可用、运行异常） */
.cp-bubble.is-error {
  border-color: #f56c6c;
  color: #f56c6c;
  background: rgba(245, 108, 108, 0.06);
}
/* —— Markdown 正文排版（模型回复渲染后的观感：更大字号、分级标题、彩色代码/引用、缩进列表）——
   md-body 由 v-html 注入，子元素不带 scope 属性，故用 :deep 命中；配色走主题变量明暗自适应。
   空行分段交由 md（breaks:false），故在此把气泡的 pre-wrap 关掉，段落间距由下面显式控制。 */
.cp-bubble .md-body {
  font-size: 13px;
  line-height: 1.75;
  color: var(--ls-fg);
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
}
.cp-bubble .md-body :deep(:first-child) {
  margin-top: 0;
}
.cp-bubble .md-body :deep(:last-child) {
  margin-bottom: 0;
}
.cp-bubble .md-body :deep(p) {
  margin: 6px 0;
}
/* 分级标题：级别越大越醒目，用主题高亮色（明暗均清晰），弱化级标题回归正文色 */
.cp-bubble .md-body :deep(h1),
.cp-bubble .md-body :deep(h2) {
  color: var(--ls-accent);
  font-weight: 700;
  line-height: 1.35;
  margin: 14px 0 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--ls-border);
}
.cp-bubble .md-body :deep(h3) {
  color: var(--ls-fg);
  font-weight: 700;
  margin: 12px 0 6px;
}
.cp-bubble .md-body :deep(h4),
.cp-bubble .md-body :deep(h5),
.cp-bubble .md-body :deep(h6) {
  color: var(--ls-fg-dim);
  font-weight: 700;
  margin: 10px 0 6px;
}
.cp-bubble .md-body :deep(h1) {
  font-size: 19px;
}
.cp-bubble .md-body :deep(h2) {
  font-size: 16.5px;
}
.cp-bubble .md-body :deep(h3) {
  font-size: 14.5px;
}
.cp-bubble .md-body :deep(h4) {
  font-size: 13.5px;
}
.cp-bubble .md-body :deep(h5),
.cp-bubble .md-body :deep(h6) {
  font-size: 13px;
}
.cp-bubble .md-body :deep(strong) {
  font-weight: 700;
}
.cp-bubble .md-body :deep(em) {
  font-style: italic;
}
.cp-bubble .md-body :deep(del) {
  color: var(--ls-fg-dim);
}
/* 列表/嵌套缩进 */
.cp-bubble .md-body :deep(ul),
.cp-bubble .md-body :deep(ol) {
  margin: 6px 0;
  padding-left: 22px;
}
.cp-bubble .md-body :deep(li) {
  margin: 3px 0;
}
.cp-bubble .md-body :deep(li > ul),
.cp-bubble .md-body :deep(li > ol) {
  margin: 2px 0;
}
/* 行内代码：底色轻染 + 圆角；代码块统一在 pre 规则里整块处理 */
.cp-bubble .md-body :deep(code) {
  font-family: 'JetBrains Mono', 'Consolas', 'Menlo', monospace;
  font-size: 0.9em;
  background: rgba(127, 143, 166, 0.14);
  color: var(--ls-fg);
  padding: 1px 5px;
  border-radius: 4px;
}
.cp-bubble .md-body :deep(pre) {
  margin: 8px 0;
  padding: 10px 12px;
  border: 1px solid var(--ls-border);
  border-radius: 8px;
  background: rgba(127, 143, 166, 0.08);
  overflow-x: auto;
  line-height: 1.6;
}
.cp-bubble .md-body :deep(pre code) {
  background: transparent;
  border: none;
  padding: 0;
  font-size: 0.9em;
}
/* 引用：主题高亮竖条 + 弱化正文色，块级代码里不许透出行内样式 */
.cp-bubble .md-body :deep(blockquote) {
  margin: 8px 0;
  padding: 2px 0 2px 12px;
  border-left: 3px solid var(--ls-accent);
  color: var(--ls-fg-dim);
}
.cp-bubble .md-body :deep(blockquote p) {
  margin: 4px 0;
}
.cp-bubble .md-body :deep(a) {
  color: var(--ls-accent);
  text-decoration: none;
}
.cp-bubble .md-body :deep(a:hover) {
  text-decoration: underline;
}
/* 表格：描边对齐，表头轻染高亮 */
.cp-bubble .md-body :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
  max-width: 100%;
}
.cp-bubble .md-body :deep(th),
.cp-bubble .md-body :deep(td) {
  border: 1px solid var(--ls-border);
  padding: 5px 10px;
  text-align: left;
}
.cp-bubble .md-body :deep(th) {
  background: rgba(63, 126, 247, 0.08);
  font-weight: 600;
  white-space: nowrap;
}
.cp-bubble .md-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--ls-border);
  margin: 12px 0;
}
.cp-bubble .md-body :deep(img) {
  max-width: 100%;
  border-radius: 6px;
}
/* 动态 "…" 进行态：助手正文未产出首段文本时的思考/回复占位 */
.cp-dots {
  display: inline-flex;
  gap: 3px;
  align-items: baseline;
  min-height: 1em;
  padding: 2px 0;
}
.cp-dots i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--ls-fg-dim);
  animation: cp-dot 1.2s ease-in-out infinite;
}
.cp-dots i:nth-child(2) {
  animation-delay: 0.2s;
}
.cp-dots i:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes cp-dot {
  0%,
  80%,
  100% {
    opacity: 0.25;
    transform: translateY(0);
  }
  40% {
    opacity: 1;
    transform: translateY(-2px);
  }
}
.cp-msg-meta {
  margin-top: 3px;
  font-size: 11px;
}
/* 二次确认卡片：卡在气泡流末尾，左对齐强调「待你操作」 */
.cp-confirm {
  max-width: 94%;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid #e6a23c;
  background: rgba(230, 162, 60, 0.06);
  margin-bottom: 12px;
}
.cp-confirm-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.cp-confirm-name {
  font-weight: 600;
  font-size: 13px;
  min-width: 0;
}
.cp-confirm-action {
  font-size: 12px;
  word-break: break-all;
  margin-bottom: 4px;
}
.cp-confirm-reason {
  font-size: 12px;
  margin-bottom: 8px;
}
.cp-confirm-btns {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
/* 时间线定位：气泡短暂外发光高亮（连点同一条会重触发动画） */
.cp-flash {
  animation: cp-flash-row 1.6s ease;
}
@keyframes cp-flash-row {
  0% {
    box-shadow: 0 0 0 5px rgba(63, 126, 247, 0.35);
  }
  100% {
    box-shadow: 0 0 0 5px rgba(63, 126, 247, 0);
  }
}
</style>

<style>
/* 顶栏权限/模型下拉菜单 teleport 到 body，scoped 到不了 → 走 popper-class（.cp-dd）全局样式 */
.cp-dd .el-dropdown-menu__item {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  min-width: 168px;
}
.cp-dd .cf-dot {
  display: inline-block;
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.cp-dd .cf-danger { background: var(--el-color-danger); }
.cp-dd .cf-warning { background: var(--el-color-warning); }
.cp-dd .cf-success { background: var(--el-color-success); }
.cp-dd .cf-primary { background: var(--el-color-primary); }
.cp-dd .cf-info { background: var(--el-color-info); }
.cp-dd .cf-item { white-space: nowrap; }
.cp-dd .cf-check {
  margin-left: auto;
  color: var(--ls-accent);
  font-weight: 700;
}
.cp-dd .el-dropdown-menu__item.is-disabled .cf-item {
  color: var(--el-text-color-placeholder);
}
</style>
