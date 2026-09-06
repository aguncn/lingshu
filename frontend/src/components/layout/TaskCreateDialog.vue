<script setup>
// 新建任务对话框：选空间 + title + task_type(受控枚举) + 可选 visibility + 可选场景域（P9）。
// 「场景模板」默认取顶部域条点选值（ui.taskDialogDomain）；选定域后提交会先建任务、
// 再 POST apply 自动套用该域预设（挂载 MCP/专家等），成功后展开细节栏让装配立即可见。
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { TASK_TYPE_META, VISIBILITY_META } from '../../constants'
import { useScenarioStore } from '../../stores/scenario'
import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import { useUiStore } from '../../stores/ui'

const ui = useUiStore()
const space = useSpaceStore()
const task = useTaskStore()
const scenario = useScenarioStore()

const visible = computed({
  get: () => ui.taskDialogOpen,
  set: (v) => (ui.taskDialogOpen = v),
})

// 场景域选项：留空=不绑域（走手动挂载，行为与旧版一致）；其余来自 /api/scenarios 十二域
const DOMAIN_OPTIONS = computed(() => [
  { value: '', label: '不绑定（手动挂载）' },
  ...scenario.domains.map((d) => ({ value: d.domain, label: d.name })),
])

// 选定域的装配摘要（提示「会自动挂什么」）：未选或清单未载 → null
const chosenPresetHint = computed(() => {
  if (!form.scenario_domain) return ''
  const d = scenario.byDomain[form.scenario_domain]
  if (!d) return ''
  const p = d.preset || {}
  const parts = []
  if (p.mcps) parts.push(`MCP ${p.mcps}`)
  if (p.experts) parts.push(`专家 ${p.experts}`)
  if (p.skills) parts.push(`技能 ${p.skills}`)
  if (p.kbs) parts.push(`知识库 ${p.kbs}`)
  return parts.length ? `创建后自动套用该域预设：${parts.join(' · ')}` : '该域无预设，创建后手动挂载'
})

const form = reactive({ space_id: null, title: '', task_type: 'general', visibility: 'private', scenario_domain: '' })
const saving = ref(false)

const TYPE_OPTIONS = Object.entries(TASK_TYPE_META).map(([value, m]) => ({ value, label: m.label }))
const VIS_OPTIONS = Object.entries(VISIBILITY_META).map(([value, m]) => ({ value, label: m.label }))

onMounted(() => scenario.ensureLoaded())

// 打开时预选：当前过滤空间 → 首个空间；场景域取顶部条点选（默认空=不绑域）
watch(visible, (v) => {
  if (!v) return
  if (!space.spaces.length) {
    // 尚无空间：提示先建空间（选择框空态可辨）
    form.space_id = null
    return
  }
  form.space_id = space.activeSpaceId && space.byId[space.activeSpaceId] ? space.activeSpaceId : space.spaces[0].id
  form.title = ''
  form.task_type = 'general'
  form.visibility = 'private'
  form.scenario_domain = ui.taskDialogDomain || ''
})
// 关闭即清掉预选域，让顶部 chips 高亮只存在于编排进行中，避免「上次选域」残留误导
watch(visible, (v) => {
  if (!v) ui.taskDialogDomain = ''
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
  const withDomain = !!form.scenario_domain
  try {
    const t = await task.createTask({
      space_id: form.space_id,
      title: form.title.trim(),
      task_type: form.task_type,
      visibility: form.visibility,
      scenario_domain: form.scenario_domain || undefined, // 有域才触发 store 内 apply
    })
    if (withDomain) {
      // 套用成功：展开细节栏，让「自动挂上 MCP/专家」立即可见（spec 验收观感）
      ui.detailOpen = true
      ElMessage.success(`任务「${t.title}」已创建并套用「${scenario.labelOf(form.scenario_domain)}」预设`)
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
      <el-form-item label="任务类型">
        <el-select v-model="form.task_type" style="width: 100%">
          <el-option v-for="o in TYPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="场景模板">
        <el-select v-model="form.scenario_domain" style="width: 100%" placeholder="绑定运维场景，自动装配预设">
          <el-option v-for="o in DOMAIN_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
        <div v-if="chosenPresetHint" class="td-hint text-dim">{{ chosenPresetHint }}</div>
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
</style>
