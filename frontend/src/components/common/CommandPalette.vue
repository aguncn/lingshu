<script setup>
// 命令面板（spec R8 / task 4.1 / design D5）：全局 Ctrl/Cmd+K 打开、Esc/失焦关闭；
// 模糊过滤 + 方向键高亮 + 回车执行；执行动作统一走 store（新建对话框 / 暗色 / 抽屉 / 刷新）。
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import { useUiStore } from '../../stores/ui'

const ui = useUiStore()
const space = useSpaceStore()
const task = useTaskStore()

const keyword = ref('')
const activeIndex = ref(0)
const inputRef = ref(null)
let lastFocus = null // 打开前焦点元素：Esc 关闭后还原（spec R8 场景2）

// 命令注册表：label 供过滤/展示，keywords 扩展命中词
const commands = [
  { id: 'new-space', label: '新建空间', keywords: 'space 空间 新建 create', run: () => { ui.spaceDialogOpen = true } },
  { id: 'new-task', label: '新建任务', keywords: 'task 任务 新建 create', run: () => { ui.taskDialogOpen = true } },
  {
    id: 'toggle-dark',
    label: '切换暗色模式',
    keywords: 'dark theme 暗色 主题 亮色 切换',
    run: () => {
      ui.toggleDark()
      ElMessage.success(ui.dark ? '已切换为暗色模式' : '已切换为亮色模式')
    },
  },
  { id: 'open-settings', label: '打开设置', keywords: 'settings setting 设置 偏好 配置', run: () => { ui.settingsOpen = true } },
  { id: 'open-plaza', label: '打开能力广场', keywords: 'plaza 广场 能力 技能 资料库 mcp 知识库', run: () => { ui.openPlaza('skills') } },
  {
    id: 'refresh-tasks',
    label: '刷新任务列表',
    keywords: 'refresh reload 刷新 任务 列表 同步',
    run: async () => {
      await task.loadAll()
      ElMessage.success('任务列表已刷新')
    },
  },
]

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return commands
  return commands.filter((c) => `${c.label} ${c.keywords}`.toLowerCase().includes(kw))
})

// 过滤结果变化时把高亮收回到首项
watch(filtered, () => {
  activeIndex.value = 0
})

watch(() => ui.commandOpen, (open) => {
  if (open) {
    keyword.value = ''
    activeIndex.value = 0
    nextTick(() => inputRef.value?.focus())
  }
})

function restoreFocus() {
  if (lastFocus && typeof lastFocus.focus === 'function') {
    try { lastFocus.focus() } catch { /* 忽略不可聚焦节点 */ }
  }
}

function closeAndRestore() {
  ui.commandOpen = false
  restoreFocus()
}

function runAt(index) {
  const cmd = filtered.value[index]
  if (!cmd) return
  ui.commandOpen = false // 执行前先关面板（新建对话框/抽屉随后经 store 打开）
  cmd.run()
}

function onGlobalKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    if (ui.commandOpen) {
      ui.commandOpen = false
      restoreFocus()
    } else {
      lastFocus = document.activeElement
      ui.commandOpen = true
    }
    return
  }
  if (ui.commandOpen && e.key === 'Escape') {
    ui.commandOpen = false
    restoreFocus()
  }
}

function onInputKeydown(e) {
  const len = filtered.value.length
  if (!len) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = (activeIndex.value + 1) % len
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = (activeIndex.value - 1 + len) % len
  } else if (e.key === 'Enter') {
    e.preventDefault()
    runAt(activeIndex.value)
  }
}

onMounted(() => window.addEventListener('keydown', onGlobalKeydown, true))
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobalKeydown, true))
</script>

<template>
  <teleport to="body">
    <div v-if="ui.commandOpen" class="palette-mask" @click.self="closeAndRestore">
      <div class="palette">
        <div class="palette-search">
          <el-icon class="palette-search-icon"><Search /></el-icon>
          <input
            ref="inputRef"
            v-model="keyword"
            class="palette-input"
            placeholder="输入命令或关键词，如「暗色」「新建任务」…"
            @keydown="onInputKeydown"
          />
          <kbd class="palette-esc">Esc</kbd>
        </div>

        <ul class="palette-list">
          <li
            v-for="(cmd, i) in filtered"
            :key="cmd.id"
            class="palette-item"
            :class="{ active: i === activeIndex }"
            @mouseenter="activeIndex = i"
            @click="runAt(i)"
          >
            <span class="palette-item-label">{{ cmd.label }}</span>
            <span v-if="i === activeIndex" class="palette-item-hit">↵ 执行</span>
          </li>

          <li v-if="!filtered.length" class="palette-empty">没有匹配的命令</li>
        </ul>

        <div class="palette-footer text-dim">
          ↑↓ 选择 · Enter 执行 · Esc 关闭
        </div>
      </div>
    </div>
  </teleport>
</template>

<style scoped>
.palette-mask {
  position: fixed;
  inset: 0;
  background: rgba(12, 16, 24, 0.45);
  z-index: 3000;
  display: flex;
  align-items: flex-start;
  justify-content: center;
}
.palette {
  margin-top: 16vh;
  width: 560px;
  max-width: calc(100vw - 40px);
  border-radius: 10px;
  overflow: hidden;
  background: var(--ls-panel);
  border: 1px solid var(--ls-border);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.28);
}
.palette-search {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--ls-border);
}
.palette-search-icon {
  color: var(--ls-fg-dim);
}
.palette-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  color: var(--ls-fg);
  font-size: 14px;
}
.palette-esc {
  font-size: 11px;
  color: var(--ls-fg-dim);
  border: 1px solid var(--ls-border);
  border-radius: 4px;
  padding: 1px 6px;
}
.palette-list {
  list-style: none;
  margin: 0;
  padding: 6px;
  max-height: 300px;
  overflow-y: auto;
}
.palette-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13.5px;
}
.palette-item.active {
  background: var(--ls-accent);
  color: #fff;
}
.palette-item-label {
  font-weight: 500;
}
.palette-item-hit {
  font-size: 11px;
  opacity: 0.85;
}
.palette-empty {
  padding: 14px;
  text-align: center;
  font-size: 13px;
  color: var(--ls-fg-dim);
}
.palette-footer {
  padding: 8px 14px;
  border-top: 1px solid var(--ls-border);
  font-size: 11px;
}
</style>
