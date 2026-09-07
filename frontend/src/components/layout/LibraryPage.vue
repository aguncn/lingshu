<script setup>
// 资料库整页（P6 library / C4 由 540px 抽屉升格为主区广场页）：按 全部/全局/共享/空间 浏览集中文件资产。
// 支持上传（可选归属空间）、预览、下载、分享开关、改名、删除（被任务引用禁止）。
// 与 FileTree 里的「引用 → 加入任务文件树」互操作不同：本页是库资产的全局管理视角。
import { Download, Plus, Refresh, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import {
  getLibraryBlob, listLibrary, removeLibrary, updateLibrary, uploadLibrary,
} from '../../api/library'
import { LIBRARY_SCOPE_META } from '../../constants'
import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import { formatBytes } from '../../utils/file'

const space = useSpaceStore()
const task = useTaskStore()

// —— 过滤态 ——
const scope = ref('all')
const filterSpaceId = ref(null) // 仅 scope=space 时生效
const rows = ref([])
const loading = ref(false)

// —— 上传态 ——
const uploadSpaceId = ref(null) // null=存入全局
const uploading = ref(false)
const fileInput = ref(null)

// —— 预览态 ——
const preview = reactive({ open: false, filename: '', kind: '', text: '', url: '', size: 0 })
const previewLoading = ref(false)

const spaceName = (id) => (id ? (space.byId[id]?.name ?? `#${id}`) : '')

async function load() {
  loading.value = true
  try {
    const params = {}
    if (scope.value === 'global') params.scope = 'global'
    else if (scope.value === 'shared') params.scope = 'shared'
    else if (scope.value === 'space') {
      if (!filterSpaceId.value) { rows.value = []; return }
      params.scope = 'space'
      params.space_id = filterSpaceId.value
    }
    rows.value = (await listLibrary(params)) || []
  } catch { /* 拦截器已提示 */ } finally {
    loading.value = false
  }
}

watch(scope, () => {
  // 切到「空间」时给默认空间：优先当前过滤空间，其次当前选中空间，再退第一项
  if (scope.value === 'space' && !filterSpaceId.value) {
    filterSpaceId.value = space.activeSpaceId ?? space.spaces[0]?.id ?? null
  }
  load()
})
watch(filterSpaceId, () => { if (scope.value === 'space') load() })

onMounted(async () => {
  await space.ensureLoaded()
  if (space.activeSpaceId && uploadSpaceId.value === null) uploadSpaceId.value = space.activeSpaceId
  load()
})

// —— 上传：先记目标空间，点隐藏 file input ——
function pickUploadFile() {
  fileInput.value && fileInput.value.click()
}

async function onFileChosen(e) {
  const file = e.target.files && e.target.files[0]
  e.target.value = ''
  if (!file) return
  uploading.value = true
  try {
    await uploadLibrary(file, uploadSpaceId.value ?? null)
    ElMessage.success(`已上传「${file.name}」至${uploadSpaceId.value ? '空间「' + spaceName(uploadSpaceId.value) + '」' : '全局'}`)
    await load()
  } catch { /* 拦截器已提示 */ } finally {
    uploading.value = false
  }
}

async function openPreview(row) {
  previewLoading.value = true
  preview.open = true
  preview.filename = row.filename
  preview.size = row.size
  preview.kind = row.mime || ''
  preview.text = ''
  preview.url = ''
  try {
    const blob = await getLibraryBlob(row.id)
    const isText = /text|markdown|json|javascript|xml/i.test(preview.kind)
    const isImage = /image\//i.test(preview.kind)
    if (isImage) {
      preview.url = URL.createObjectURL(blob)
    } else if (isText || blob.type.startsWith('text/')) {
      preview.text = await blob.text()
    } else {
      preview.text = ''
      preview.url = URL.createObjectURL(blob) // 兜底：浏览器能渲染的格式直接展示，否则提示下载
    }
  } catch {
    preview.open = false
    ElMessage.error('预览读取失败')
  } finally {
    previewLoading.value = false
  }
}

function downloadRow(row) {
  getLibraryBlob(row.id).then((blob) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = row.filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 4000)
  }).catch(() => ElMessage.error('下载失败'))
}

async function toggleShared(row) {
  try {
    await updateLibrary(row.id, { shared: !row.shared })
    ElMessage.success(row.shared ? '已取消共享' : '已设为共享')
    await load()
  } catch { /* 拦截器已提示 */ }
}

async function rename(row) {
  try {
    const { value } = await ElMessageBox.prompt('新的文件名', '重命名', {
      inputValue: row.filename,
      inputValidator: (v) => (v && v.trim() ? true : '文件名不能为空'),
      confirmButtonText: '保存',
      cancelButtonText: '取消',
    })
    await updateLibrary(row.id, { filename: value.trim() })
    ElMessage.success('已重命名')
    await load()
  } catch (err) {
    if (err !== 'cancel' && err?.message !== 'cancel') { /* 拦截器已提示；点取消静默 */ }
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `删除资料「${row.filename}」？若已被任务引用将删除失败，需先在任务侧解除引用。`,
      '删除资料',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await removeLibrary(row.id)
    ElMessage.success('已删除')
    await load()
  } catch { /* 拦截器已提示（含被引用 400） */ }
}

const activeScopeLabel = computed(() => LIBRARY_SCOPE_META.find((s) => s.value === scope.value)?.label ?? scope.value)
</script>

<template>
  <div class="lib rc-library">
    <!-- 头：页名 + 计数 + 刷新 -->
    <div class="lib-head">
      <span class="lib-title">资料库</span>
      <span v-if="rows.length" class="lib-count">{{ rows.length }}</span>
      <span class="lib-head-note text-dim">原文全文引用：文档整份挂载给任务（区别于 RAG 的切块检索）</span>
      <el-tooltip content="刷新" placement="top">
        <el-button class="lib-icon-btn" text :icon="Refresh" @click="load" />
      </el-tooltip>
    </div>

    <!-- 过滤 + 上传工具栏 -->
    <div class="lib-toolbar">
      <el-radio-group v-model="scope" size="small">
        <el-radio-button v-for="s in LIBRARY_SCOPE_META" :key="s.value" :value="s.value">
          {{ s.label }}
        </el-radio-button>
      </el-radio-group>

      <div class="lib-upload">
        <el-select v-model="uploadSpaceId" size="small" clearable placeholder="全局" style="width: 190px">
          <template #prefix>
            <span class="lib-label-prefix">存入</span>
          </template>
          <el-option :value="null" label="全局（所有空间可用）" />
          <el-option v-for="sp in space.spaces" :key="sp.id" :label="`空间 · ${sp.name}`" :value="sp.id" />
        </el-select>
        <el-button size="small" type="primary" :icon="Plus" :loading="uploading" @click="pickUploadFile">
          上传文件
        </el-button>
        <input ref="fileInput" type="file" class="lib-file" @change="onFileChosen" />
      </div>
    </div>

    <div v-if="scope === 'space'" class="lib-filter-space">
      <span class="lib-label">空间：</span>
      <el-select v-model="filterSpaceId" size="small" style="width: 220px" placeholder="选择空间">
        <el-option v-for="sp in space.spaces" :key="sp.id" :label="sp.name" :value="sp.id" />
      </el-select>
    </div>

    <!-- 卡片网格 -->
    <div v-loading="loading" class="lib-body">
      <el-empty
        v-if="!loading && !rows.length"
        :description="scope === 'space' && !filterSpaceId ? '请选择空间' : `${activeScopeLabel}暂无文件`"
        :image-size="72"
      >
        <el-button size="small" type="primary" @click="pickUploadFile">上传第一个文件</el-button>
      </el-empty>

      <div v-else class="lib-list">
        <div v-for="row in rows" :key="row.id" class="lib-item">
          <div class="lib-item-main">
            <div class="lib-txt">
              <div class="lib-line1">
                <span class="lib-name" :title="row.filename" @click="openPreview(row)">{{ row.filename }}</span>
                <el-tag v-if="row.shared" size="small" type="warning" effect="plain">共享</el-tag>
                <el-tag v-if="row.space_id" size="small" effect="plain" type="info">
                  空间 {{ spaceName(row.space_id) }}
                </el-tag>
              </div>
              <div class="lib-sub">{{ formatBytes(row.size) }} · {{ row.mime || '未知类型' }}</div>
            </div>
          </div>
          <div class="lib-ops">
            <el-button text size="small" :icon="View" @click="openPreview(row)">预览</el-button>
            <el-button text size="small" :icon="Download" @click="downloadRow(row)">下载</el-button>
            <el-button text size="small" @click="toggleShared(row)">
              {{ row.shared ? '取消共享' : '共享' }}
            </el-button>
            <el-button text size="small" @click="rename(row)">改名</el-button>
            <el-button text size="small" type="danger" @click="onDelete(row)">删除</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 预览弹层 -->
    <el-dialog v-model="preview.open" :title="preview.filename" width="720px" append-to-body top="6vh">
      <div v-loading="previewLoading" class="lib-preview">
        <img v-if="preview.url && /image\//i.test(preview.kind)" :src="preview.url" class="lib-preview-img" alt="preview" />
        <div v-else-if="preview.text !== ''" class="lib-preview-text">{{ preview.text }}</div>
        <div v-else-if="preview.url" class="lib-preview-plain">
          <p>该类型无法内联预览，请在外部查看：</p>
          <a :href="preview.url" :download="preview.filename">打开文件</a>
        </div>
        <el-empty v-else description="内容为空" :image-size="48" />
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.lib { display: flex; flex-direction: column; height: 100%; min-width: 0; }
.lib-head { display: flex; align-items: center; gap: 8px; padding: 2px 2px 10px; flex: none; }
.lib-title { font-size: 13px; font-weight: 600; }
.lib-count { font-size: 11px; color: var(--ls-fg-dim); background: rgba(127,132,148,.18); border-radius: 999px; padding: 0 6px; }
.lib-head-note { flex: 1 1 auto; min-width: 0; font-size: 12px; }
.lib-icon-btn { flex: none; color: var(--ls-fg-dim); }
.lib-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex: none; flex-wrap: wrap; }
.lib-upload { display: flex; gap: 8px; flex: none; }
.lib-label-prefix { font-size: 12px; color: var(--ls-fg-dim); padding-right: 2px; }
.lib-file { display: none; }
.lib-filter-space { display: flex; align-items: center; gap: 6px; margin-top: 8px; flex: none; }
.lib-label { font-size: 12px; color: var(--ls-fg-dim); }
.lib-body { flex: 1 1 auto; min-height: 0; overflow-y: auto; margin: 10px -2px 0; padding-right: 2px; }
.lib-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; align-content: start; }
.lib-item { display: flex; flex-direction: column; border: 1px solid var(--ls-border); border-radius: 8px; background: var(--ls-bg); padding: 10px 12px 8px; }
.lib-item-main { display: flex; }
.lib-txt { flex: 1 1 auto; min-width: 0; }
.lib-line1 { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.lib-name { font-size: 13px; font-weight: 600; cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 0 1 auto; min-width: 0; }
.lib-name:hover { color: var(--ls-accent); text-decoration: underline; }
.lib-sub { font-size: 12px; color: var(--ls-fg-dim); margin-top: 2px; }
.lib-ops { display: flex; align-items: center; gap: 0; margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--ls-border); flex-wrap: wrap; }
.lib-preview-text { white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.65; font-family: Consolas, monospace; max-height: 72vh; overflow-y: auto; }
.lib-preview-img { max-width: 100%; max-height: 72vh; display: block; margin: 0 auto; }
.lib-preview-plain { color: var(--ls-fg-dim); }

/* —— C6 版末：资料库与其余中心同规格强调（emerald，var(--cc) 见 index.css）。卡片 = 顶缘彩线 + 浅彩卡底；
     文件名行压淡、hover 换主题色，中部 大小·类型 信息行着彩出挑；hover 轻浮起 —— */
.lib-list { column-gap: 14px; row-gap: 14px; }
.lib-item {
  border-top: 2px solid var(--cc);
  background: var(--cc-soft);
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}
.lib-item:hover { border-color: var(--cc); box-shadow: 0 4px 14px rgba(15, 23, 42, 0.1); transform: translateY(-1px); }
.lib-name { color: var(--ls-fg-dim); }
.lib-name:hover { color: var(--cc); text-decoration: none; }
.lib-sub { color: var(--cc); font-weight: 600; }
.lib-count { color: var(--cc); background: var(--cc-soft2); }
</style>
