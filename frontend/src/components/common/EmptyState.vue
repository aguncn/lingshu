<script setup>
// 统一空态：el-empty + 主文案 + 次要说明 + 可选「重试」，全站 P4~P6 占位复用（design D2）。
defineProps({
  description: { type: String, default: '暂无内容' },
  tip: { type: String, default: '' },
  imageSize: { type: Number, default: 60 },
  retry: { type: Boolean, default: false }, // 置 true 时显示重试按钮（点触发 retry 事件）
})
defineEmits(['retry'])
</script>

<template>
  <div class="ls-empty">
    <el-empty :image-size="imageSize">
      <template #description>
        <div class="ls-empty-desc">{{ description }}</div>
        <div v-if="tip" class="ls-empty-tip">{{ tip }}</div>
        <div class="ls-empty-extra">
          <slot />
          <el-button v-if="retry" size="small" @click="$emit('retry')">重试</el-button>
        </div>
      </template>
    </el-empty>
  </div>
</template>

<style scoped>
.ls-empty {
  padding: 6px 0;
}
.ls-empty-desc {
  font-size: 13px;
  color: var(--ls-fg-dim);
}
.ls-empty-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--ls-fg-dim);
  opacity: 0.8;
  line-height: 1.5;
}
.ls-empty-extra {
  margin-top: 6px;
}
</style>
