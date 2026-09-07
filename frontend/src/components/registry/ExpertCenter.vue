<script setup>
// 运维专家中心（P5 AD-04 / C5 expert-profile）：档案组装页。
// 一份「运维专家档案」= 名称/描述/人设(system_prompt) + 预设技能/MCP/RAG(知识库)/资料库(库文件, id 数组)
//   + 可选默认模型（供应商 → model，留空取供应商 default_model）。
// 建任务时可套用档案（快照到任务，见 TaskCreateDialog）；此页只管档案的组装/启停/删除。
// 数据源：reg store 的 experts/skills/mcps/kbs；库文件来自 /api/library；供应商来自 model store。
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { createExpert, removeExpert, updateExpert } from '../../api/experts'
import { listLibrary } from '../../api/library'
import { useModelStore } from '../../stores/model'
import { useRegistryStore } from '../../stores/registry'

const reg = useRegistryStore()
const model = useModelStore()
const list = computed(() => reg.experts)

const libraryRows = ref([]) // 资料库文档（档案预设 library 的候选；跨空间全局候选）
const dialogOpen = ref(false)
const editingId = ref(null) // null=新建；有值=编辑该档案
const saving = ref(false)

const form = reactive({
  name: '',
  description: '',
  system_prompt: '',
  enabled: true,
  preset_skills: [],
  preset_mcp: [],
  preset_kb: [],
  preset_library: [],
  default_provider_id: null,
  default_model_name: '',
})

function resetForm() {
  form.name = ''
  form.description = ''
  form.system_prompt = ''
  form.enabled = true
  form.preset_skills = []
  form.preset_mcp = []
  form.preset_kb = []
  form.preset_library = []
  form.default_provider_id = null
  form.default_model_name = ''
}

// 卡片副行：人设摘要 + 各类预设计数 + 默认模型
function modelLabel(e) {
  if (!e.default_provider_id) return ''
  const p = e.default_provider_id ? model.providerById(e.default_provider_id) : null
  if (!p) return ''
  const m = (e.default_model_name || '').trim() || p.default_model || ''
  return m ? `${m} · ${p.name}` : p.name
}
function presetSummary(e) {
  const parts = []
  const sk = e.preset_skills || []
  const mc = e.preset_mcp || []
  const kb = e.preset_kb || []
  const lb = e.preset_library || []
  if (sk.length) parts.push(`技能 ${sk.length}`)
  if (mc.length) parts.push(`MCP ${mc.length}`)
  if (kb.length) parts.push(`RAG ${kb.length}`)
  if (lb.length) parts.push(`资料 ${lb.length}`)
  return parts.length ? parts.join(' · ') : '无预设（仅人设）'
}

// 打开对话框（新建/编辑）前补齐候选：库文档清单 + 供应商 + 注册表各类列表
async function ensureCandidates() {
  reg.ensureLoaded()
  model.fetchProviders()
  try {
    libraryRows.value = (await listLibrary()) || []
  } catch {
    libraryRows.value = [] // 拦截器已提示；缺库文档只影响「资料」预设选择，不阻塞其余字段
  }
}

function openNew() {
  editingId.value = null
  resetForm()
  ensureCandidates()
  dialogOpen.value = true
}

function openEdit(expert) {
  editingId.value = expert.id
  form.name = expert.name || ''
  form.description = expert.description || ''
  form.system_prompt = expert.system_prompt || ''
  form.enabled = !!expert.enabled
  form.preset_skills = (expert.preset_skills || []).slice()
  form.preset_mcp = (expert.preset_mcp || []).slice()
  form.preset_kb = (expert.preset_kb || []).slice()
  form.preset_library = (expert.preset_library || []).slice()
  form.default_provider_id = expert.default_provider_id ?? null
  form.default_model_name = expert.default_model_name || ''
  ensureCandidates()
  dialogOpen.value = true
}

async function submit() {
  if (!form.name.trim()) {
    ElMessage.warning('name 不能为空')
    return
  }
  saving.value = true
  const payload = {
    name: form.name.trim(),
    description: form.description.trim() || null,
    system_prompt: form.system_prompt,
    enabled: form.enabled,
    preset_skills: form.preset_skills,
    preset_mcp: form.preset_mcp,
    preset_kb: form.preset_kb,
    preset_library: form.preset_library,
    // 选供应商才带默认模型（name 空=用供应商 default_model）；未选则整体置空
    default_provider_id: form.default_provider_id || null,
    default_model_name: form.default_provider_id ? (form.default_model_name.trim() || null) : null,
  }
  try {
    if (editingId.value === null) await createExpert(payload)
    else await updateExpert(editingId.value, payload)
    ElMessage.success(editingId.value === null ? '运维专家档案已创建' : '运维专家档案已更新')
    dialogOpen.value = false
    await reg.loadCategory('experts')
  } catch {
    // 拦截器已弹后端 message（如重名 400 / 预设引用不存在 400）
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(expert) {
  try {
    await updateExpert(expert.id, { enabled: !expert.enabled })
    await reg.loadCategory('experts')
  } catch { /* 拦截器已提示 */ }
}

async function onDelete(expert) {
  try {
    await ElMessageBox.confirm(
      `删除档案「${expert.name}」后，引用它的任务不受影响（人设/预设已在挂载时快照）；但新任务无法再套用它。确定删除？`,
      '删除运维专家档案',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await removeExpert(expert.id)
    ElMessage.success('档案已删除')
    await reg.loadCategory('experts')
  } catch { /* 拦截器已提示 */ }
}

// 关闭对话框时也清理？不必：下次打开 resetForm/openEdit 会重置
watch(dialogOpen, (v) => { if (!v) editingId.value = null })
</script>

<template>
  <div class="rc rc-experts">
    <div class="rc-head">
      <span class="rc-title">运维专家</span>
      <span v-if="list.length" class="rc-count">{{ list.length }}</span>
      <span class="rc-hint text-dim">可复用智能体档案：人设 + 预设技能/MCP/RAG/资料 + 默认模型，套用到任务即快照</span>
      <el-button class="rc-add" size="small" type="primary" :icon="Plus" @click="openNew">
        新建档案
      </el-button>
    </div>

    <div v-loading="reg.loading" class="rc-body">
      <el-empty
        v-if="!reg.loading && !list.length"
        description="暂无运维专家档案"
        :image-size="64"
      >
        <el-button size="small" type="primary" @click="openNew">组装第一份档案</el-button>
      </el-empty>

      <div v-else class="rc-list">
        <div v-for="e in list" :key="e.id" class="rc-item">
          <div class="rc-item-main rc-no-caret">
            <div class="rc-txt">
              <div class="rc-line1">
                <span class="rc-name">{{ e.name }}</span>
                <el-tag size="small" effect="plain" type="info">{{ e.role || 'general' }}</el-tag>
                <el-tag size="small" :type="e.enabled ? 'success' : 'info'">
                  {{ e.enabled ? '启用' : '停用' }}
                </el-tag>
              </div>
              <div v-if="e.description" class="rc-sub">{{ e.description }}</div>
              <div class="rc-tags">
                <span class="rc-tag">{{ presetSummary(e) }}</span>
                <span v-if="modelLabel(e)" class="rc-tag rc-tag-model">默认模型：{{ modelLabel(e) }}</span>
              </div>
            </div>
          </div>

          <div class="rc-ops">
            <el-switch
              size="small"
              :model-value="!!e.enabled"
              @change="toggleEnabled(e)"
            />
            <el-button text size="small" @click="openEdit(e)">编辑</el-button>
            <el-button text size="small" type="danger" @click="onDelete(e)">删除</el-button>
          </div>
        </div>
      </div>
    </div>

    <el-dialog
      v-model="dialogOpen"
      :title="editingId === null ? '新建运维专家档案' : '编辑运维专家档案'"
      width="860px"
      append-to-body
    >
      <el-form label-width="110px" label-position="left">
        <div class="ec-row">
          <el-form-item label="名称" required>
            <el-input v-model="form.name" placeholder="如：SRE 值班专家" maxlength="128" />
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="form.enabled" />
          </el-form-item>
        </div>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="一句话说明专长/适用场景（可选）" maxlength="512" />
        </el-form-item>
        <el-form-item label="人设提示词">
          <el-input
            v-model="form.system_prompt"
            type="textarea"
            :rows="5"
            placeholder="系统提示词全文：定义该运维专家的角色、行为准则、输出风格。套用档案时快照到任务"
          />
        </el-form-item>

        <el-divider content-position="left">预设装配（套用档案时覆盖挂载到任务）</el-divider>

        <el-form-item label="技能">
          <el-select v-model="form.preset_skills" multiple filterable placeholder="可复用技能指令" style="width: 100%">
            <el-option v-for="s in reg.skills" :key="s.id" :label="`${s.name}${s.enabled ? '' : '（停用）'}`" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="MCP">
          <el-select v-model="form.preset_mcp" multiple filterable placeholder="外部工具连接器" style="width: 100%">
            <el-option v-for="m in reg.mcps" :key="m.id" :label="`${m.name}${m.enabled ? '' : '（停用）'}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="RAG">
          <el-select v-model="form.preset_kb" multiple filterable placeholder="检索切块知识库" style="width: 100%">
            <el-option v-for="k in reg.kbs" :key="k.id" :label="`${k.name}${k.status === 'ready' ? '' : '（' + (k.status || '未就绪') + '）'}`" :value="k.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="资料库文档">
          <el-select v-model="form.preset_library" multiple filterable placeholder="整份文档原文引用（跨空间）" style="width: 100%">
            <el-option v-for="f in libraryRows" :key="f.id" :label="f.filename" :value="f.id" />
          </el-select>
        </el-form-item>

        <el-form-item label="默认模型">
          <div class="ec-model">
            <el-select v-model="form.default_provider_id" clearable filterable placeholder="选供应商（可选）" style="width: 220px">
              <el-option v-for="p in model.providers" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
            <el-input
              v-model="form.default_model_name"
              placeholder="模型名（留空用供应商默认）"
              style="width: 260px"
              :disabled="!form.default_provider_id"
            />
          </div>
          <div class="ec-hint text-dim">选供应商即套用档案时把任务模型绑到该供应商；留空模型名 = 用供应商 default_model。不选则不动任务既有绑定</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存档案</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* 各 center 共用一套 .rc 卡片网格样式（C4：行 → 卡；dark 兼容走 CSS 变量），
   本页内容更宽，卡片采用上下布局与预设标签摘要 */
.rc { display: flex; flex-direction: column; height: 100%; min-width: 0; }
.rc-head { display: flex; align-items: center; gap: 8px; padding: 2px 2px 10px; }
.rc-title { font-size: 13px; font-weight: 600; }
.rc-count { font-size: 11px; color: var(--ls-fg-dim); background: rgba(127,132,148,.18); border-radius: 999px; padding: 0 6px; }
.rc-hint { font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rc-add { margin-left: auto; }
.rc-body { flex: 1 1 auto; min-height: 0; overflow-y: auto; }
.rc-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 10px; align-content: start; }
.rc-item { display: flex; flex-direction: column; border: 1px solid var(--ls-border); border-radius: 8px; background: var(--ls-bg); min-width: 0; }
.rc-item-main { display: flex; align-items: flex-start; width: 100%; padding: 10px 12px 6px; border: none; background: transparent; color: var(--ls-fg); text-align: left; }
.rc-no-caret { cursor: default; }
.rc-txt { flex: 1 1 auto; min-width: 0; }
.rc-line1 { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.rc-name { font-size: 13px; font-weight: 600; }
.rc-sub { font-size: 12px; color: var(--ls-fg-dim); margin-top: 2px; }
.rc-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.rc-tag { font-size: 11px; color: var(--ls-fg-dim); background: rgba(127,132,148,.14); border-radius: 4px; padding: 1px 6px; }
.rc-tag-model { color: var(--ls-accent); }
.rc-ops { display: flex; align-items: center; gap: 2px; padding: 6px 10px 8px 12px; margin-top: 6px; border-top: 1px dashed var(--ls-border); flex-wrap: wrap; }
.ec-row { display: flex; gap: 16px; }
.ec-row .el-form-item { flex: 1 1 auto; min-width: 0; }
.ec-model { display: flex; gap: 8px; width: 100%; }
.ec-hint { font-size: 12px; margin-top: 4px; line-height: 1.5; }

/* —— C6 版末：运维专家也与其余中心同规格 = 每行两卡（覆写原 auto-fill，避免大屏跑出 3+ 列）。
     强调色 rose：卡片顶缘彩线 + 浅彩卡底，名称/操作行压淡、描述句着彩出挑 —— */
.rc-list { grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 14px; row-gap: 14px; }
.rc-item {
  border-top: 2px solid var(--cc);
  background: var(--cc-soft);
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}
.rc-item:hover { border-color: var(--cc); box-shadow: 0 4px 14px rgba(15, 23, 42, 0.1); transform: translateY(-1px); }
.rc-name { color: var(--ls-fg-dim); }
.rc-sub { color: var(--cc); font-weight: 600; }
.rc-count { color: var(--cc); background: var(--cc-soft2); }
</style>
