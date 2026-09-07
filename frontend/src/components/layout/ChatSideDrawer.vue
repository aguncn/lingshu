<script setup>
// C3 右侧抽屉薄壳：聊天区头部「文件 / 时间线」按钮共用一个右抽屉，标题区分。
// 内联组件自带区段标题与滚动（FileTree bare / TimelinePanel），故 body 去 padding、子级撑满。
// append-to-body 用 teleport：抽屉 DOM 在 body 下，组件级（非 scoped）样式以根类限定避免泄漏。
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})
</script>

<template>
  <el-drawer
    v-model="open"
    class="csd-drawer"
    :title="title"
    direction="rtl"
    size="min(460px, 92vw)"
    append-to-body
  >
    <div class="csd"><slot /></div>
  </el-drawer>
</template>

<style>
/* drawer teleport 到 body，scoped 到不了库内部节点 → 用带类作用域的非 scoped 规则限定本抽屉 */
.csd-drawer .el-drawer__body {
  padding: 0;
  display: flex;
  flex-direction: column;
}
.csd-drawer .el-drawer__body .csd {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  width: 100%;
}
</style>
