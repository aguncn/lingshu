<script setup>
// 能力挂载对话框（P4 capability-mount）：技能 / 知识库 / MCP / 专家 四组勾选，
// 保存走 PUT /tasks/<id>/caps —— 该接口为全量覆盖，四项都按当前勾选整体提交，
// 因此对话框一次性呈现四组，避免某张 tile 只改一类却清空其余。
import { ElMessage } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { useRegistryStore } from '../../stores/registry'
import { useTaskStore } from '../../stores/task'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'saved'])

const task = useTaskStore()
const reg = useRegistryStore()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const saving = ref(false)
const selected = ref({ skills: [], mcps: [], kbs: [], experts: [] })

const GROUPS = [
  { key: 'skills', title: '技能', note: 'AgentScope 技能库（注入 record 指令）', items: computed(() => reg.skills) },
  { key: 'kbs', title: '知识库', note: '检索增强，向任务提供库内切块', items: computed(() => reg.kbs) },
  { key: 'mcps', title: 'MCP', note: '外部工具连接器，暴露工具给智能体', items: computed(() => reg.mcps) },
  { key: 'experts', title: '专家', note: '角色/多专家协作编排', items: computed(() => reg.experts) },
]

const taskTitle = computed(() => task.activeTask?.title ?? '')

function isEnabled(groupKey, item) {
  // 全局按各自 enabled 标记：skill/expert 字段 enabled；kb 看 status==='ready'；mcp enabled
  if (groupKey === 'kbs') return item.status === 'ready'
  return !!item.enabled
}

async function open() {
  reg.ensureLoaded() // 名称 join 需注册表列表；冷启动时补拉
  await task.loadCaps(task.activeTaskId, { force: true }) // 打开即拿权威挂载
  const c = task.caps || {}
  selected.value = {
    skills: (c.skills || []).slice(),
    mcps: (c.mcps || []).slice(),
    kbs: (c.kbs || []).slice(),
    experts: (c.experts || []).slice(),
  }
}

watch(visible, (v) => {
  if (v && task.activeTaskId) open()
})

async function submit() {
  if (!task.activeTaskId) return
  saving.value = true
  try {
    await task.updateCaps({
      skills: selected.value.skills,
      mcps: selected.value.mcps,
      kbs: selected.value.kbs,
      experts: selected.value.experts,
    })
    ElMessage.success('能力挂载已保存')
    visible.value = false
    emit('saved')
  } catch { /* 拦截器已提示 */ } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="`能力挂载${taskTitle ? ' · ' + taskTitle : ''}`"
    width="680px"
    append-to-body
  >
    <p class="cm-tip">
      勾选项为当前任务可用的能力。保存为<strong>全量覆盖</strong>——四组均按当前勾选提交；停用/未就绪实体亦允许挂载（运行时将被忽略）。
    </p>

    <div v-loading="task.capsLoading" class="cm-groups">
      <section v-for="g in GROUPS" :key="g.key" class="cm-group">
        <h4 class="cm-group-title">
          {{ g.title }}
          <span class="cm-group-note">{{ g.note }}</span>
        </h4>
        <el-empty
          v-if="!g.items.value.length"
          description="注册中心暂无此项"
          :image-size="40"
        >
          <span class="text-dim cm-empty-hint">请先在「注册中心」新建</span>
        </el-empty>
        <el-checkbox-group v-else v-model="selected[g.key]" class="cm-opts">
          <el-checkbox
            v-for="item in g.items.value"
            :key="item.id"
            :value="item.id"
            class="cm-opt"
          >
            <span class="cm-opt-name">{{ item.name }}</span>
            <el-tag v-if="!isEnabled(g.key, item)" size="small" type="info" effect="plain">
              {{ g.key === 'kbs' ? (item.status || '未就绪') : '停用' }}
            </el-tag>
          </el-checkbox>
        </el-checkbox-group>
      </section>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">保存挂载</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.cm-tip { margin: 0 0 12px; font-size: 12.5px; color: var(--ls-fg-dim); line-height: 1.6; }
.cm-groups { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; max-height: 56vh; overflow-y: auto; padding-right: 4px; }
.cm-group { border: 1px solid var(--ls-border); border-radius: 8px; padding: 10px 12px; min-width: 0; }
.cm-group-title { margin: 0 0 8px; font-size: 12.5px; font-weight: 600; display: flex; align-items: baseline; gap: 8px; }
.cm-group-note { font-size: 11px; color: var(--ls-fg-dim); font-weight: 400; }
.cm-opts { display: flex; flex-direction: column; gap: 4px; max-height: 220px; overflow-y: auto; }
.cm-opt { margin-right: 0; height: auto; }
.cm-opt-name { margin-right: 4px; }
.cm-empty-hint { font-size: 12px; }
</style>
