<script setup>
// 首页（脚手架联调页）：挂载时探测后端健康状态并展示。
// 三种状态：loading 检测中 / ok 后端就绪 / down 后端不可达（页面不白屏，可手动重试）。
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'

import { getHealth } from '../api/health'

const status = ref('loading') // 'loading' | 'ok' | 'down'
const ts = ref('')

async function checkHealth() {
  status.value = 'loading'
  try {
    const data = await getHealth()
    if (data?.ok) {
      status.value = 'ok'
      ts.value = data.ts
    } else {
      status.value = 'down'
    }
  } catch {
    // 拦截器已弹 ElMessage，这里只置状态避免页面空白
    status.value = 'down'
  }
}

onMounted(checkHealth)

function retry() {
  checkHealth()
  ElMessage.info('正在重新探测后端…')
}
</script>

<template>
  <el-container class="home-shell">
    <el-main>
      <el-card class="home-card">
        <template #header>
          <span class="home-title">灵枢 · IT 运维智能体平台</span>
        </template>

        <div class="health-block">
          <template v-if="status === 'loading'">
            <el-tag type="info" effect="dark">正在检测后端…</el-tag>
          </template>

          <template v-else-if="status === 'ok'">
            <el-tag type="success" effect="dark" size="large">后端就绪</el-tag>
            <div class="health-ts">{{ ts }}</div>
          </template>

          <template v-else>
            <el-alert
              title="后端不可达"
              type="error"
              :closable="false"
              description="请确认已运行：uv run flask --app backend.app run --port 5000"
              show-icon
            />
          </template>
        </div>

        <el-button class="home-retry" v-if="status !== 'loading'" @click="retry">
          重新探测
        </el-button>
      </el-card>
    </el-main>
  </el-container>
</template>

<style scoped>
.home-shell {
  min-height: 100vh;
}
.home-card {
  max-width: 640px;
  margin: 80px auto;
}
.home-title {
  font-weight: 600;
}
.health-block {
  min-height: 72px;
}
.health-ts {
  margin-top: 12px;
  color: #909399;
  font-size: 13px;
}
.home-retry {
  margin-top: 16px;
}
</style>
