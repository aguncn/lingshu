<script setup>
// 右栏（design D2 / §4.4 三段）：中部会话+文件/时间线 → 底部细节栏 + 输入框。
// C5：顶部「场景域」快捷条（TemplateBar）已随十二场景域体系一并移除。
import ChatPane from './ChatPane.vue'
import DetailDock from './DetailDock.vue'
import PromptInput from './PromptInput.vue'
</script>

<template>
  <div class="rp">
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
