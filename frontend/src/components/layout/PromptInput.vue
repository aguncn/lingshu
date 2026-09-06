<script setup>
// 会话输入框（spec R7 / task 3.4 + P8 agentscope-runtime）：常驻右栏底部。
// 「发送」走真会话 SSE：task store 负责流式渲染/确认/收尾，这里只负责取文本触发。
// 进行中（流式或等待二次确认）时禁用发送并给出「停止」——停止即断开会话连接，
// 后端 cancel 当前 run（每任务单活动会话），不会污染下一条消息。
import { Document, Promotion } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, ref } from 'vue'

import { useModelStore } from '../../stores/model'
import { usePromptStore } from '../../stores/prompt'
import { useTaskStore } from '../../stores/task'

const task = useTaskStore()
const prompt = usePromptStore()
const model = useModelStore()
const text = ref('')

const activeTask = computed(() => task.activeTask)
// 会话进行中：发送按钮/回车禁用；等待确认时提示工具名
const busy = computed(() => task.busy)
const busyHint = computed(() => {
  if (!busy.value) return ''
  return task.confirm ? `等待你对「${task.confirm.name}」放行/拒绝` : '智能体回复中…'
})
// 模型绑定提示：任务已绑 → 显示所用模型；未绑且不在加载 → 弱提示（后端也给出精确报错）
const modelHint = computed(() => {
  const c = model.config
  if (!activeTask.value) return ''
  if (model.configLoading) return ''
  return c ? `· 已绑 ${c.model_name || ''}` : '· 未绑模型'
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
    <!-- 模板选中提示：体现为输入框上方的“选中上下文” -->
    <div v-if="prompt.selectedPreset" class="pi-preset">
      <el-icon><Document /></el-icon>
      <span class="pi-preset-label">已选模板：{{ prompt.selectedPreset.name }}</span>
      <span class="pi-preset-content text-dim ellipsis">{{ prompt.selectedPreset.content }}</span>
      <el-button link type="primary" size="small" @click="prompt.clear()">取消</el-button>
    </div>

    <div class="pi-row">
      <div class="pi-context text-dim">
        <template v-if="activeTask">
          当前任务：{{ activeTask.title }} <span v-if="modelHint">{{ modelHint }}</span>
        </template>
        <template v-else>未选择任务</template>
      </div>

      <div class="pi-actions">
        <span v-if="busy" class="pi-busy text-dim">{{ busyHint }}</span>
        <el-button v-if="busy && activeTask" link size="small" type="danger" @click="task.abortChat()">
          停止
        </el-button>
      </div>
    </div>

    <div class="pi-input-row">
      <el-input
        v-model="text"
        type="textarea"
        :rows="1"
        :autosize="{ minRows: 1, maxRows: 4 }"
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
  </div>
</template>

<style scoped>
.pi {
  flex: none;
  padding: 8px 16px 12px;
  border-top: 1px solid var(--ls-border);
  background: var(--ls-panel);
}
.pi-preset {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  margin-bottom: 8px;
  border-radius: 6px;
  background: rgba(63, 126, 247, 0.08);
  color: var(--ls-fg);
  font-size: 12px;
}
.pi-preset-label {
  flex: none;
  color: var(--ls-accent);
  font-weight: 600;
}
.pi-preset-content {
  flex: 1 1 auto;
  min-width: 0;
}
.pi-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 12px;
}
.pi-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pi-busy {
  font-size: 12px;
  color: var(--ls-accent);
}
.pi-input-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}
.pi-send {
  flex: none;
}
</style>
