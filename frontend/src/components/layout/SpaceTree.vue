<script setup>
// 左栏空间树（C1）：取代原横向空间 pill + 只读分组列表。
// 空间以树节点呈现：chevron 折叠/展开；点空间名=选中该空间为作用域（再点回全部）；
// 行悬停出「⋯」下拉：在此空间新建任务 / 重命名空间 / 删除空间（二次确认，级联删任务与文件）。
// 每个空间下的任务行悬停出操作下拉：重命名 / 改状态(待处理/进行中/已完成) / 删除。
// 搜索框同时匹配任务标题与空间名；作用域/展开态均为纯前端本地状态。
import {
  CaretRight,
  Delete,
  EditPen,
  MoreFilled,
  Plus,
  Search,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, reactive, ref } from 'vue'

import { metaOf, STATUS_META, TASK_TYPE_META, VISIBILITY_META } from '../../constants'
import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import { useUiStore } from '../../stores/ui'
import EmptyState from '../common/EmptyState.vue'
import StatusTag from '../common/StatusTag.vue'
import SpaceRenameDialog from './SpaceRenameDialog.vue'
import TaskRenameDialog from './TaskRenameDialog.vue'

const space = useSpaceStore()
const task = useTaskStore()
const ui = useUiStore()

// —— 分组：作用域(全部/单空间) + 关键字过滤（标题/空间名），与原分组列表语义一致 ——
const groups = computed(() => {
  const kw = task.search.trim().toLowerCase()
  const scoped = space.activeSpaceId
    ? space.spaces.filter((s) => s.id === space.activeSpaceId)
    : space.spaces
  const result = []
  for (const s of scoped) {
    let tasks = task.bySpace[s.id] || []
    if (kw) {
      const spaceHit = (s.name || '').toLowerCase().includes(kw)
      const hitTasks = tasks.filter((t) => (t.title || '').toLowerCase().includes(kw))
      if (!spaceHit && !hitTasks.length) continue
      tasks = spaceHit ? tasks : hitTasks
    }
    result.push({ space: s, tasks })
  }
  return result
})

const noSpace = computed(() => !space.loading && !space.spaces.length)
const noMatch = computed(() => space.spaces.length > 0 && groups.value.length === 0)

// —— 展开态：默认全部展开，折叠只存「被折叠」的空间 id ——
const collapsed = reactive(new Set())
function isCollapsed(sid) {
  return collapsed.has(sid)
}
function toggleCollapse(sid) {
  if (collapsed.has(sid)) collapsed.delete(sid)
  else collapsed.add(sid)
}

// 点空间名 = 选中该空间为作用域；再点已选中的空间名回到「全部」
function toggleScope(sid) {
  space.selectSpace(space.activeSpaceId === sid ? null : sid)
}

const statusOptions = Object.entries(STATUS_META).map(([value, m]) => ({
  value,
  label: `置为${m.label}`,
}))

function visColor(v) {
  const m = metaOf(VISIBILITY_META, v)
  const colorMap = { info: '#7a8494', success: '#67c23a', primary: '#3f7ef7' }
  return colorMap[m.type] || '#7a8494'
}

function typeLabel(value) {
  return metaOf(TASK_TYPE_META, value).label
}

function fmtDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// —— 空间行操作：新建任务 / 重命名 / 删除 ——
const spaceRenameOpen = ref(false)
const renameSpaceTarget = ref(null)

async function onSpaceCmd(cmd, s) {
  if (cmd === 'newtask') {
    space.selectSpace(s.id) // 选中该空间 → 新建任务对话框以它为默认归属
    ui.openCreateTask()
  } else if (cmd === 'rename') {
    renameSpaceTarget.value = s
    spaceRenameOpen.value = true
  } else if (cmd === 'delete') {
    await confirmDeleteSpace(s)
  }
}

async function confirmDeleteSpace(s) {
  const n = (task.bySpace[s.id] || []).length
  try {
    await ElMessageBox.confirm(
      `空间「${s.name}」及其下 ${n} 个任务、会话与工作文件将一并删除，且不可恢复。确定删除？`,
      '删除空间',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await space.deleteSpace(s.id)
    ElMessage.success(`空间「${s.name}」已删除`)
  } catch {
    // 失败提示由 http 拦截器统一弹出
  }
}

// —— 任务行操作：重命名 / 改状态 / 删除 ——
const taskRenameOpen = ref(false)
const renameTaskTarget = ref(null)

async function onTaskCmd(cmd, t) {
  if (cmd === 'rename') {
    renameTaskTarget.value = t
    taskRenameOpen.value = true
  } else if (cmd && cmd.startsWith('status:')) {
    const status = cmd.slice('status:'.length)
    try {
      await task.updateTaskEntry(t, { status })
    } catch {
      // 失败提示由 http 拦截器统一弹出
    }
  } else if (cmd === 'delete') {
    await confirmDeleteTask(t)
  }
}

async function confirmDeleteTask(t) {
  try {
    await ElMessageBox.confirm(
      `删除任务「${t.title}」？其会话消息与工作文件将一并删除，且不可恢复。`,
      '删除任务',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await task.deleteTaskEntry(t)
    ElMessage.success('任务已删除')
  } catch {
    // 失败提示由 http 拦截器统一弹出
  }
}
</script>

<template>
  <div class="st">
    <el-input
      v-model="task.search"
      class="st-search"
      size="small"
      :prefix-icon="Search"
      clearable
      placeholder="搜索任务 / 空间"
    />

    <div v-loading="task.loading" class="st-body">
      <EmptyState
        v-if="noSpace"
        description="还没有空间"
        tip="点上方「新建空间」创建第一个空间，任务按空间分组管理"
      />
      <EmptyState v-else-if="noMatch" description="没有匹配的任务或空间" />

      <template v-else>
        <div v-for="g in groups" :key="g.space.id" class="st-group">
          <!-- 空间节点头：chevron 折叠/展开 + 点名字选作用域 + 行操作下拉 -->
          <div class="st-group-head">
            <button
              type="button"
              class="st-caret"
              :class="{ open: !isCollapsed(g.space.id) }"
              :aria-label="isCollapsed(g.space.id) ? '展开' : '折叠'"
              @click="toggleCollapse(g.space.id)"
            >
              <el-icon><CaretRight /></el-icon>
            </button>
            <button
              type="button"
              class="st-name"
              :class="{ scoped: space.activeSpaceId === g.space.id }"
              :title="`${g.space.name} · 点击${
                space.activeSpaceId === g.space.id ? '回到全部' : '只看该空间'
              }`"
              @click="toggleScope(g.space.id)"
            >
              <span class="st-dot" :style="{ background: visColor(g.space.visibility) }" />
              <span class="ellipsis st-name-text">{{ g.space.name }}</span>
              <span class="st-count">{{ g.tasks.length }}</span>
            </button>
            <el-dropdown
              trigger="click"
              class="st-ops"
              @command="(cmd) => onSpaceCmd(cmd, g.space)"
            >
              <button type="button" class="st-more" @click.stop>
                <el-icon><MoreFilled /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="newtask" :icon="Plus">在此空间新建任务</el-dropdown-item>
                  <el-dropdown-item command="rename" :icon="EditPen">重命名空间</el-dropdown-item>
                  <el-dropdown-item command="delete" :icon="Delete" divided>删除空间</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <!-- 空间下任务（折叠时隐藏） -->
          <div v-show="!isCollapsed(g.space.id)" class="st-tasks">
            <div
              v-for="t in g.tasks"
              :key="t.id"
              class="st-task"
              :class="{ active: task.activeTaskId === t.id }"
              @click="task.selectTask(t)"
            >
              <div class="st-task-main">
                <span class="st-task-title ellipsis">{{ t.title }}</span>
                <span class="st-task-meta">{{ typeLabel(t.task_type) }} · {{ fmtDate(t.created_at) }}</span>
              </div>
              <StatusTag :value="t.status" />
              <el-dropdown
                trigger="click"
                class="st-task-ops"
                @command="(cmd) => onTaskCmd(cmd, t)"
              >
                <button type="button" class="st-task-more" @click.stop>
                  <el-icon><MoreFilled /></el-icon>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="rename" :icon="EditPen">重命名</el-dropdown-item>
                    <el-dropdown-item
                      v-for="o in statusOptions"
                      :key="o.value"
                      :command="`status:${o.value}`"
                      :disabled="t.status === o.value"
                    >
                      {{ o.label }}
                    </el-dropdown-item>
                    <el-dropdown-item command="delete" :icon="Delete" divided>删除任务</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <div v-if="!g.tasks.length" class="st-empty-group">该空间暂无任务</div>
          </div>
        </div>
      </template>
    </div>

    <!-- 行内重命名对话框 -->
    <SpaceRenameDialog v-model="spaceRenameOpen" :space="renameSpaceTarget" />
    <TaskRenameDialog v-model="taskRenameOpen" :task="renameTaskTarget" />
  </div>
</template>

<style scoped>
.st {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.st-search {
  margin-bottom: 6px;
}
.st-search :deep(.el-input__wrapper) {
  background: var(--ls-left-bg-hi);
  box-shadow: none;
  border-radius: 6px;
}
.st-body {
  min-height: 80px;
}
.st-group {
  margin-bottom: 4px;
}
/* —— 空间节点头 —— */
.st-group-head {
  display: flex;
  align-items: center;
  gap: 2px;
  border-radius: 6px;
  padding-right: 2px;
}
.st-group-head:hover {
  background: var(--ls-left-bg-hi);
}
.st-caret {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 22px;
  border: none;
  background: transparent;
  color: var(--ls-left-fg-dim);
  cursor: pointer;
  border-radius: 4px;
}
.st-caret .el-icon {
  transition: transform 0.15s ease;
  font-size: 12px;
}
.st-caret.open .el-icon {
  transform: rotate(90deg);
}
.st-name {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 4px;
  border: none;
  background: transparent;
  color: var(--ls-left-fg);
  cursor: pointer;
  text-align: left;
}
.st-name.scoped .st-name-text {
  color: #dfe8ff;
}
.st-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
}
.st-name-text {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ls-left-fg-strong);
}
.st-name.scoped .st-name-text {
  color: var(--ls-left-fg-strong);
}
.st-count {
  flex: none;
  font-size: 11px;
  color: var(--ls-left-fg-dim);
}
.st-more,
.st-task-more {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  background: transparent;
  color: var(--ls-left-fg-dim);
  cursor: pointer;
  border-radius: 4px;
}
.st-more:hover,
.st-task-more:hover {
  background: var(--ls-left-bg-hi);
  color: var(--ls-left-fg);
}
.st-ops,
.st-task-ops {
  flex: none;
  opacity: 0; /* 悬停空间/任务行才浮现，避免默认太挤 */
}
.st-group-head:hover .st-ops,
.st-task:hover .st-task-ops {
  opacity: 1;
}
/* —— 任务区 —— */
.st-tasks {
  margin-left: 8px;
  border-left: 1px solid var(--ls-left-border);
}
.st-task {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 5px 6px;
  border: none;
  background: transparent;
  color: var(--ls-left-fg);
  cursor: pointer;
  border-radius: 0 6px 6px 0;
  text-align: left;
}
.st-task:hover {
  background: var(--ls-left-bg-hi);
}
.st-task.active {
  background: rgba(63, 126, 247, 0.22);
  color: #dfe8ff;
}
.st-task-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.st-task-title {
  font-size: 13px;
}
.st-task-meta {
  font-size: 11px;
  color: var(--ls-left-fg-dim);
}
.st-empty-group {
  margin: 2px 0 6px 14px;
  font-size: 12px;
  color: var(--ls-left-fg-dim);
  opacity: 0.85;
}
</style>
