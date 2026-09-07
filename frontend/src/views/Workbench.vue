<script setup>
// 三栏工业风工作台（spec R1 / design D1/D2）：左栏控制台 + 主区；
// 主区整页按 ui.mainView 切换：chat=工作区(RightPanel 会话+细节)｜plaza=能力广场整页。
// C4 退役 注册中心/资料库/能力占位 三个抽屉，入口并入左侧广场导航与主区广场顶栏；
// 设置抽屉保留。CapabilityPlaza 懒挂载：首次进入 plaza 才实例化，之后常驻保持各页状态；
// RightPanel 常驻以保留聊天滚动/草稿（v-show 隐藏而非销毁）。
// —— 左栏宽度：可拖拽分隔条动态调宽（夹在 LEFT_MIN/LEFT_MAX），可整栏折叠（ui.leftCollapsed）。
//    折叠时整栏 + 分隔条让出布局，主区占满；左缘浮出「展开」钮还原。宽度/折叠态均持久化。
import { Expand } from '@element-plus/icons-vue'
import { ref, watch } from 'vue'

import CapabilityPlaza from '../components/layout/CapabilityPlaza.vue'
import LeftPanel from '../components/layout/LeftPanel.vue'
import RightPanel from '../components/layout/RightPanel.vue'
import SettingsDrawer from '../components/layout/SettingsDrawer.vue'
import { useUiStore } from '../stores/ui'

const ui = useUiStore()

// 广场组件懒挂载：首次切到 plaza 置 true 后不再销毁（内部四页各自持有滚动/展开/表单态）
const plazaAlive = ref(false)
watch(
  () => ui.mainView,
  (v) => {
    if (v === 'plaza') plazaAlive.value = true
  },
  { immediate: true },
)

// —— 左栏拖拽调宽：鼠标按住分隔条左右拖，宽度实时夹到 [MIN, MAX] 并持久化 ——
// 用 window 级 pointer 监听，避免拖出分隔条外丢事件；拖拽期加 body 光标与禁用选中。
function beginResize(e) {
  if (ui.leftCollapsed) return
  const startX = e.clientX
  const startW = ui.leftWidth
  const onMove = (ev) => ui.setLeftWidth(startW + (ev.clientX - startX))
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    document.body.classList.remove('ls-resizing')
  }
  document.body.classList.add('ls-resizing')
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}
</script>

<template>
  <div class="wb-root">
    <!-- 左栏：v-if 让折叠时完全让出布局（v-show 的 display:none 不占宽，等价但省 DOM 不用 if 保留内部态，故用 v-show） -->
    <aside v-show="!ui.leftCollapsed" class="wb-left" :style="{ width: ui.leftWidth + 'px' }">
      <LeftPanel />
    </aside>
    <!-- 拖拽分隔条（仅展开态出现） -->
    <div v-if="!ui.leftCollapsed" class="wb-resizer" title="拖拽调整左栏宽度" @mousedown="beginResize" />

    <el-main class="wb-main">
      <RightPanel v-show="ui.mainView !== 'plaza'" />
      <CapabilityPlaza v-if="plazaAlive" v-show="ui.mainView === 'plaza'" />
    </el-main>

    <!-- 折叠时的展开钮：浮在主区左缘顶部，点它还原左栏 -->
    <el-tooltip v-if="ui.leftCollapsed" content="展开导航" placement="right">
      <button type="button" class="wb-expand" @click="ui.setLeftCollapsed(false)">
        <el-icon><Expand /></el-icon>
      </button>
    </el-tooltip>

    <!-- 浮层：设置抽屉（广场/工作区共用） -->
    <SettingsDrawer />
  </div>
</template>

<style scoped>
.wb-root {
  position: relative; /* 展开钮绝对定位的锚 */
  height: 100%;
  display: flex;
  flex-direction: row;
}
.wb-left {
  background: var(--ls-left-bg);
  border-right: 1px solid var(--ls-left-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex: none;
}
/* 分隔条：左缘紧贴左栏右边线（1px border），本身是不可见拖拽热区；hover/拖拽时压一层强调线提示可拖 */
.wb-resizer {
  flex: none;
  width: 5px;
  cursor: col-resize;
  background: transparent;
  position: relative;
}
.wb-resizer::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 1px;
  background: transparent;
}
.wb-resizer:hover::before,
.ls-resizing .wb-resizer::before {
  background: var(--ls-accent);
  width: 3px;
}
.wb-main {
  flex: 1 1 auto;
  min-width: 0;
  padding: 0;
  background: var(--ls-bg);
  overflow: hidden;
  display: flex;
}
.wb-main > :deep(*) {
  flex: 1;
  min-width: 0;
}
/* 折叠态展开钮：悬浮在主区左上，避开常规内容 */
.wb-expand {
  position: absolute;
  left: 8px;
  top: 8px;
  z-index: 20;
  width: 30px;
  height: 30px;
  border: 1px solid var(--ls-border);
  border-radius: 6px;
  background: var(--ls-panel);
  color: var(--ls-fg-dim);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.wb-expand:hover {
  color: var(--ls-accent);
  border-color: var(--ls-accent);
}
</style>
