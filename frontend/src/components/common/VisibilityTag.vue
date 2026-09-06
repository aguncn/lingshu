<script setup>
// 可见性徽标：visibility(private/team/public) → ElTag 类型样式（spec R3 / D7）。
import { computed } from 'vue'

import { VISIBILITY_META, metaOf } from '../../constants'

const props = defineProps({
  value: { type: String, default: '' },
})

const meta = computed(() => metaOf(VISIBILITY_META, props.value))
</script>

<template>
  <el-tag :type="meta.type" size="small" effect="plain">{{ meta.label }}</el-tag>
</template>
