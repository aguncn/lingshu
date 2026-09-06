<script setup>
// 任务分组列表（design D2③ / D8）：逐空间拉取的任务在此按空间分组展示，
// 搜索同时匹配「任务标题 / 空间名」，随行 StatusTag 徽标，点击任务载入右栏。
import { Search } from '@element-plus/icons-vue'
import { computed } from 'vue'

import { metaOf, TASK_TYPE_META } from '../../constants'
import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import EmptyState from '../common/EmptyState.vue'
import StatusTag from '../common/StatusTag.vue'
import VisibilityTag from '../common/VisibilityTag.vue'

const space = useSpaceStore()
const task = useTaskStore()

// 按「全部 / 选中空间」圈定空间集合，再做标题/空间名过滤（spec R2 场景1）
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

function typeLabel(value) {
  return metaOf(TASK_TYPE_META, value).label
}

function fmtDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function toggleGroup(spaceId) {
  // 点分组头 = 只看该空间；再点回到全部
  space.selectSpace(space.activeSpaceId === spaceId ? null : spaceId)
}
</script>

<template>
  <div class="tgl">
    <el-input
      v-model="task.search"
      class="tgl-search"
      size="small"
      :prefix-icon="Search"
      clearable
      placeholder="搜索任务 / 空间"
    />

    <div v-loading="task.loading" class="tgl-body">
      <EmptyState
        v-if="noSpace"
        description="还没有空间"
        tip="点上方「新建空间」创建第一个空间，任务按空间分组管理"
      />
      <EmptyState v-else-if="noMatch" description="没有匹配的任务或空间" />

      <template v-else>
        <div
          v-for="g in groups"
          :key="g.space.id"
          class="tgl-group"
        >
          <button
            type="button"
            class="tgl-group-head"
            :class="{ scoped: space.activeSpaceId === g.space.id }"
            :title="`${g.space.name} · ${g.space.visibility}`"
            @click="toggleGroup(g.space.id)"
          >
            <span class="ellipsis tgl-group-name">{{ g.space.name }}</span>
            <VisibilityTag :value="g.space.visibility" />
            <span class="tgl-group-count">{{ g.tasks.length }}</span>
          </button>

          <div v-if="g.tasks.length" class="tgl-tasks">
            <button
              v-for="t in g.tasks"
              :key="t.id"
              type="button"
              class="tgl-task"
              :class="{ active: task.activeTaskId === t.id }"
              @click="task.selectTask(t)"
            >
              <div class="tgl-task-main">
                <span class="tgl-task-title ellipsis">{{ t.title }}</span>
                <span class="tgl-task-meta">
                  {{ typeLabel(t.task_type) }} · {{ fmtDate(t.created_at) }}
                </span>
              </div>
              <StatusTag :value="t.status" />
            </button>
          </div>
          <div v-else class="tgl-empty-group">该空间暂无任务</div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.tgl-search {
  margin-bottom: 6px;
}
.tgl-search :deep(.el-input__wrapper) {
  background: var(--ls-left-bg-hi);
  box-shadow: none;
  border-radius: 6px;
}
.tgl-body {
  min-height: 80px;
}
.tgl-group {
  margin-bottom: 4px;
}
.tgl-group-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 5px 6px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--ls-left-fg);
  cursor: pointer;
  text-align: left;
}
.tgl-group-head:hover,
.tgl-group-head.scoped {
  background: var(--ls-left-bg-hi);
}
.tgl-group-name {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ls-left-fg-strong);
}
.tgl-group-count {
  font-size: 11px;
  color: var(--ls-left-fg-dim);
}
.tgl-tasks {
  margin-left: 6px;
  border-left: 1px solid var(--ls-left-border);
}
.tgl-task {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 8px;
  border: none;
  background: transparent;
  color: var(--ls-left-fg);
  cursor: pointer;
  border-radius: 0 6px 6px 0;
  text-align: left;
}
.tgl-task:hover {
  background: var(--ls-left-bg-hi);
}
.tgl-task.active {
  background: rgba(63, 126, 247, 0.22);
  color: #dfe8ff;
}
.tgl-task-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.tgl-task-title {
  font-size: 13px;
}
.tgl-task-meta {
  font-size: 11px;
  color: var(--ls-left-fg-dim);
}
.tgl-empty-group {
  margin: 2px 0 6px 12px;
  font-size: 12px;
  color: var(--ls-left-fg-dim);
  opacity: 0.85;
}
</style>
