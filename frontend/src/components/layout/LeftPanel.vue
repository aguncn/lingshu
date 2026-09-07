<script setup>
// 左栏控制台（design D2 ①~④ / §4.4）：品牌 + 新建任务 + 能力广场导航 + 空间树 + 底部入口。
// C1 起空间不再横向并列铺开：中段头 =「全部空间 (N)」+「新建空间」，下面是可交互空间树(SpaceTree)。
// C4 起能力导航 = 主区整页广场：资料库/技能/MCP/知识库/运维专家 各自为独立菜单项，点击 → ui.openPlaza(page)。
//   C5 起「运维专家」=可复用档案组装页，在导航/广场与四中心同级；自动化仍属 P1/P2 范围外不出现在导航。
// 数据冷启动在此编排：空间 → 逐空间任务；运维专家档案的装载由广场/对话框各自懒加载，与供应商并行不互拖累。
import {
  Collection, Connection, Files, Fold, FolderOpened, Plus, Setting, UserFilled,
} from '@element-plus/icons-vue'
import { onMounted } from 'vue'

import { useModelStore } from '../../stores/model'
import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import { useUiStore } from '../../stores/ui'
import SpaceCreateDialog from './SpaceCreateDialog.vue'
import SpaceTree from './SpaceTree.vue'
import TaskCreateDialog from './TaskCreateDialog.vue'

const ui = useUiStore()
const space = useSpaceStore()
const task = useTaskStore()

// 能力广场页面（C4）：key 与 ui.plazaTab / 广场顶部页签一一对应。
// 资料库=RAG 是两类易混资产：资料库存「原文全文」，任务按全文原文引用；
// RAG(知识库)则把文档切块建索引，按关键词/相似度召回命中片段。文案上点明区分。
const PLAZA_PAGES = [
  { key: 'library', label: '资料库', icon: FolderOpened, desc: '原文全文引用：整份文档挂载复用' },
  { key: 'skills', label: '技能', icon: Collection, desc: 'AgentScope 技能库（SKILL.md 指令）' },
  { key: 'mcps', label: 'MCP', icon: Connection, desc: '外部工具连接器（stdio/http）' },
  { key: 'kbs', label: 'RAG', icon: Files, desc: '检索切块知识库：文档切块建索引，召回命中片段' },
  { key: 'experts', label: '运维专家', icon: UserFilled, desc: '可复用智能体档案：人设+技能/MCP/RAG+资料+默认模型，套用到任务即快照' },
]

// 导航点击 → 主区切到该页的整页广场
function goPage(page) {
  ui.openPlaza(page.key)
}

// 冷启动装载：空间确定后拉全部空间任务；模型供应商并行加载（失败互不拖累）。
// 运维专家档案等注册表数据由广场/挂载面板/建任务对话框各自懒加载（见 ExpertCenter 等）。
onMounted(async () => {
  await space.ensureLoaded()
  task.loadAll()
  useModelStore().fetchProviders()
})
</script>

<template>
  <div class="lp">
    <!-- 顶部：品牌 + 新建任务 + 能力广场导航（固定） -->
    <div class="lp-top">
      <div class="lp-brand">
        <div class="lp-brand-id">
          <div class="lp-logo">灵枢</div>
          <div class="lp-sub">IT 运维智能体 · 工作台</div>
        </div>
        <!-- 收起整栏：点它把左导航折起，主区占满（Workbench 左缘会浮出展开钮还原） -->
        <el-tooltip content="收起导航" placement="right">
          <el-button class="lp-collapse" text circle :icon="Fold" @click="ui.setLeftCollapsed(true)" />
        </el-tooltip>
      </div>

      <el-button class="lp-new-task" type="primary" :icon="Plus" @click="ui.openCreateTask()">
        新建任务
      </el-button>

      <div class="lp-nav">
        <div class="lp-nav-label">能力广场</div>
        <button
          v-for="p in PLAZA_PAGES"
          :key="p.key"
          class="lp-nav-item"
          :class="{ active: ui.mainView === 'plaza' && ui.activeNavKey === p.key }"
          type="button"
          :title="p.desc"
          @click="goPage(p)"
        >
          <el-icon><component :is="p.icon" /></el-icon>
          <span class="ellipsis">{{ p.label }}</span>
        </button>
      </div>
    </div>

    <!-- 中段：空间头（全部计数 + 新建按钮）+ 空间树（可滚动） -->
    <div class="lp-scroll">
      <div class="lp-section-head">
        <button
          class="lp-space-all"
          :class="{ active: space.activeSpaceId === null }"
          type="button"
          title="查看全部空间的任务"
          @click="space.selectSpace(null)"
        >
          <el-icon><FolderOpened /></el-icon>
          <span>全部空间</span>
          <span class="lp-space-count">{{ space.spaces.length }}</span>
        </button>
        <el-button
          class="lp-add-space"
          link
          :icon="Plus"
          @click="ui.spaceDialogOpen = true"
        >
          新建空间
        </el-button>
      </div>

      <SpaceTree />
    </div>

    <!-- 底部：个人信息 + 设置入口（注册中心已并入上方广场导航） -->
    <div class="lp-foot">
      <div class="lp-user">
        <el-avatar :size="26" class="lp-avatar">a</el-avatar>
        <div class="lp-user-meta">
          <div class="lp-user-name">admin</div>
          <div class="lp-user-role">单机 · 拥有者</div>
        </div>
      </div>
      <div class="lp-foot-actions">
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
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.lp-brand-id {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
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
  white-space: nowrap;
}
/* 收起钮：靠右吸边，hover 提亮，避免与品牌名挤在一行 */
.lp-collapse {
  margin-left: auto;
  flex: none;
  color: var(--ls-left-fg-dim);
}
.lp-collapse:hover {
  color: var(--ls-accent);
  background: transparent;
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
/* 全部空间：左侧计数按钮（activeSpaceId===null 时高亮 = 当前查看全部） */
.lp-space-all {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  padding: 4px 8px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--ls-left-fg);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}
.lp-space-all:hover {
  background: var(--ls-left-bg-hi);
}
.lp-space-all.active {
  background: rgba(63, 126, 247, 0.22);
  color: #dfe8ff;
}
.lp-space-all .el-icon {
  font-size: 14px;
  color: var(--ls-left-fg-dim);
}
.lp-space-all.active .el-icon {
  color: #dfe8ff;
}
.lp-space-count {
  font-size: 11px;
  color: var(--ls-left-fg-dim);
  background: var(--ls-left-bg-hi);
  border-radius: 999px;
  padding: 0 6px;
  line-height: 16px;
}
.lp-space-all.active .lp-space-count {
  color: #dfe8ff;
  background: rgba(255, 255, 255, 0.12);
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
