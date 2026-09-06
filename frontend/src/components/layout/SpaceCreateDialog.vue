<script setup>
// 新建空间对话框：POST /api/spaces 成功后重拉列表并选中（spec R2 / task 2.1）。
import { ElMessage } from 'element-plus'
import { computed, reactive, ref } from 'vue'

import { VISIBILITY_META } from '../../constants'
import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import { useUiStore } from '../../stores/ui'

const ui = useUiStore()
const space = useSpaceStore()
const task = useTaskStore()

const visible = computed({
  get: () => ui.spaceDialogOpen,
  set: (v) => (ui.spaceDialogOpen = v),
})

const form = reactive({ name: '', description: '', visibility: 'private' })
const saving = ref(false)

// 常量表按顺序给出选项（键值展示文案）
const VIS_OPTIONS = Object.entries(VISIBILITY_META).map(([value, m]) => ({ value, label: m.label }))

function reset() {
  form.name = ''
  form.description = ''
  form.visibility = 'private'
}

async function submit() {
  const name = form.name.trim()
  if (!name) {
    ElMessage.warning('请填写空间名称')
    return
  }
  saving.value = true
  try {
    const sp = await space.createSpace({ name, description: form.description.trim(), visibility: form.visibility })
    // 新空间可能是空的：重拉任务分组，让其作为「分组头」出现在左栏（task 2.1 验收）
    await task.loadAll()
    ElMessage.success(`空间「${sp.name}」已创建`)
    visible.value = false
    reset()
  } catch {
    // 失败提示已由 http 拦截器统一弹出，这里只停止提交态
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="新建空间" width="420px" append-to-body>
    <el-form label-width="72px" @submit.prevent="submit">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" placeholder="如：核心业务系统排障" maxlength="128" @keyup.enter="submit" />
      </el-form-item>
      <el-form-item label="可见性">
        <el-select v-model="form.visibility" style="width: 100%">
          <el-option v-for="o in VIS_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="2" maxlength="512" placeholder="可选" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">创建</el-button>
    </template>
  </el-dialog>
</template>
