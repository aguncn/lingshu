<script setup>
// 注册中心抽屉（spec R9 / task 4.2 → P5 全量管理）：技能/MCP/知识库/专家四 center 内嵌。
// 打开即 ensureLoaded 冷启动一次；各 center 内 CRUD 后用 reg.loadCategory 局部刷新。
// tab-position=left：label 区窄、内容区宽（660px 抽屉容纳四类管理动作与表单）。
import { Collection, Connection, FolderOpened, User } from '@element-plus/icons-vue'
import { computed, onMounted } from 'vue'

import ExpertCenter from '../registry/ExpertCenter.vue'
import KbCenter from '../registry/KbCenter.vue'
import McpCenter from '../registry/McpCenter.vue'
import SkillCenter from '../registry/SkillCenter.vue'
import { useRegistryStore } from '../../stores/registry'
import { useUiStore } from '../../stores/ui'

const ui = useUiStore()
const reg = useRegistryStore()

const visible = computed({
  get: () => ui.registryOpen,
  set: (v) => (ui.registryOpen = v),
})

const TABS = [
  { name: 'skills', label: '技能', icon: Collection, comp: SkillCenter },
  { name: 'mcp', label: 'MCP', icon: Connection, comp: McpCenter },
  { name: 'knowledge', label: '知识库', icon: FolderOpened, comp: KbCenter },
  { name: 'experts', label: '专家', icon: User, comp: ExpertCenter },
]

onMounted(() => {
  // 抽屉打开即并拉四类，供各 tab 即时可用；单类失败不拖垮其余（store 内 try/catch）
  reg.ensureLoaded()
})
</script>

<template>
  <el-drawer v-model="visible" title="注册中心" size="660px" append-to-body class="reg-drawer">
    <el-tabs v-model="ui.activeRegistryTab" tab-position="left" class="reg-tabs">
      <el-tab-pane v-for="t in TABS" :key="t.name" :name="t.name">
        <template #label>
          <span class="reg-tab-label">
            <el-icon><component :is="t.icon" /></el-icon>
            <span>{{ t.label }}</span>
          </span>
        </template>
        <div class="reg-center">
          <component :is="t.comp" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-drawer>
</template>

<style scoped>
/* 抽屉内部占满，center 在各自容器内滚动，避免整页滚动错位 */
.reg-tabs { height: 100%; }
.reg-tabs :deep(.el-tabs__content) { height: 100%; }
.reg-tabs :deep(.el-tab-pane) { height: 100%; }
.reg-center { height: 100%; min-width: 0; }
.reg-tab-label { display: inline-flex; align-items: center; gap: 6px; }
.reg-tab-label :deep(.el-icon) { font-size: 15px; }
</style>

<style>
/* 作用于 append-to-body 的抽屉本体（非 scoped 也能命中，放在组件作用域外）
   body 收边距并成 flex 列；tabs 撑满剩余高度，各 center 在自身容器内滚动 */
.reg-drawer .el-drawer__body { padding: 8px 12px 12px 4px; overflow: hidden; display: flex; flex-direction: column; }
.reg-drawer .el-tabs { flex: 1 1 auto; min-height: 0; }
</style>
