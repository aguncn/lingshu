<script setup>
// 空间重命名对话框（C1 左栏空间树行内操作）：PATCH /api/spaces/<id> 改名/改描述。
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { useSpaceStore } from '../../stores/space'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  space: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue'])

const spaceStore = useSpaceStore()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const form = reactive({ name: '', description: '' })
const saving = ref(false)

// 每次打开预填当前值（目标可能变，须 watch 而非 onMounted）
watch(visible, (v) => {
  if (!v || !props.space) return
  form.name = props.space.name || ''
  form.description = props.space.description || ''
})

async function submit() {
  const name = form.name.trim()
  if (!name) {
    ElMessage.warning('请填写空间名称')
    return
  }
  saving.value = true
  try {
    await spaceStore.updateSpace(props.space.id, {
      name,
      description: form.description.trim(),
    })
    ElMessage.success('空间已更新')
    visible.value = false
  } catch {
    // 失败提示由 http 拦截器统一弹出，这里只停止提交态
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="重命名空间" width="420px" append-to-body>
    <el-form label-width="72px" @submit.prevent="submit">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" placeholder="如：核心业务系统排障" maxlength="128" @keyup.enter="submit" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="2" maxlength="512" placeholder="可选" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
    </template>
  </el-dialog>
</template>
