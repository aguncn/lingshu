<script setup>
// 新建任务对话框（C5 改造）：选空间 + title + 可选「运维专家」+ 可选 visibility + 权限模式。
// C5 起去掉「任务类型」与「场景模板」两栏（十二场景域体系硬删）：改选一位运维专家档案——
// 选中后提交先建任务、再 apply 快照装配（人设快照 + 预设技能/MCP/RAG/资料 + 默认模型落到任务自身），
// 成功后展开细节栏让装配立即可见；装配失败不阻断创建（任务已落库，降级手动挂载）。
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { PERMISSION_MODE_META, PERMISSION_MODE_ORDER, VISIBILITY_META } from '../../constants'
import { useModelStore } from '../../stores/model'
import { useRegistryStore } from '../../stores/registry'
import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import { useUiStore } from '../../stores/ui'

const ui = useUiStore()
const space = useSpaceStore()
const task = useTaskStore()
const reg = useRegistryStore()
const model = useModelStore()

const visible = computed({
  get: () => ui.taskDialogOpen,
  set: (v) => (ui.taskDialogOpen = v),
})

const form = reactive({ space_id: null, title: '', visibility: 'private', permission_mode: 'strict', expert_id: null })
const saving = ref(false)

const VIS_OPTIONS = Object.entries(VISIBILITY_META).map(([value, m]) => ({ value, label: m.label }))
// 权限三档（有序）：label + desc；strict 为默认（=旧行为，最严不打断现状）
const PERM_OPTIONS = PERMISSION_MODE_ORDER.map((value) => ({
  value,
  label: PERMISSION_MODE_META[value].label,
  desc: PERMISSION_MODE_META[value].desc,
}))
// 新建时已选档位的风险注记（未选前给 strict 说明，避免用户误以为无门槛）
const chosenPermDesc = computed(() =>
  form.permission_mode ? PERMISSION_MODE_META[form.permission_mode].desc : '',
)

// 可选运维专家 = 注册表中启用中的档案；未启用者不可套（后端 apply 亦 400），故不列
const expertOptions = computed(() => reg.experts.filter((e) => e.enabled))

// 档案的装配摘要（提示「套用会自动挂什么」）：技能/MCP/RAG/资料 计数 + 默认模型名
function expertSubtitle(e) {
  const parts = []
  const sk = e.preset_skills || []
  const mc = e.preset_mcp || []
  const kb = e.preset_kb || []
  const lb = e.preset_library || []
  if (sk.length) parts.push(`技能 ${sk.length}`)
  if (mc.length) parts.push(`MCP ${mc.length}`)
  if (kb.length) parts.push(`RAG ${kb.length}`)
  if (lb.length) parts.push(`资料 ${lb.length}`)
  const prov = e.default_provider_id ? model.providerById(e.default_provider_id) : null
  const mdl = (e.default_model_name || '').trim() || (prov ? prov.default_model || '' : '')
  if (prov) parts.push(mdl ? `模型 ${mdl}` : `默认模型 ${prov.name}`)
  return parts.length ? `套用即装配：${parts.join(' · ')}` : '空档案：仅人设，建后手动挂载'
}

onMounted(() => reg.ensureLoaded())

// 打开时预选：当前过滤空间 → 首个空间；每次重置「是否选运维专家」，避免上次选择残留误导
watch(visible, (v) => {
  if (!v) return
  if (!space.spaces.length) {
    // 尚无空间：提示先建空间（选择框空态可辨）
    form.space_id = null
    return
  }
  form.space_id = space.activeSpaceId && space.byId[space.activeSpaceId] ? space.activeSpaceId : space.spaces[0].id
  form.title = ''
  form.visibility = 'private'
  form.expert_id = null
  form.permission_mode = 'strict' // 每次新建都回默认最严，用户按任务风险显式下调
})

async function submit() {
  if (!form.space_id) {
    ElMessage.warning('请先创建并选择一个空间')
    return
  }
  if (!form.title.trim()) {
    ElMessage.warning('请填写任务标题')
    return
  }
  saving.value = true
  const expert = form.expert_id ? expertOptions.value.find((e) => e.id === form.expert_id) : null
  try {
    const { task: t, apply } = await task.createTask({
      space_id: form.space_id,
      title: form.title.trim(),
      visibility: form.visibility,
      permission_mode: form.permission_mode, // 三档权限（strict/limited/trusted）
      expert_id: form.expert_id || null,
      expert_name: expert ? expert.name : '',
    })
    if (expert && apply && !apply.error) {
      // 套用成功：展开细节栏，让「自动挂上人设/技能/MCP/RAG」立即可见（C5 快照装配观感）
      ui.detailOpen = true
      const skipped = apply.skipped || []
      if (skipped.length) {
        const reasons = [...new Set(skipped.map((s) => s.reason))]
        ElMessage.warning(
          `任务「${t.title}」已创建并套用「${expert.name}」；${skipped.length} 项预设未挂载（${reasons.join('、')}），可在底部「个性设置」里「编辑挂载」补全`,
        )
      } else {
        ElMessage.success(`任务「${t.title}」已创建并套用「${expert.name}」档案`)
      }
    } else if (expert && apply && apply.error) {
      ElMessage.warning(`任务「${t.title}」已创建，但运维专家套用失败：${apply.error}；可稍后手动挂载`)
    } else {
      ElMessage.success(`任务「${t.title}」已创建`)
    }
    visible.value = false
  } catch {
    // 失败提示由 http 拦截器统一弹出
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="新建任务" width="460px" append-to-body>
    <el-form label-width="72px" @submit.prevent="submit">
      <el-form-item label="所属空间" required>
        <el-select v-model="form.space_id" placeholder="选择空间" style="width: 100%" :disabled="!space.spaces.length">
          <el-option v-for="s in space.spaces" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
        <div v-if="!space.spaces.length" class="td-hint text-dim">还没有空间，请先在左栏「新建空间」</div>
      </el-form-item>
      <el-form-item label="标题" required>
        <el-input v-model="form.title" placeholder="如：支付网关间歇性 502 排障" maxlength="256" @keyup.enter="submit" />
      </el-form-item>
      <el-form-item label="运维专家">
        <el-select
          v-model="form.expert_id"
          clearable
          filterable
          style="width: 100%"
          placeholder="可选：套用运维专家档案（不选=建后手动挂载）"
        >
          <el-option
            v-for="e in expertOptions"
            :key="e.id"
            :value="e.id"
            :label="e.name"
            :title="e.description || ''"
          >
            <div class="td-exp">
              <div class="td-exp-name">{{ e.name }}</div>
              <div class="td-exp-sub text-dim">{{ e.description || '' }}<template v-if="e.description"> · </template>{{ expertSubtitle(e) }}</div>
            </div>
          </el-option>
        </el-select>
        <div v-if="!expertOptions.length" class="td-hint text-dim">还没有启用的运维专家：可在能力广场「运维专家」页组装档案，或先手动挂载</div>
        <div v-if="form.expert_id" class="td-hint td-hint-accent">选择后该档案将<strong>快照</strong>到任务（此后改档案不影响本任务）</div>
      </el-form-item>
      <el-form-item label="权限模式">
        <el-select v-model="form.permission_mode" style="width: 100%">
          <el-option v-for="o in PERM_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
        <div class="td-hint text-dim">{{ chosenPermDesc }}</div>
      </el-form-item>
      <el-form-item label="可见性">
        <el-select v-model="form.visibility" style="width: 100%">
          <el-option v-for="o in VIS_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">创建</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.td-hint {
  font-size: 12px;
  margin-top: 4px;
  line-height: 1.5;
}
.td-hint-accent {
  color: var(--ls-accent);
}
.td-exp-name {
  font-size: 13px;
  font-weight: 500;
}
.td-exp-sub {
  font-size: 11.5px;
  white-space: normal;
  line-height: 1.4;
}
</style>
