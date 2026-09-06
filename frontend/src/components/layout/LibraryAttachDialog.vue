<script setup>
// 资料引用挂载对话框（P6 library attach）：挑集中库文件关联到当前任务，
// 关联后该文件以 kind=ref 出现在任务文件树，字节不复制（FileRecord.library_file_id 指向库行）。
import { ElMessage } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { attachLibraryFile, listLibrary } from '../../api/library'
import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import { formatBytes } from '../../utils/file'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'attached'])

const task = useTaskStore()
const space = useSpaceStore()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// —— 待选库文件 & 已挂引用集（用于剔除/灰置）——
const rows = ref([])
const attachedIds = ref(new Set()) // library_file_id 集合
const attaching = ref(false)
const selected = ref([])
const scope = ref('all')

const taskId = computed(() => task.activeTaskId)
const taskSpaceId = computed(() => task.activeTask?.space_id ?? null)
const spaceName = (id) => (id ? (space.byId[id]?.name ?? `#${id}`) : '全局')

const attachable = computed(() => rows.value.filter((r) => !attachedIds.value.has(r.id)))

async function load() {
  if (!taskId.value) return
  // 当前任务已引用的库 id：从文件树 kind=ref 条目反查
  const files = task.filesByTask[taskId.value] || []
  attachedIds.value = new Set(files.filter((f) => f.library_file_id).map((f) => f.library_file_id))
  selected.value = []
  try {
    const params = {}
    if (scope.value === 'global') params.scope = 'global'
    else if (scope.value === 'shared') params.scope = 'shared'
    else if (scope.value === 'space') {
      if (!taskSpaceId.value) { rows.value = []; return }
      params.scope = 'space'
      params.space_id = taskSpaceId.value
    }
    rows.value = (await listLibrary(params)) || []
  } catch {
    rows.value = []
  }
}

watch(visible, (v) => {
  if (v) { space.ensureLoaded(); load() }
})
watch(scope, () => { if (visible.value) load() })

async function submit() {
  if (!taskId.value) return
  attaching.value = true
  try {
    for (const id of selected.value) {
      await attachLibraryFile(taskId.value, id)
    }
    ElMessage.success(`已挂载 ${selected.value.length} 个资料引用`)
    visible.value = false
    emit('attached') // 调用方重拉文件树/资料分区
  } catch { /* 拦截器已提示 */ } finally {
    attaching.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="`挂载资料引用${taskId ? '' : '（请先选择任务）'}`"
    width="560px"
    append-to-body
  >
    <div class="la-bar">
      <el-radio-group v-model="scope" size="small">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="global">全局</el-radio-button>
        <el-radio-button value="shared">共享</el-radio-button>
        <el-radio-button value="space">当前空间</el-radio-button>
      </el-radio-group>
    </div>

    <el-empty v-if="!taskId" description="请先在左侧选中一个任务" :image-size="56" />
    <el-empty v-else-if="!attachable.length" description="没有可挂载的库文件" :image-size="56">
      <span class="text-dim la-empty-note">可到左栏「资料库」上传，或切换上方过滤范围</span>
    </el-empty>

    <div v-else class="la-list">
      <el-checkbox-group v-model="selected" class="la-opts">
        <el-checkbox v-for="row in attachable" :key="row.id" :value="row.id" class="la-opt">
          <span class="la-name">{{ row.filename }}</span>
          <el-tag v-if="row.shared" size="small" type="warning" effect="plain">共享</el-tag>
          <span class="la-sub">{{ formatBytes(row.size) }}</span>
          <span v-if="row.space_id" class="la-sub">{{ spaceName(row.space_id) }}</span>
        </el-checkbox>
      </el-checkbox-group>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :disabled="!selected.length"
        :loading="attaching"
        @click="submit"
      >挂载 {{ selected.length }} 项</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.la-bar { margin-bottom: 10px; }
.la-empty-note { font-size: 12px; }
.la-list { max-height: 46vh; overflow-y: auto; }
.la-opts { display: flex; flex-direction: column; gap: 4px; }
.la-opt { margin-right: 0; height: auto; display: flex; align-items: center; }
.la-name { margin-right: 6px; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.la-sub { margin-left: 8px; font-size: 12px; color: var(--ls-fg-dim); }
</style>
