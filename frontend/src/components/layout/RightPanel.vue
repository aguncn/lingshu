<script setup>
// 右栏（design D2 / §4.4 三段）：顶部模板条 → 中部会话+文件/时间线 → 底部细节栏 + 输入框。
import ChatPane from './ChatPane.vue'
import DetailDock from './DetailDock.vue'
import PromptInput from './PromptInput.vue'
import TemplateBar from './TemplateBar.vue'
</script>

<template>
  <div class="rp">
    <TemplateBar />
    <ChatPane />
    <DetailDock />
    <PromptInput />
  </div>
</template>

<style scoped>
.rp {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
</style>
