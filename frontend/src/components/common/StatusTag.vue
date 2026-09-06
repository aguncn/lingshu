<script setup>
// 任务状态徽标：status(open/in_progress/done) → ElTag 类型样式（spec R3 / D7）。
import { computed } from 'vue'

import { STATUS_META, metaOf } from '../../constants'

const props = defineProps({
  value: { type: String, default: '' },
})

const meta = computed(() => metaOf(STATUS_META, props.value))
</script>

<template>
  <el-tag :type="meta.type" size="small" effect="plain">{{ meta.label }}</el-tag>
</template>
