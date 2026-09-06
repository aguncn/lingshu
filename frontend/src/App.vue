<script setup>
// 根组件：只承载路由出口 + 命令面板。
// 命令面板放这里而非 Workbench：它自己注册 Ctrl/Cmd+K 全局键（design D1），
// 这样即使将来新增 /health 之类非工作台路由，快捷键依旧全局生效。
import CommandPalette from './components/common/CommandPalette.vue'
</script>

<template>
  <router-view />
  <CommandPalette />
</template>
