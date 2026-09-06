<script setup>
// 左栏控制台（design D2 ①~④ / §4.4）：品牌 + 新建任务 + 能力导航 + 空间/任务列表 + 底部入口。
// 数据冷启动在此编排：空间 → 逐空间任务；模板条与供应商并行（各自失败互不拖累）。
import {
  Collection, Cpu, FolderOpened, Plus, Setting, VideoPlay,
} from '@element-plus/icons-vue'
import { onMounted } from 'vue'

import { useModelStore } from '../../stores/model'
import { usePromptStore } from '../../stores/prompt'
import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import { useUiStore } from '../../stores/ui'
import { metaOf, VISIBILITY_META } from '../../constants'
import SpaceCreateDialog from './SpaceCreateDialog.vue'
import TaskCreateDialog from './TaskCreateDialog.vue'
import TaskGroupList from './TaskGroupList.vue'

const ui = useUiStore()
const space = useSpaceStore()
const task = useTaskStore()

// 主导航（spec R1）：专家·技能·MCP → 注册中心技能 tab；资料库 → 资料库抽屉；自动化远期占位。
// 后两者已有真实后端（P5 registry / P6 library），不再只开空态。
const NAV_ITEMS = [
  {
    key: 'cap',
    label: '专家·技能·MCP',
    icon: Cpu,
    kind: 'registry',
    desc: '能力登记与挂载中心（P5 已交付）：打开注册中心统一管理技能 / MCP / 知识库 / 专家。',
  },
  {
    key: 'automation',
    label: '自动化',
    icon: VideoPlay,
    kind: 'capability',
    capTitle: '自动化引擎',
    phase: 'P1/P2',
    desc: '自动化编排与触发器属远期能力（范围外 P1/P2），本期不提供入口。',
  },
  {
    key: 'library',
    label: '资料库',
    icon: FolderOpened,
    kind: 'library',
    desc: '集中资料库（P6 已交付）：跨任务复用文件，按 全部/全局/共享/空间 浏览与检索。',
  },
]

// 导航分流：注册中心 / 资料库走真实抽屉，能力占位仅保留给远期（自动化）项
function handleNav(item) {
  if (item.kind === 'registry') {
    ui.activeNavKey = item.key // 高亮当前项；抽屉开关状态由 store 统一管
    ui.openRegistry('skills')
  } else if (item.kind === 'library') {
    ui.openLibrary() // openLibrary 内部已置 activeNavKey='library'
  } else {
    ui.openCapability({ key: item.key, title: item.capTitle, phase: item.phase, desc: item.desc })
  }
}

const visColor = (v) => {
  const m = metaOf(VISIBILITY_META, v)
  const colorMap = { info: '#7a8494', success: '#67c23a', primary: '#3f7ef7' }
  return colorMap[m.type] || '#7a8494'
}

function taskCountOf(sid) {
  return (task.bySpace[sid] || []).length
}

function totalTaskCount() {
  return space.spaces.reduce((sum, s) => sum + taskCountOf(s.id), 0)
}

// 冷启动装载：空间确定后拉全部空间任务；模板条/供应商并行加载
onMounted(async () => {
  await space.ensureLoaded()
  task.loadAll()
  usePromptStore().fetchPresets()
  useModelStore().fetchProviders()
})
</script>

<template>
  <div class="lp">
    <!-- 顶部：品牌 + 新建任务 + 能力导航（固定） -->
    <div class="lp-top">
      <div class="lp-brand">
        <div class="lp-logo">灵枢</div>
        <div class="lp-sub">IT 运维智能体 · 工作台</div>
      </div>

      <el-button class="lp-new-task" type="primary" :icon="Plus" @click="ui.taskDialogOpen = true">
        新建任务
      </el-button>

      <div class="lp-nav">
        <div class="lp-nav-label">能力导航</div>
        <button
          v-for="item in NAV_ITEMS"
          :key="item.key"
          class="lp-nav-item"
          :class="{ active: ui.activeNavKey === item.key }"
          type="button"
          @click="handleNav(item)"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span class="ellipsis">{{ item.label }}</span>
        </button>
      </div>
    </div>

    <!-- 中段：空间过滤 + 任务分组（可滚动） -->
    <div class="lp-scroll">
      <div class="lp-section-head">
        <div class="lp-spaces" @click.stop>
          <button
            class="lp-space-chip"
            :class="{ active: space.activeSpaceId === null }"
            type="button"
            title="全部空间"
            @click="space.selectSpace(null)"
          >
            <el-icon><Collection /></el-icon>
            <span>全部</span>
            <span class="lp-chip-count">{{ totalTaskCount() }}</span>
          </button>
          <el-tooltip
            v-for="s in space.spaces"
            :key="s.id"
            :content="`${s.name}（${s.visibility}）`"
            placement="top"
          >
            <button
              class="lp-space-chip"
              :class="{ active: space.activeSpaceId === s.id }"
              type="button"
              @click="space.selectSpace(s.id)"
            >
              <span class="lp-dot" :style="{ background: visColor(s.visibility) }" />
              <span class="ellipsis">{{ s.name }}</span>
              <span class="lp-chip-count">{{ taskCountOf(s.id) }}</span>
            </button>
          </el-tooltip>
        </div>
        <el-button
          class="lp-add-space"
          link
          :icon="Plus"
          @click="ui.spaceDialogOpen = true"
        >
          新建空间
        </el-button>
      </div>

      <TaskGroupList />
    </div>

    <!-- 底部：个人信息 + 注册中心/设置入口 -->
    <div class="lp-foot">
      <div class="lp-user">
        <el-avatar :size="26" class="lp-avatar">a</el-avatar>
        <div class="lp-user-meta">
          <div class="lp-user-name">admin</div>
          <div class="lp-user-role">单机 · 拥有者</div>
        </div>
      </div>
      <div class="lp-foot-actions">
        <el-tooltip content="注册中心" placement="top">
          <el-button class="lp-foot-btn" text circle @click="ui.openRegistry('skills')">
            <el-icon><Collection /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip content="设置" placement="top">
          <el-button class="lp-foot-btn" text circle @click="ui.settingsOpen = true">
            <el-icon><Setting /></el-icon>
          </el-button>
        </el-tooltip>
      </div>
    </div>

    <!-- 新建浮层（左栏承载，命令面板经 ui store 开关直达） -->
    <SpaceCreateDialog />
    <TaskCreateDialog />
  </div>
</template>

<style scoped>
.lp {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  color: var(--ls-left-fg);
}
/* —— 顶部 —— */
.lp-top {
  padding: 14px 14px 10px;
  border-bottom: 1px solid var(--ls-left-border);
  flex: none;
}
.lp-brand {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 12px;
}
.lp-logo {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--ls-left-fg-strong);
}
.lp-sub {
  font-size: 11px;
  color: var(--ls-left-fg-dim);
  letter-spacing: 0.5px;
}
.lp-new-task {
  width: 100%;
  margin-bottom: 12px;
  font-weight: 600;
}
.lp-nav-label {
  font-size: 11px;
  color: var(--ls-left-fg-dim);
  letter-spacing: 1px;
  margin-bottom: 6px;
}
.lp-nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  margin-bottom: 2px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--ls-left-fg);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}
.lp-nav-item:hover {
  background: var(--ls-left-bg-hi);
}
.lp-nav-item.active {
  background: rgba(63, 126, 247, 0.22);
  color: #dfe8ff;
}
/* —— 中段 —— */
.lp-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 8px 6px;
}
.lp-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin: 2px 4px 8px;
}
.lp-spaces {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  scrollbar-width: none;
  min-width: 0;
}
.lp-space-chip {
  display: flex;
  align-items: center;
  gap: 5px;
  max-width: 120px;
  padding: 3px 8px;
  border: 1px solid var(--ls-left-border);
  border-radius: 999px;
  background: transparent;
  color: var(--ls-left-fg);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.lp-space-chip.active {
  background: var(--ls-accent);
  border-color: var(--ls-accent);
  color: #fff;
}
.lp-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
}
.lp-chip-count {
  font-size: 11px;
  opacity: 0.75;
}
.lp-add-space {
  flex: none;
  font-size: 12px;
}
/* —— 底部 —— */
.lp-foot {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-top: 1px solid var(--ls-left-border);
}
.lp-user {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.lp-avatar {
  background: #3a4a63;
  color: #dbe4f2;
  font-size: 12px;
}
.lp-user-name {
  font-size: 13px;
  color: var(--ls-left-fg-strong);
  line-height: 1.2;
}
.lp-user-role {
  font-size: 11px;
  color: var(--ls-left-fg-dim);
}
.lp-foot-actions {
  display: flex;
  gap: 2px;
}
.lp-foot-btn {
  color: var(--ls-left-fg-dim);
}
</style>
