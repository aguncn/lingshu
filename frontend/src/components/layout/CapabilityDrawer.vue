<script setup>
// 左栏能力导航占位抽屉（spec R1 场景2 / task 2.4）：主导航（专家·技能·MCP / 自动化 /
// 资料库）点击打开，后端 P4~P6 交付前显示稳定空态与阶段说明，不发起网络请求、不报错。
import { computed } from 'vue'

import { useUiStore } from '../../stores/ui'
import EmptyState from '../common/EmptyState.vue'

const ui = useUiStore()

const visible = computed({
  get: () => ui.capabilityOpen,
  set: (v) => (ui.capabilityOpen = v),
})
</script>

<template>
  <el-drawer v-model="visible" title="能力导航" size="400px" append-to-body>
    <template v-if="ui.capability.title">
      <div class="cap-head">
        <span class="cap-title">{{ ui.capability.title }}</span>
        <el-tag v-if="ui.capability.phase" size="small" type="info" effect="plain">
          {{ ui.capability.phase }}
        </el-tag>
      </div>
      <EmptyState
        :description="`${ui.capability.title} 后端未交付`"
        :tip="ui.capability.desc || '对应后端能力交付后由该提案回填数据源'"
      />
    </template>
  </el-drawer>
</template>

<style scoped>
.cap-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.cap-title {
  font-size: 15px;
  font-weight: 600;
}
</style>
