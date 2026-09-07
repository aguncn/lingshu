<script setup>
// 设置抽屉（spec R9 / task 4.2）：模型供应商管理（多供应商+密钥掩码）+ 外观（暗色）+ 后端探活。
// 模型供应商 CRUD 在 ModelProvidersPanel：密钥只掩码展示、不回看完整明文（见组件注释）。
// 探活以 silent 请求进行：后端不可达时本页显示状态而不弹全局错误（由视图承接）。
import { Monitor, RefreshRight, Sunny } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'

import { getHealth } from '../../api/health'
import { useUiStore } from '../../stores/ui'
import ModelProvidersPanel from './ModelProvidersPanel.vue'

const ui = useUiStore()

const visible = computed({
  get: () => ui.settingsOpen,
  set: (v) => (ui.settingsOpen = v),
})

const health = ref({ state: 'idle', ts: '' }) // idle | checking | ok | down

async function checkHealth() {
  health.value = { state: 'checking', ts: '' }
  try {
    const data = await getHealth({ silent: true })
    health.value = { state: data?.ok ? 'ok' : 'down', ts: data?.ts || '' }
  } catch {
    health.value = { state: 'down', ts: '' }
  }
}

onMounted(() => {
  if (ui.settingsOpen) checkHealth()
})
</script>

<template>
  <el-drawer v-model="visible" class="set-drawer" title="设置" size="480px" append-to-body @open="checkHealth">
    <!-- 模型供应商：多供应商 + 各自密钥，改完细节栏供应商下拉即时一致 -->
    <section class="set-sec">
      <h4 class="set-title">模型供应商</h4>
      <ModelProvidersPanel />
    </section>

    <section class="set-sec">
      <h4 class="set-title">外观</h4>
      <div class="set-row">
        <el-icon><Sunny /></el-icon>
        <span>暗色模式</span>
        <el-switch
          class="set-switch"
          :model-value="ui.dark"
          @update:model-value="ui.setDark"
        />
      </div>
      <p class="set-hint">切换即时生效并持久化到本地（刷新页面保持）</p>
    </section>

    <section class="set-sec">
      <h4 class="set-title">后端</h4>
      <div class="set-row">
        <el-icon><Monitor /></el-icon>
        <span>探活 /api/health</span>
        <el-button link :icon="RefreshRight" @click="checkHealth">重测</el-button>
      </div>
      <el-alert
        v-if="health.state === 'ok'"
        type="success"
        :closable="false"
        show-icon
        :title="`后端就绪 · ${health.ts}`"
      />
      <el-alert
        v-else-if="health.state === 'down'"
        type="error"
        :closable="false"
        show-icon
        title="后端不可达"
        description="请运行：uv run flask --app backend.app run --port 5000"
      />
      <el-skeleton v-else-if="health.state === 'checking'" :rows="1" animated />
      <p v-else class="set-hint">打开抽屉后自动探测后端健康状态</p>
    </section>
  </el-drawer>
</template>

<style scoped>
.set-sec {
  margin-bottom: 20px;
}
.set-title {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ls-fg-dim);
}
.set-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
}
.set-switch {
  margin-left: auto;
}
.set-hint {
  font-size: 12px;
  color: var(--ls-fg-dim);
  margin: 4px 0 0;
}
</style>

<style>
/* 设置抽屉 teleport 到 body，scoped 到不了 body 下节点 → 用带类作用域的非 scoped 规则让它能滚动（供应商多时） */
.set-drawer .el-drawer__body {
  overflow-y: auto;
}
</style>
