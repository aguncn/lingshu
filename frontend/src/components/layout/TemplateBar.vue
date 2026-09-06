<script setup>
// 顶部「常用任务分类 / 提示词模板」快捷入口（spec R4 / task 3.1）。
// 数据源 GET /api/prompts?category=task-preset（P3 种子：写文档/写代码/数据分析/排障）。
// 点击置为「选中上下文」（P8 前仅在输入框提示）；接口失败降级为轻量空态，不阻塞会话区。
import { RefreshRight } from '@element-plus/icons-vue'
import { computed } from 'vue'

import { usePromptStore } from '../../stores/prompt'

const prompt = usePromptStore()

const ready = computed(() => prompt.loaded && prompt.presets.length > 0)
const failed = computed(() => prompt.loaded && !prompt.presets.length)

function reload() {
  prompt.fetchPresets({ force: true })
}
</script>

<template>
  <div class="tb">
    <span class="tb-label">常用任务</span>

    <div v-loading="prompt.loading" class="tb-chips">
      <button
        v-for="p in prompt.presets"
        :key="p.id"
        type="button"
        class="tb-chip"
        :class="{ active: prompt.selectedId === p.id }"
        :title="p.content"
        @click="prompt.toggleSelect(p.id)"
      >
        {{ p.name }}
      </button>

      <span v-if="failed" class="tb-fallback text-dim">预设暂不可用</span>
    </div>

    <div class="tb-side">
      <template v-if="prompt.selectedPreset">
        <span class="tb-selected">已选：{{ prompt.selectedPreset.name }}</span>
      </template>
      <el-button v-if="failed" link :icon="RefreshRight" class="tb-retry" @click="reload">重试</el-button>
      <span v-else-if="ready" class="tb-hint text-dim">点选带入会话上下文（智能体接入后注入）</span>
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
}
.tb-chip {
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
.tb-selected {
  color: var(--ls-accent);
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tb-hint {
  font-size: 11px;
}
.tb-retry {
  padding: 0;
}
</style>
