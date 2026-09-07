<script setup>
// 单类能力挂载编辑器（P4 capability-mount）：一次只编辑一种能力（kind 决定候选集）。
// 之前“四组全量覆盖”的对话框误伤性太强——改技能会连带清空其它三类；现在保存时
// 只替换传入 kind 那类的挂载列表，其余三类保持当前任务原样（同 PUT /caps 全量语义，但前端合并后再提交）。
import { ElMessage } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { useRegistryStore } from '../../stores/registry'
import { useTaskStore } from '../../stores/task'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // skills | mcps | kbs | experts：本轮要编辑哪一类，就只显示哪一类的候选
  kind: { type: String, default: 'skills' },
})
const emit = defineEmits(['update:modelValue', 'saved'])

const task = useTaskStore()
const reg = useRegistryStore()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const saving = ref(false)
const selected = ref([]) // 当前 kind 下已勾选的 id

// 四类各自独立的候选与说明；list() 每次取注册表最新（增删改后无需重启）
const KIND_META = {
  skills: { title: '技能', note: 'AgentScope 技能库（注入 record 指令）', list: () => reg.skills || [] },
  kbs: { title: 'RAG', note: '检索增强：任务按关键词召回库内切块', list: () => reg.kbs || [] },
  mcps: { title: 'MCP', note: '外部工具连接器，暴露工具给智能体', list: () => reg.mcps || [] },
  experts: { title: '运维专家', note: '档案人设（挂载即快照）', list: () => reg.experts || [] },
}
const kindMeta = computed(() => KIND_META[props.kind] || KIND_META.skills)
const candidates = computed(() => kindMeta.value.list())
const taskTitle = computed(() => task.activeTask?.title ?? '')

function isReady(item) {
  if (props.kind === 'kbs') return item.status === 'ready'
  return !!item.enabled
}
function readyText(item) {
  return props.kind === 'kbs' ? (item.status || '未就绪') : '停用'
}

async function open() {
  reg.ensureLoaded() // 候选 join 需注册表列表；冷启动补拉
  await task.loadCaps(task.activeTaskId, { force: true }) // 拿权威挂载，别把其它类的旧值盖掉
  selected.value = (task.caps?.[props.kind] || []).slice()
}

watch(visible, (v) => {
  if (v && task.activeTaskId) open()
})

async function submit() {
  if (!task.activeTaskId) return
  saving.value = true
  try {
    // 合并：只改当前 kind，其余三类保持任务现有挂载（避免单类编辑误清空）
    const cur = task.caps || { skills: [], mcps: [], kbs: [], experts: [] }
    const merged = {
      skills: (cur.skills || []).slice(),
      mcps: (cur.mcps || []).slice(),
      kbs: (cur.kbs || []).slice(),
      experts: (cur.experts || []).slice(),
    }
    merged[props.kind] = selected.value.slice()
    await task.updateCaps(merged)
    ElMessage.success(`「${kindMeta.value.title}」挂载已保存`)
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
    :title="`编辑「${kindMeta.title}」挂载${taskTitle ? ' · ' + taskTitle : ''}`"
    width="480px"
    append-to-body
  >
    <p class="cm-tip">
      勾选可用的{{ kindMeta.title }}项。保存<strong>只更新「{{ kindMeta.title }}」</strong>，
      其余三类能力挂载保持不动；停用/未就绪实体亦允许勾选（运行时将被忽略）。
    </p>

    <div v-loading="task.capsLoading" class="cm-main">
      <h4 class="cm-title">
        {{ kindMeta.title }}
        <span class="cm-note">{{ kindMeta.note }}</span>
      </h4>
      <el-empty
        v-if="!candidates.length"
        description="暂无此项"
        :image-size="44"
      >
        <span class="text-dim cm-empty-hint">请先在「能力广场」新建</span>
      </el-empty>
      <el-checkbox-group v-else v-model="selected" class="cm-opts">
        <el-checkbox v-for="item in candidates" :key="item.id" :value="item.id" class="cm-opt">
          <span class="cm-opt-name">{{ item.name }}</span>
          <el-tag v-if="!isReady(item)" size="small" type="info" effect="plain">
            {{ readyText(item) }}
          </el-tag>
        </el-checkbox>
      </el-checkbox-group>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">保存挂载</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.cm-tip { margin: 0 0 12px; font-size: 12.5px; color: var(--ls-fg-dim); line-height: 1.6; }
.cm-main { border: 1px solid var(--ls-border); border-radius: 8px; padding: 10px 12px; }
.cm-title { margin: 0 0 8px; font-size: 12.5px; font-weight: 600; display: flex; align-items: baseline; gap: 8px; }
.cm-note { font-size: 11px; color: var(--ls-fg-dim); font-weight: 400; }
.cm-opts { display: flex; flex-direction: column; gap: 4px; max-height: 320px; overflow-y: auto; }
.cm-opt { margin-right: 0; height: auto; }
.cm-opt-name { margin-right: 4px; }
.cm-empty-hint { font-size: 12px; }
</style>
