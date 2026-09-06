<script setup>
// 专家中心（P5 AD-04）：列表 + 新建/编辑（role / system_prompt / composed_of 协作子专家）。
// composed_of 只允许选「其他」专家（排除自身，自指由后端校验兜底）；空=单专家，供 P1 多专家编排。
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import { createExpert, removeExpert, updateExpert } from '../../api/experts'
import { EXPERT_ROLE_META, metaOf } from '../../constants'
import { useRegistryStore } from '../../stores/registry'

const reg = useRegistryStore()
const list = computed(() => reg.experts)

const dialogOpen = ref(false)
const editingId = ref(null)
const saving = ref(false)

const form = reactive({
  name: '', description: '', system_prompt: '', role: 'general', composedOf: [], enabled: true,
})

function roleMeta(r) { return metaOf(EXPERT_ROLE_META, r) }

// 可选协作子专家：除自身外的全部专家（composed 字段只存 id 数组）
const candidates = computed(() => {
  const self = editingId.value
  return list.value.filter((x) => x.id !== self)
})

function openNew() {
  editingId.value = null
  Object.assign(form, {
    name: '', description: '', system_prompt: '', role: 'general', composedOf: [], enabled: true,
  })
  dialogOpen.value = true
}

function openEdit(ex) {
  editingId.value = ex.id
  form.name = ex.name || ''
  form.description = ex.description || ''
  form.system_prompt = ex.system_prompt || ''
  form.role = ex.role || 'general'
  form.composedOf = Array.isArray(ex.composed_of) ? ex.composed_of.slice() : []
  form.enabled = !!ex.enabled
  dialogOpen.value = true
}

// id → 名称解析（子专家也许在列表之外被删，兜底显示 #id）
function childName(id) {
  const child = list.value.find((x) => x.id === id)
  return child ? child.name : `#${id}`
}

async function submit() {
  if (!form.name.trim()) { ElMessage.warning('name 不能为空'); return }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      system_prompt: form.system_prompt,
      role: form.role,
      composed_of: form.composedOf,
      enabled: form.enabled,
    }
    if (editingId.value === null) await createExpert(payload)
    else await updateExpert(editingId.value, payload)
    ElMessage.success(editingId.value === null ? '专家已创建' : '专家已更新')
    dialogOpen.value = false
    await reg.loadCategory('experts')
  } catch { /* 拦截器已提示 */ } finally {
    saving.value = false
  }
}

async function toggleEnabled(ex) {
  try {
    await updateExpert(ex.id, { enabled: !ex.enabled })
    await reg.loadCategory('experts')
  } catch { /* 拦截器已提示 */ }
}

async function onDelete(ex) {
  try {
    await ElMessageBox.confirm(
      `删除专家「${ex.name}」后，相关任务挂载与协作关系将一并清理。确定删除？`,
      '删除专家',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await removeExpert(ex.id)
    ElMessage.success('专家已删除')
    await reg.loadCategory('experts')
  } catch { /* 拦截器已提示 */ }
}
</script>

<template>
  <div class="rc">
    <div class="rc-head">
      <span class="rc-title">专家库</span>
      <span v-if="list.length" class="rc-count">{{ list.length }}</span>
      <el-button class="rc-add" size="small" type="primary" :icon="Plus" @click="openNew">
        新建专家
      </el-button>
    </div>

    <div v-loading="reg.loading" class="rc-body">
      <el-empty v-if="!reg.loading && !list.length" description="暂无专家" :image-size="64">
        <el-button size="small" type="primary" @click="openNew">创建第一位专家</el-button>
      </el-empty>

      <div v-else class="rc-list">
        <div v-for="ex in list" :key="ex.id" class="rc-item">
          <div class="rc-item-main no-btn">
            <div class="rc-txt">
              <div class="rc-line1">
                <span class="rc-name">{{ ex.name }}</span>
                <el-tag size="small" effect="plain" :type="roleMeta(ex.role).type">
                  {{ roleMeta(ex.role).label }}
                </el-tag>
                <el-tag size="small" :type="ex.enabled ? 'success' : 'info'">
                  {{ ex.enabled ? '启用' : '停用' }}
                </el-tag>
              </div>
              <div v-if="ex.description" class="rc-sub">{{ ex.description }}</div>
              <div v-if="Array.isArray(ex.composed_of) && ex.composed_of.length" class="rc-sub">
                协作：{{ ex.composed_of.map(childName).join(' + ') }}
              </div>
            </div>
          </div>
          <div class="rc-ops">
            <el-switch size="small" :model-value="!!ex.enabled" @change="toggleEnabled(ex)" />
            <el-button text size="small" @click="openEdit(ex)">编辑</el-button>
            <el-button text size="small" type="danger" @click="onDelete(ex)">删除</el-button>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialogOpen" :title="editingId === null ? '新建专家' : '编辑专家'" width="560px" append-to-body>
      <el-form label-width="92px" label-position="left">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="128" placeholder="如：db-ops-sme" />
        </el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="form.role">
            <el-radio-button value="ops-sme">运维专家</el-radio-button>
            <el-radio-button value="general">通用</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" maxlength="512" placeholder="一句话说明专长边界（可选）" />
        </el-form-item>
        <el-form-item label="人设">
          <el-input v-model="form.system_prompt" type="textarea" :rows="5" placeholder="人设与工作流程；多专家编排时作为系统提示注入" />
        </el-form-item>
        <el-form-item label="协作子专家">
          <el-select v-model="form.composedOf" multiple clearable filterable placeholder="空=单专家">
            <el-option v-for="c in candidates" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.rc { display: flex; flex-direction: column; height: 100%; min-width: 0; }
.rc-head { display: flex; align-items: center; gap: 8px; padding: 2px 2px 10px; }
.rc-title { font-size: 13px; font-weight: 600; }
.rc-count { font-size: 11px; color: var(--ls-fg-dim); background: rgba(127,132,148,.18); border-radius: 999px; padding: 0 6px; }
.rc-add { margin-left: auto; }
.rc-body { flex: 1 1 auto; min-height: 0; overflow-y: auto; }
.rc-list { display: flex; flex-direction: column; gap: 4px; }
.rc-item { border: 1px solid var(--ls-border); border-radius: 8px; background: var(--ls-bg); padding: 9px 10px 8px; }
.rc-item-main.no-btn { display: flex; }
.rc-txt { flex: 1 1 auto; min-width: 0; }
.rc-line1 { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.rc-name { font-size: 13px; font-weight: 600; }
.rc-sub { font-size: 12px; color: var(--ls-fg-dim); margin-top: 2px; }
.rc-ops { display: flex; align-items: center; gap: 2px; margin-top: 6px; flex-wrap: wrap; }
</style>
