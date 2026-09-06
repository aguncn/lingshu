<script setup>
// 细节栏「模型」分区（spec R6 / task 3.4 / D8）：真实联调 P3——
// 供应商下拉来自 /api/model-providers（掩码密钥展示），
// 绑定/替换走 POST /api/tasks/<id>/model-config，调参走 PATCH；回显最新参数。
import { ElMessage } from 'element-plus'
import { computed, reactive, watch } from 'vue'

import { PROVIDER_TYPE_META, metaOf } from '../../constants'
import { useModelStore } from '../../stores/model'
import { useTaskStore } from '../../stores/task'
import EmptyState from '../common/EmptyState.vue'

const model = useModelStore()
const task = useTaskStore()

const activeTaskId = computed(() => task.activeTaskId)
const config = computed(() => model.config)

// 表单默认：temperature 1.0 / timeout 60（对齐后端 ModelConfig 默认值）
const form = reactive({
  provider_id: null,
  model_name: '',
  temperature: 1.0,
  max_tokens: null,
  timeout: 60,
})

const chosenProvider = computed(() =>
  form.provider_id ? model.providerById(form.provider_id) : null,
)
const boundProvider = computed(() =>
  config.value ? model.providerById(config.value.provider_id) : null,
)

function resetFromDefault() {
  const first = model.providers[0]
  form.provider_id = first ? first.id : null
  form.model_name = ''
  form.temperature = config.value ? config.value.temperature ?? 1.0 : 1.0
  form.max_tokens = config.value ? config.value.max_tokens ?? null : null
  form.timeout = config.value ? config.value.timeout ?? 60 : 60
}

// 加载到的绑定写入表单；切换任务时 loadConfig 会置 config=null/新值
watch(config, (cfg) => {
  if (cfg) {
    form.provider_id = cfg.provider_id
    form.model_name = cfg.model_name || ''
    form.temperature = cfg.temperature ?? 1.0
    form.max_tokens = cfg.max_tokens ?? null
    form.timeout = cfg.timeout ?? 60
  } else if (form.provider_id == null) {
    resetFromDefault()
  }
}, { immediate: true })

// 供应商列表就绪且尚未选过 → 默认取第一个
watch(() => model.providers.length, (n) => {
  if (n > 0 && form.provider_id == null) resetFromDefault()
})

// 切换供应商时若模型名未填且新供应商有 default_model，落到 placeholder 即可（不覆盖用户输入）
const defaultModel = computed(() => chosenProvider.value?.default_model || '')

async function save() {
  if (!activeTaskId.value || !form.provider_id) return
  const payload = { provider_id: form.provider_id }
  const name = form.model_name.trim()
  if (name) payload.model_name = name
  if (form.temperature != null && form.temperature !== '') payload.temperature = Number(form.temperature)
  if (form.max_tokens) payload.max_tokens = Number(form.max_tokens)
  if (form.timeout != null && form.timeout !== '') payload.timeout = Number(form.timeout)
  try {
    await model.saveConfig(activeTaskId.value, payload)
  } catch {
    // 失败提示由 http 拦截器统一弹出；不打断表单以允许重试
  }
}

function copyDefault() {
  if (defaultModel.value) {
    form.model_name = defaultModel.value
    ElMessage.info('已填入供应商默认模型')
  }
}

const providerTypeLabel = (p) => (p ? metaOf(PROVIDER_TYPE_META, p.type).label : '')
</script>

<template>
  <div class="mp">
    <!-- 未选任务 / 无供应商 → 引导态 -->
    <EmptyState
      v-if="!activeTaskId"
      description="选择任务后绑定模型"
      image-size="48"
    />
    <EmptyState
      v-else-if="!model.providersLoading && !model.providers.length"
      description="尚无模型供应商"
      tip="请经后端接口 POST /api/model-providers 先配置（密钥 Fernet 加密落库）"
      retry
      @retry="model.fetchProviders({ force: true })"
    />

    <template v-else>
      <!-- 已绑定信息 -->
      <div v-if="config && boundProvider" class="mp-bound">
        <el-tag type="success" size="small" effect="light">已绑定</el-tag>
        <span class="mp-bound-name">{{ boundProvider.name }}</span>
        <span class="mp-bound-meta text-dim">{{ providerTypeLabel(boundProvider) }}</span>
        <el-tooltip :content="`掩码密钥 ${boundProvider.api_key || '（未配置）'}`" placement="top">
          <span class="mp-mask text-dim">{{ boundProvider.api_key || '无密钥' }}</span>
        </el-tooltip>
      </div>

      <el-form label-position="top" size="small" class="mp-form" @submit.prevent="save">
        <el-form-item label="供应商">
          <el-select v-model="form.provider_id" style="width: 100%" :loading="model.providersLoading">
            <el-option v-for="p in model.providers" :key="p.id" :value="p.id">
              <span>{{ p.name }}</span>
              <span class="text-dim mp-opt-sub">（{{ providerTypeLabel(p) }} · {{ p.base_url }}）</span>
            </el-option>
          </el-select>
        </el-form-item>

        <template v-if="chosenProvider">
          <el-form-item label="供应商信息">
            <div class="mp-prov-info text-dim">
              <div>类型 {{ providerTypeLabel(chosenProvider) }} · base_url {{ chosenProvider.base_url }}</div>
              <div>
                默认模型 {{ chosenProvider.default_model || '—' }} ·
                <el-tooltip content="密钥经 Fernet 加密后仅存后端，接口只回掩码" placement="top">
                  <span>密钥 {{ chosenProvider.api_key || '未配置' }}</span>
                </el-tooltip>
              </div>
            </div>
          </el-form-item>
        </template>

        <el-form-item label="模型名">
          <el-input
            v-model="form.model_name"
            :placeholder="defaultModel || '留空则用供应商默认模型'"
          >
            <template v-if="defaultModel" #append>
              <el-button :disabled="!!form.model_name" @click="copyDefault">默认</el-button>
            </template>
          </el-input>
        </el-form-item>

        <div class="mp-params">
          <el-form-item label="temperature">
            <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" :controls="false" size="small" style="width: 100%" />
          </el-form-item>
          <el-form-item label="max_tokens">
            <el-input-number v-model="form.max_tokens" :min="1" :step="256" :controls="false" size="small" placeholder="默认" style="width: 100%" />
          </el-form-item>
          <el-form-item label="timeout(s)">
            <el-input-number v-model="form.timeout" :min="1" :step="10" :controls="false" size="small" style="width: 100%" />
          </el-form-item>
        </div>

        <el-button
          type="primary"
          size="small"
          :loading="model.saving"
          :disabled="!form.provider_id"
          @click="save"
        >
          {{ config ? '保存调参' : '绑定模型' }}
        </el-button>
      </el-form>
    </template>
  </div>
</template>

<style scoped>
.mp-bound {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 12px;
}
.mp-bound-name {
  font-weight: 600;
}
.mp-mask {
  font-size: 11px;
}
.mp-opt-sub {
  font-size: 11px;
  margin-left: 4px;
}
.mp-prov-info {
  font-size: 11.5px;
  line-height: 1.7;
}
.mp-params {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
}
.mp-form :deep(.el-form-item) {
  margin-bottom: 8px;
}
</style>
