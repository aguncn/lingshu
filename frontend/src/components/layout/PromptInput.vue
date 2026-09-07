<script setup>
// 会话输入框（spec R7 / task 3.4 + P8 agentscope-runtime）：右栏底部的圆角「作曲家」。
// 输入框与「个性设置」链接融在同一圆角卡片里：底部一条链接行，平时不显示任务名/模型/权限/专家
// （那些常驻标签在顶部任务行、配置在点开「个性设置」后弹出的详情卡片，见 ChatPane/DetailDock）。
// 「发送」走真会话 SSE：task store 负责流式渲染/确认/收尾，这里只负责取文本触发。
// 进行中（流式、等待二次确认，或经 /chat/status 采纳的后台 run）时禁用发送并给出「停止」——
// 停止走 POST /chat/stop 真取消当前 run（区别于切走时的「脱离=保活」，见 task store 注释）。
import { Promotion, Top } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, ref } from 'vue'

import { useTaskStore } from '../../stores/task'
import { useUiStore } from '../../stores/ui'

const task = useTaskStore()
const ui = useUiStore()
const text = ref('')

const activeTask = computed(() => task.activeTask)
// 会话进行中：发送按钮/回车禁用；等待确认时提示工具名
const busy = computed(() => task.busy)
const busyHint = computed(() => {
  if (!busy.value) return ''
  if (task.confirm) return `等待你对「${task.confirm.name}」放行/拒绝`
  // 区分本地 SSE 流式与「后台 run 经 /chat/status 采纳」（刷新/切回恢复的运行，看不到逐字流式）
  return task.polling ? '智能体仍在后台运行…' : '智能体回复中…'
})

async function send() {
  const content = text.value.trim()
  if (!content) return
  if (!activeTask.value) {
    ElMessage.warning('请先从左侧选择一个任务')
    return
  }
  if (busy.value) {
    ElMessage.info('当前会话正在进行，请稍候')
    return
  }
  text.value = '' // 立即清空：气泡已乐观上屏，后续成败由 store 维护
  const ok = await task.sendMessage(content)
  if (!ok) text.value = content // 失败（如模型不可用）保留输入，改好配置可直接重发
}

// 回车发送，Shift+Enter 换行；进行中禁发（防止打断当前 run）
function onKeydown(e) {
  if (busy.value) return
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <div class="pi">
    <!-- 圆角作曲家：textarea + 底部「个性设置」链接 融在同一圆角框；打开详情卡片见 DetailDock -->
    <div class="pi-card" :class="{ open: ui.detailOpen }">
      <div class="pi-input-row">
        <el-input
          v-model="text"
          type="textarea"
          :rows="1"
          :autosize="{ minRows: 2, maxRows: 6 }"
          resize="none"
          placeholder="输入消息，向当前任务智能体提问（Enter 发送，Shift+Enter 换行）"
          @keydown="onKeydown"
        />
        <el-button
          type="primary"
          class="pi-send"
          :icon="Promotion"
          :disabled="!text.trim() || busy"
          @click="send"
        >发送</el-button>
      </div>

      <!-- 底部一条链接行：仅「个性设置」开关 + 进行态提示，不重复任务名/模型/权限/专家 -->
      <div class="pi-foot">
        <button
          type="button"
          class="pi-detail-link"
          :class="{ open: ui.detailOpen }"
          title="展开/收起 个性设置（模型绑定、挂载能力、权限、资料、工作空间）"
          @click="ui.detailOpen = !ui.detailOpen"
        >
          <el-icon class="pi-caret"><Top /></el-icon>
          <span>个性设置</span>
        </button>

        <div class="pi-foot-right">
          <span v-if="busy" class="pi-busy ellipsis">{{ busyHint }}</span>
          <el-button v-if="busy && activeTask" link size="small" type="danger" @click="task.stopChat()">
            停止
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pi {
  flex: none;
  padding: 6px 16px 12px;
}
/* 圆角作曲家：与输入框一体，底部一行个性设置链接视觉上“长”在框内；focus 描边提亮 */
.pi-card {
  border: 1px solid var(--ls-border);
  border-radius: 12px;
  background: var(--ls-panel);
  padding: 8px 10px 4px;
  box-shadow: 0 2px 8px rgba(20, 30, 50, 0.06);
}
.pi-card.open {
  border-color: var(--ls-accent);
}
.pi-input-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}
.pi-send {
  flex: none;
}
.pi-input-row :deep(.el-textarea__inner) {
  font-size: 12px;   /* 按需改小 */
}
/* 底部一条链接行：左「个性设置」、右进行态提示/停止 */
.pi-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 26px;
  border-top: 1px dashed var(--ls-border);
  margin-top: 4px;
  padding-top: 3px;
}
.pi-detail-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: transparent;
  color: var(--ls-fg-dim);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 2px;
}
.pi-detail-link:hover,
.pi-detail-link.open {
  color: var(--ls-accent);
}
.pi-caret {
  transition: transform 0.18s;
}
.pi-detail-link.open .pi-caret {
  transform: rotate(180deg); /* 打开时箭头朝下=收起示意 */
}
.pi-foot-right {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.pi-busy {
  font-size: 12px;
  color: var(--ls-accent);
  max-width: 60vw;
}
</style>
