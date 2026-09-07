<script setup>
// 设置抽屉「模型供应商」区（多个供应商 + 各自密钥 + 默认模型 的增删改）。
// 安全口径（design D2 / crypto.mask_key）：明文密钥仅在此输入时出现（password 输入 + 眼睛可回看刚输入的明文），
// 落库即 Fernet 加密；出口永远只回掩码 ****xxxx（末4位）。已存密钥不回看完整明文——
// 编辑时输入框留空=保持不变，填入新值=覆盖；展示位只挂掩码。
// 变更经 model store 收口并 force 重拉 providers，让细节栏供应商下拉/已绑信息即时一致。
import { Delete, EditPen, Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import { PROVIDER_TYPE_META, metaOf } from '../../constants'
import { useModelStore } from '../../stores/model'

const model = useModelStore()

// 供应商 type 取值白名单（与 backend/models.MODEL_PROVIDER_TYPES 一致）
const TYPE_OPTIONS = Object.keys(PROVIDER_TYPE_META)
const typeLabel = (t) => metaOf(PROVIDER_TYPE_META, t).label

// —— 列表 ——
onMounted(() => {
  model.fetchProviders({ force: false })
})

// —— 新建/编辑 对话框 ——
const dialogOpen = ref(false)
const editing = ref(null) // null=新建；否则为 {id, api_key 掩码} 行，用于「留空不改」提示
const saving = ref(false)
const form = reactive({ name: '', type: 'openai', base_url: '', default_model: '', api_key: '' })

function openNew() {
  editing.value = null
  form.name = ''
  form.type = 'openai'
  form.base_url = ''
  form.default_model = ''
  form.api_key = ''
  dialogOpen.value = true
}
function openEdit(p) {
  editing.value = p
  form.name = p.name
  form.type = p.type
  form.base_url = p.base_url || ''
  form.default_model = p.default_model || ''
  form.api_key = '' // 绝不回填密钥；留空=保留原密文
  dialogOpen.value = true
}

async function save() {
  const payload = {
    name: form.name.trim(),
    type: form.type,
    base_url: form.base_url.trim(),
    default_model: form.default_model.trim(),
  }
  // 只在新密钥非空时携带；编辑留空则不提交该字段（后端保留原密文）
  if (form.api_key.trim()) payload.api_key = form.api_key.trim()
  saving.value = true
  try {
    if (editing.value) {
      await model.updateProvider(editing.value.id, payload)
      ElMessage.success('供应商已更新')
    } else {
      await model.createProvider(payload)
      ElMessage.success('供应商已创建')
    }
    dialogOpen.value = false
  } catch {
    // 校验/重复 name 等错误由 http 拦截器统一提示；保留对话框便于修正
  } finally {
    saving.value = false
  }
}

async function remove(p) {
  try {
    await model.removeProvider(p.id)
    ElMessage.success('供应商已删除')
  } catch {
    // 被任务绑定 → 400 由拦截器提示（防悬空绑定）
  }
}
</script>

<template>
  <div class="mpv">
    <!-- 空态 / 骨架 -->
    <el-skeleton v-if="model.providersLoading && !model.providers.length" :rows="2" animated />
    <div v-else-if="!model.providers.length" class="mpv-empty">
      <div class="text-dim">还没有模型供应商。</div>
      <div class="mpv-empty-tip">点「新建供应商」填入 base_url 与 API Key（密钥加密落库，展示仅掩码）。</div>
      <el-button type="primary" size="small" :icon="Plus" @click="openNew">新建供应商</el-button>
    </div>

    <!-- 供应商列表 -->
    <template v-else>
      <div class="mpv-head">
        <span class="mpv-count text-dim">{{ model.providers.length }} 个供应商</span>
        <el-button class="mpv-add" type="primary" size="small" :icon="Plus" @click="openNew">新建</el-button>
      </div>
      <div class="mpv-list">
        <div v-for="p in model.providers" :key="p.id" class="mpv-item">
          <div class="mpv-item-main">
            <div class="mpv-name-row">
              <span class="mpv-name ellipsis">{{ p.name }}</span>
              <el-tag size="small" :type="metaOf(PROVIDER_TYPE_META, p.type).type" effect="plain">
                {{ typeLabel(p.type) }}
              </el-tag>
            </div>
            <div class="mpv-meta text-dim ellipsis">
              {{ p.base_url }}<template v-if="p.default_model"> · 默认 {{ p.default_model }}</template>
            </div>
          </div>
          <div class="mpv-item-side">
            <!-- 密钥展示：后端掩码（****末4位）；无 key 置灰占位 -->
            <el-tooltip v-if="p.api_key" :content="`密钥掩码 ${p.api_key}`" placement="top">
              <code class="mpv-key">{{ p.api_key }}</code>
            </el-tooltip>
            <span v-else class="mpv-key mpv-key-none text-dim">未配置密钥</span>
            <el-button class="mpv-act" text size="small" :icon="EditPen" title="编辑" @click="openEdit(p)" />
            <el-popconfirm
              :title="`删除供应商「${p.name}」？`"
              confirm-button-text="删除"
              cancel-button-text="取消"
              confirm-button-type="danger"
              width="240"
              @confirm="remove(p)"
            >
              <template #reference>
                <el-button class="mpv-act mpv-del" text size="small" :icon="Delete" title="删除" />
              </template>
            </el-popconfirm>
          </div>
        </div>
      </div>
    </template>

    <!-- 新建/编辑 对话框 -->
    <el-dialog
      v-model="dialogOpen"
      :title="editing ? `编辑供应商 ${editing.name}` : '新建供应商'"
      width="460px"
      append-to-body
    >
      <el-form label-position="top" size="default" @submit.prevent="save">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如 deepseek / ccswitch-v2（唯一，标识密钥来源）" />
        </el-form-item>
        <el-form-item label="类型" required>
          <el-select v-model="form.type" style="width: 100%">
            <el-option v-for="t in TYPE_OPTIONS" :key="t" :label="typeLabel(t)" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL（OpenAI 兼容端点）" required>
          <el-input v-model="form.base_url" placeholder="https://api.deepseek.com/v1" />
        </el-form-item>
        <el-form-item label="默认模型">
          <el-input v-model="form.default_model" placeholder="如 deepseek-chat；任务绑定未填模型名时用它" />
        </el-form-item>
        <el-form-item label="API Key">
          <!-- password + show-password：输入时圆点掩码、点眼睛可看刚输入的明文；绝不回显已存密文 -->
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="editing ? '留空保持不变；输入新密钥即覆盖' : '粘贴密钥（Fernet 加密后仅存后端）'"
          />
          <div v-if="editing" class="mpv-hint">
            <template v-if="editing.api_key">当前密钥 {{ editing.api_key }}（不回看完整明文）</template>
            <template v-else>当前未配置密钥，填入即保存。</template>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ editing ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.mpv-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.mpv-count {
  font-size: 12px;
}
.mpv-add {
  font-size: 12px;
}
.mpv-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.mpv-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--ls-border);
  border-radius: 8px;
  background: var(--ls-panel);
  min-width: 0;
}
.mpv-item-main {
  flex: 1 1 auto;
  min-width: 0;
}
.mpv-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.mpv-name {
  font-size: 13px;
  font-weight: 600;
}
.mpv-meta {
  font-size: 11.5px;
  margin-top: 2px;
}
.mpv-item-side {
  flex: none;
  display: flex;
  align-items: center;
  gap: 2px;
}
.mpv-key {
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 11.5px;
  color: var(--ls-fg-dim);
  background: rgba(127, 143, 166, 0.12);
  border-radius: 4px;
  padding: 2px 6px;
  margin-right: 2px;
}
.mpv-key-none {
  background: transparent;
  padding: 2px 0;
}
.mpv-act {
  height: auto;
  padding: 2px;
  font-size: 14px;
}
.mpv-del {
  color: var(--ls-fg-dim);
}
.mpv-del:hover {
  color: #f56c6c;
}
.mpv-empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  font-size: 13px;
}
.mpv-empty-tip {
  font-size: 12px;
  color: var(--ls-fg-dim);
  margin-bottom: 4px;
}
.mpv-hint {
  font-size: 11.5px;
  color: var(--ls-fg-dim);
  margin-top: 4px;
}
</style>
