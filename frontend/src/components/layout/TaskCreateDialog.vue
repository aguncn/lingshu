<script setup>
// 新建任务对话框：选空间 + title + task_type(受控枚举) + 可选 visibility（spec R2 / task 2.3）。
// 成功后重拉该空间任务分组并选中新任务。
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { TASK_TYPE_META, VISIBILITY_META } from '../../constants'
import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import { useUiStore } from '../../stores/ui'

const ui = useUiStore()
const space = useSpaceStore()
const task = useTaskStore()

const visible = computed({
  get: () => ui.taskDialogOpen,
  set: (v) => (ui.taskDialogOpen = v),
})

const form = reactive({ space_id: null, title: '', task_type: 'general', visibility: 'private' })
const saving = ref(false)

const TYPE_OPTIONS = Object.entries(TASK_TYPE_META).map(([value, m]) => ({ value, label: m.label }))
const VIS_OPTIONS = Object.entries(VISIBILITY_META).map(([value, m]) => ({ value, label: m.label }))

// 打开时预选：当前过滤空间 → 首个空间
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
  try {
    const t = await task.createTask({
      space_id: form.space_id,
      title: form.title.trim(),
      task_type: form.task_type,
      visibility: form.visibility,
    })
    ElMessage.success(`任务「${t.title}」已创建`)
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
}
</style>
