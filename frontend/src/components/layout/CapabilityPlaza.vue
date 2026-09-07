<script setup>
// 能力广场主区整页（C4 / design D1）：顶部一排「卡片式」大页签，可来回切
//   资料库/技能/MCP/知识库/运维专家；页体为对应整页（列表均以卡片网格承载 CRUD）。多页常驻 DOM（v-show）
//   → 切换不丢滚动/展开态。与右栏工作区（chat）互斥：由 Workbench 按 ui.mainView 决定显隐，此组件懒挂载。
// 资料库=集中文档资产(LibraryPage)、知识库=可切块检索的 KB 实体(KbCenter)——两类不同，故各自独立页签；
// C5 起「运维专家」=可复用档案组装页（ExpertCenter），与四中心同级。
import { ArrowRight, Collection, Connection, Files, FolderOpened, UserFilled } from '@element-plus/icons-vue'
import { onMounted } from 'vue'

import { useRegistryStore } from '../../stores/registry'
import { useUiStore } from '../../stores/ui'
import ExpertCenter from '../registry/ExpertCenter.vue'
import KbCenter from '../registry/KbCenter.vue'
import McpCenter from '../registry/McpCenter.vue'
import SkillCenter from '../registry/SkillCenter.vue'
import LibraryPage from './LibraryPage.vue'

const ui = useUiStore()
const reg = useRegistryStore()

const PAGES = [
  { key: 'library', label: '资料库', sub: '原文全文引用', icon: FolderOpened },
  { key: 'skills', label: '技能', sub: '可复用技能指令', icon: Collection },
  { key: 'mcps', label: 'MCP', sub: '外部工具连接器', icon: Connection },
  { key: 'kbs', label: 'RAG', sub: '切块检索 · 相似召回', icon: Files },
  { key: 'experts', label: '运维专家', sub: '可复用档案 · 套用即快照', icon: UserFilled },
]

// 打开即冷启动注册表一次（技能/MCP 两个 center 依赖 reg 全局列表；失败各自置空不拖垮）
onMounted(() => reg.ensureLoaded())
</script>

<template>
  <div class="plz">
    <!-- 顶：卡片式大页签（左） + 回到工作区（右） -->
    <header class="plz-head">
      <div class="plz-tabs">
        <button
          v-for="p in PAGES"
          :key="p.key"
          type="button"
          class="plz-tab"
          :class="{ active: ui.plazaTab === p.key }"
          @click="ui.openPlaza(p.key)"
        >
          <el-icon class="plz-tab-icon"><component :is="p.icon" /></el-icon>
          <span class="plz-tab-txt">
            <span class="plz-tab-label">{{ p.label }}</span>
            <span class="plz-tab-sub">{{ p.sub }}</span>
          </span>
        </button>
      </div>
      <el-button class="plz-back" text size="small" :icon="ArrowRight" @click="ui.showChat()">
        回到工作区
      </el-button>
    </header>

    <!-- 页体：多页常驻，按当前页签切换显示（各自内部滚动、带新建/操作条） -->
    <div class="plz-body">
      <div v-show="ui.plazaTab === 'library'" class="plz-page"><LibraryPage /></div>
      <div v-show="ui.plazaTab === 'skills'" class="plz-page"><SkillCenter /></div>
      <div v-show="ui.plazaTab === 'mcps'" class="plz-page"><McpCenter /></div>
      <div v-show="ui.plazaTab === 'kbs'" class="plz-page"><KbCenter /></div>
      <div v-show="ui.plazaTab === 'experts'" class="plz-page"><ExpertCenter /></div>
    </div>
  </div>
</template>

<style scoped>
.plz {
  height: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--ls-bg);
}
/* —— 顶部大页签 —— */
.plz-head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px 0;
}
.plz-tabs {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  gap: 10px;
}
.plz-tab {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 16px;
  border: 1px solid var(--ls-border);
  border-radius: 10px;
  background: var(--ls-panel);
  color: var(--ls-fg);
  font: inherit;
  text-align: left;
  cursor: pointer;
  min-width: 0;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}
.plz-tab:hover {
  border-color: rgba(63, 126, 247, 0.45);
  background: var(--ls-bg-hi, rgba(63, 126, 247, 0.07));
}
.plz-tab.active {
  border-color: rgba(63, 126, 247, 0.6);
  background: rgba(63, 126, 247, 0.13);
  box-shadow: 0 0 0 1px rgba(63, 126, 247, 0.25), inset 0 -2px 0 var(--ls-accent);
}
.plz-tab-icon {
  flex: none;
  font-size: 18px;
  color: var(--ls-fg-dim);
}
.plz-tab.active .plz-tab-icon {
  color: var(--ls-accent);
}
.plz-tab-txt {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.plz-tab-label {
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.3;
}
.plz-tab-sub {
  font-size: 11px;
  color: var(--ls-fg-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.plz-back {
  flex: none;
  color: var(--ls-fg-dim);
}
/* —— 页体 —— */
.plz-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  padding: 12px 16px 16px;
}
.plz-page {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
}
/* 窄屏收窄：页签只保留图标+主名，隐藏副标题，避免换行 */
@media (max-width: 1100px) {
  .plz-tab { padding: 9px 12px; }
  .plz-tab-sub { display: none; }
}
</style>
