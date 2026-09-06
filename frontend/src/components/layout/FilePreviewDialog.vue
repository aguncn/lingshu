<script setup>
// 文件预览对话框（design D7 / spec R5）：按类型呈现——图片走 <img>、文本走 <pre>、
// 其余仅展示 mime/大小/路径元信息。内容取字节分流：kind=file 走任务内容端点，
// kind=ref（集中库引用）改走 /library/<id>/download —— 引用文件在库、任务盘上无副本。
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { getTaskFileContent } from '../../api/files'
import { getLibraryBlob } from '../../api/library'
import { fileKind, formatBytes } from '../../utils/file'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  taskId: { type: Number, default: null },
  file: { type: Object, default: null }, // file 行 {filename,path,size,mime}；ref 行 {kind,id,library_file_id,filename,size,mime,shared}
})

const isRef = computed(() => !!(props.file && props.file.kind === 'ref' && props.file.library_file_id))
// 切换条目凭复合键去重：同名工作文件与同名库引用可能并存，仅 filename 做 key 会漏触发
const fileKey = computed(() => {
  const f = props.file
  if (!f) return ''
  return isRef.value ? `ref:${f.id}:${f.library_file_id}` : `file:${f.path ?? f.filename}`
})
const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const kind = computed(() => fileKind(props.file?.filename, props.file?.mime))
const loading = ref(false)
const error = ref('')
const text = ref('')
const imageUrl = ref('')

function revoke() {
  if (imageUrl.value) {
    URL.revokeObjectURL(imageUrl.value)
    imageUrl.value = ''
  }
}

async function load() {
  revoke()
  text.value = ''
  error.value = ''
  if (!props.file || !props.taskId) return
  // 文本/图片才真正取内容；二进制只看元信息即可（避免无谓拉取）
  if (kind.value === 'binary') return
  loading.value = true
  try {
    // ref 行字节在集中资料库（按 library_file_id 下载）；file 行走任务工作目录内容端点
    const blob = isRef.value
      ? await getLibraryBlob(props.file.library_file_id)
      : await getTaskFileContent(props.taskId, props.file.filename)
    if (kind.value === 'image') {
      imageUrl.value = URL.createObjectURL(blob)
    } else {
      text.value = await blob.text()
    }
  } catch (e) {
    error.value = e?.message || '内容读取失败'
  } finally {
    loading.value = false
  }
}

// 打开或切换文件时加载；关闭时回收 objectURL
watch(visible, (v) => {
  if (v) load()
  else revoke()
})
watch(fileKey, () => {
  if (visible.value) load()
})

// 组件卸载时回收可能残留的 objectURL
onBeforeUnmount(revoke)
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="file ? file.filename : '文件预览'"
    width="720px"
    top="6vh"
    append-to-body
    destroy-on-close
  >
    <div class="fpd-meta">
      <el-tag size="small" effect="plain">{{ file?.mime || '未知类型' }}</el-tag>
      <span class="fpd-meta-item">大小 {{ formatBytes(file?.size) }}</span>
      <span v-if="isRef" class="fpd-meta-item">来源：集中资料库引用</span>
      <el-tag v-else-if="file?.path" size="small" effect="plain" type="info">{{ file.path }}</el-tag>
      <el-tag v-if="file?.shared" size="small" type="warning" effect="plain">共享</el-tag>
      <span class="fpd-meta-item">类别 {{ kind }}</span>
    </div>

    <div v-loading="loading" class="fpd-body">
      <el-empty
        v-if="error"
        :description="`无法读取文件内容：${error}`"
        :image-size="60"
      />
      <el-empty v-else-if="kind === 'binary'" description="该类型不支持在线预览" :image-size="60">
        <div class="text-dim fpd-bin-note">仅展示元信息（文件类型未列入文本/图片预览范围）</div>
      </el-empty>

      <img v-else-if="kind === 'image' && imageUrl" :src="imageUrl" class="fpd-img" alt="预览" />
      <pre v-else-if="kind === 'text'" class="fpd-pre">{{ text }}</pre>

      <div v-else-if="!file" class="fpd-none text-dim">未选择文件</div>
    </div>
  </el-dialog>
</template>

<style scoped>
.fpd-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 10px;
  margin-bottom: 6px;
  border-bottom: 1px solid var(--ls-border);
  font-size: 12px;
  color: var(--ls-fg-dim);
  flex-wrap: wrap;
}
.fpd-body {
  min-height: 200px;
  max-height: 64vh;
  overflow: auto;
}
.fpd-img {
  max-width: 100%;
  display: block;
  margin: 0 auto;
  border-radius: 4px;
}
.fpd-pre {
  margin: 0;
  padding: 12px;
  background: #0d1117;
  color: #d6dde8;
  border-radius: 6px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
.fpd-bin-note {
  font-size: 12px;
}
.fpd-none {
  font-size: 13px;
}
</style>
