<script setup>
// 中部会话区（design D2 / spec R5、R6 + P8 agentscope-runtime）：会话主区 + 右侧文件树。
// 会话为真会话：气泡来自 task store，用户/助手分列左右；助手气泡流式打字机渲染，
// 危险工具触发 confirm_request 时在流末尾给「放行/拒绝」卡片（回执 POST /chat/decision）；
// 时间线仍为 ElTimeline 占位（spec R3 / task 4.3，审计/事件时间线接入另行排期）。
import { computed, nextTick, ref, watch } from 'vue'

import { metaOf, TASK_TYPE_META } from '../../constants'
import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import EmptyState from '../common/EmptyState.vue'
import StatusTag from '../common/StatusTag.vue'
import FileTree from './FileTree.vue'

const task = useTaskStore()
const space = useSpaceStore()

const activeTask = computed(() => task.activeTask)
const messages = computed(() => task.activeMessages)
const confirm = computed(() => task.confirm)
const confirming = ref(false) // 回执请求进行中（防双击）
const mode = ref('session') // 'session' | 'timeline'
const scroller = ref(null)

const taskTypeLabel = computed(() => metaOf(TASK_TYPE_META, activeTask.value?.task_type).label)

// 换任务默认回「会话」视图（消息按任务隔离，切走不残留别的任务内容）
watch(() => task.activeTaskId, () => {
  mode.value = 'session'
})

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

        <div class="cp-mode">
          <button
            type="button"
            class="cp-mode-btn"
            :class="{ active: mode === 'session' }"
            @click="mode = 'session'"
          >会话</button>
          <button
            type="button"
            class="cp-mode-btn"
            :class="{ active: mode === 'timeline' }"
            @click="mode = 'timeline'"
          >时间线</button>
        </div>
      </div>

      <div class="cp-body">
        <!-- 主区：会话 / 时间线 -->
        <div class="cp-main">
          <div v-if="mode === 'session'" ref="scroller" class="cp-scroll">
            <div class="cp-msgs">
              <EmptyState
                v-if="!messages.length"
                description="还没有会话内容"
                tip="在下方输入首条消息开始对话 —— 任务需在底部先绑定模型并填入 API Key（保存即 Fernet 加密，仅后端可见）"
              />

              <template v-else>
                <div
                  v-for="(m, i) in messages"
                  :key="m.id || `live-${i}`"
                  class="cp-msg"
                  :class="m.role"
                >
                  <div class="cp-bubble" :class="{ 'is-error': m.error }">
                    <template v-if="m.content">{{ m.content }}</template>
                    <span v-else-if="m.live" class="cp-pending">正在思考<span class="cp-caret" /></span>
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
              </template>
            </div>
          </div>

          <div v-else class="cp-timeline">
            <!-- 事件时间线（spec R3 / D7）：会话/审计事件接入后在 <el-timeline>
                内逐条展开，本期无事件 → 稳定占位，不报错 -->
            <EmptyState
              description="暂无事件记录"
              tip="任务事件（会话/审计）将在时间线接入后在此按时间展开"
            />
          </div>
        </div>

        <!-- 右栏：文件树 -->
        <aside class="cp-files">
          <FileTree />
        </aside>
      </div>
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
  max-width: 320px;
}
.cp-context-type {
  font-size: 12px;
  flex: none;
}
.cp-mode {
  margin-left: auto;
  display: flex;
  background: var(--ls-bg);
  border-radius: 6px;
  padding: 2px;
  flex: none;
}
.cp-mode-btn {
  border: none;
  background: transparent;
  padding: 4px 12px;
  font-size: 12px;
  border-radius: 4px;
  color: var(--ls-fg-dim);
  cursor: pointer;
}
.cp-mode-btn.active {
  background: var(--ls-accent);
  color: #fff;
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
.cp-timeline {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.cp-msgs {
  max-width: 860px;
  margin: 0 auto;
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
  max-width: 82%;
  padding: 9px 13px;
  border-radius: 10px;
  font-size: 13.5px;
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
}
/* 失败/错误类助手气泡：警示描边，与正常回答区分（如模型不可用、运行异常） */
.cp-bubble.is-error {
  border-color: #f56c6c;
  color: #f56c6c;
  background: rgba(245, 108, 108, 0.06);
}
.cp-pending {
  color: var(--ls-fg-dim);
}
.cp-caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 3px;
  vertical-align: -2px;
  background: var(--ls-accent);
  animation: cp-blink 1s steps(2, start) infinite;
}
@keyframes cp-blink {
  to {
    visibility: hidden;
  }
}
.cp-msg-meta {
  margin-top: 3px;
  font-size: 11px;
}
/* 二次确认卡片：卡在气泡流末尾，左对齐强调「待你操作」 */
.cp-confirm {
  max-width: 82%;
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
.cp-files {
  flex: none;
  width: 240px;
  border-left: 1px solid var(--ls-border);
  background: var(--ls-panel);
  min-width: 0;
  display: flex;
}
</style>
