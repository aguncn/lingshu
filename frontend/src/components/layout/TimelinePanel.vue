<script setup>
// C3 时间线抽屉内容：本任务「用户输入问题」的时间线（升序）。点任一条 → 通知 ChatPane
// 定位滚动到对应提问气泡（锚点 = 消息稳定标识，见 ChatPane.bubbleAnchor）。只列提问不列回复。
import EmptyState from '../common/EmptyState.vue'

defineProps({
  items: { type: Array, default: () => [] }, // [{ anchor, time, text }]
})
defineEmits(['locate'])
</script>

<template>
  <div class="tp">
    <EmptyState
      v-if="!items.length"
      description="暂无输入问题"
      tip="发出问题后，这里会按时间列出你提出的每个问题；点击可回到聊天对应位置"
    />
    <ul v-else class="tp-list">
      <li
        v-for="(it, i) in items"
        :key="it.anchor || `idx-${i}`"
        class="tp-item"
        @click="$emit('locate', it)"
      >
        <span class="tp-idx">{{ i + 1 }}</span>
        <div class="tp-main">
          <span class="tp-time">{{ it.time || '—' }}</span>
          <span class="tp-text">{{ it.text }}</span>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.tp {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 12px 16px;
}
.tp-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.tp-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 8px;
  border-radius: 8px;
  cursor: pointer;
  border-bottom: 1px dashed var(--ls-border);
}
.tp-item:last-child {
  border-bottom: none;
}
.tp-item:hover {
  background: var(--ls-bg-hover, rgba(63, 126, 247, 0.08));
}
.tp-idx {
  flex: none;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  background: var(--ls-accent);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
}
.tp-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.tp-time {
  font-size: 11px;
  color: var(--ls-fg-dim);
}
.tp-text {
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
