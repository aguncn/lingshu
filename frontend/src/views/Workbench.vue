<script setup>
// 三栏工业风工作台（spec R1 / design D1/D2）：左栏控制台 + 右栏三段式；
// 抽屉（注册中心/资料库/设置/能力占位）作为工作台 chrome 挂这里，不设独立路由。
import CapabilityDrawer from '../components/layout/CapabilityDrawer.vue'
import LeftPanel from '../components/layout/LeftPanel.vue'
import LibraryDrawer from '../components/layout/LibraryDrawer.vue'
import RegistryDrawer from '../components/layout/RegistryDrawer.vue'
import RightPanel from '../components/layout/RightPanel.vue'
import SettingsDrawer from '../components/layout/SettingsDrawer.vue'
</script>

<template>
  <el-container class="wb-root">
    <el-aside width="290px" class="wb-left">
      <LeftPanel />
    </el-aside>

    <el-main class="wb-main">
      <RightPanel />
    </el-main>

    <!-- 浮层抽屉：由 store 统一开关（命令面板/底部入口共用） -->
    <CapabilityDrawer />
    <LibraryDrawer />
    <RegistryDrawer />
    <SettingsDrawer />
  </el-container>
</template>

<style scoped>
.wb-root {
  height: 100%;
}
.wb-left {
  background: var(--ls-left-bg);
  border-right: 1px solid var(--ls-left-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.wb-main {
  padding: 0;
  background: var(--ls-bg);
  overflow: hidden;
  display: flex;
}
.wb-main > :deep(*) {
  flex: 1;
  min-width: 0;
}
</style>
