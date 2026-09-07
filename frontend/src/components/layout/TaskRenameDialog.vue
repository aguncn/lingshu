<script setup>
// 任务重命名对话框（C1 左栏空间树行内操作）：PATCH /api/tasks/<id> 只改标题，无需先选中。
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { useTaskStore } from '../../stores/task'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  task: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue'])

const taskStore = useTaskStore()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const form = reactive({ title: '' })
const saving = ref(false)

watch(visible, (v) => {
  if (!v || !props.task) return
  form.title = props.task.title || ''
})

async function submit() {
  const title = form.title.trim()
  if (!title) {
    ElMessage.warning('请填写任务标题')
    return
  }
  saving.value = true
  try {
    await taskStore.updateTaskEntry(props.task, { title })
    ElMessage.success('任务已重命名')
    visible.value = false
  } catch {
    // 失败提示由 http 拦截器统一弹出，这里只停止提交态
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="重命名任务" width="420px" append-to-body>
    <el-form label-width="72px" @submit.prevent="submit">
      <el-form-item label="标题" required>
        <el-input v-model="form.title" placeholder="如：支付网关间歇性 502 排障" maxlength="256" @keyup.enter="submit" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
    </template>
  </el-dialog>
</template>
