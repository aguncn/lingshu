<script setup>
// 知识库中心（P5 AD-03）：列表 + 新建/编辑（归属空间/embedding/chunk_size/status）+ 上传文档 + 关键词检索。
// 检索命中依赖 chunk 粒度评分，纯关键词、本期无向量化。
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import { createKb, removeKb, searchKb, updateKb, uploadDocument } from '../../api/kbs'
import { KB_STATUS_META, metaOf } from '../../constants'
import { useRegistryStore } from '../../stores/registry'
import { useSpaceStore } from '../../stores/space'

const reg = useRegistryStore()
const spaceStore = useSpaceStore()
const list = computed(() => reg.kbs)
// 归属空间下拉复用左侧已加载的空间列表；key 为空可选项 = 全局资料
const spaces = computed(() => spaceStore.spaces)

// 打开抽屉即补拉一次空间（已加载则 no-op），保证下拉有真实可选值
onMounted(() => {
  reg.loadCategory('kbs')
  spaceStore.ensureLoaded()
})

const dialogOpen = ref(false)
const editingId = ref(null)
const saving = ref(false)

const searchOpen = ref(false) // 检索结果弹层
const searchBusy = ref(false)
const searchResults = ref([])
const searchTarget = ref(null) // 正在检索的 KB（供标题显示）
const searchForm = reactive({ query: '', topK: 5 })

const uploading = ref(false) // 正在上传（防止重复提交）
const fileInput = ref(null) // 复用的隐藏文件框；先记目标 KB 再触发选择
const uploadTargetId = ref(null)

const form = reactive({
  name: '', spaceId: null, embeddingProvider: '', chunkSize: 400, status: 'draft',
})

function statusMeta(s) { return metaOf(KB_STATUS_META, s) }

function pickSpace(id) {
  const sp = spaces.value.find((x) => x.id === id)
  return sp ? sp.name : (id ?? '全局')
}

function openNew() {
  editingId.value = null
  Object.assign(form, { name: '', spaceId: null, embeddingProvider: '', chunkSize: 400, status: 'draft' })
  dialogOpen.value = true
}

function openEdit(kb) {
  editingId.value = kb.id
  form.name = kb.name || ''
  form.spaceId = kb.space_id ?? null
  form.embeddingProvider = kb.embedding_provider || ''
  form.chunkSize = kb.chunk_size ?? 400
  form.status = kb.status || 'draft'
  dialogOpen.value = true
}

async function submit() {
  if (!form.name.trim()) { ElMessage.warning('name 不能为空'); return }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      space_id: form.spaceId ? Number(form.spaceId) : null,
      embedding_provider: form.embeddingProvider.trim() || null,
      chunk_size: Number(form.chunkSize) || 400,
      status: form.status,
    }
    if (editingId.value === null) await createKb(payload)
    else await updateKb(editingId.value, payload)
    ElMessage.success(editingId.value === null ? '知识库已创建' : '知识库已更新')
    dialogOpen.value = false
    await reg.loadCategory('kbs')
  } catch { /* 拦截器已提示 */ } finally {
    saving.value = false
  }
}

// —— 上传：先记目标 KB，再点击同一隐藏 file input（accept 仅 .txt/.md）——
function pickUpload(kb) {
  if (kb.status === 'disabled') { ElMessage.warning('停用库不可上传，请先改为就绪/草稿'); return }
  uploadTargetId.value = kb.id
  fileInput.value && fileInput.value.click()
}

async function onFileChosen(e) {
  const file = e.target.files && e.target.files[0]
  e.target.value = '' // 允许重复选同一文件
  if (!file || uploadTargetId.value === null) return
  const okExt = /\.(txt|md)$/i
  if (!okExt.test(file.name)) { ElMessage.warning('仅支持 .txt / .md 文本文档'); return }
  uploading.value = true
  try {
    const kb = list.value.find((x) => x.id === uploadTargetId.value)
    await uploadDocument(uploadTargetId.value, file)
    ElMessage.success(`已上传「${file.name}」${kb ? '到「' + kb.name + '」' : ''}，同库同名文档整体替换切块`)
  } catch { /* 拦截器已提示 */ } finally {
    uploading.value = false
    uploadTargetId.value = null
  }
}

// —— 检索：独立弹层展示 topK 命中切块（score 降序由后端保证）——
function openSearch(kb) {
  if (kb.status === 'disabled') { ElMessage.warning('停用库不可检索，请先启用'); return }
  searchTarget.value = kb
  searchForm.query = ''
  searchForm.topK = 5
  searchResults.value = []
  searchOpen.value = true
}

async function runSearch() {
  if (!searchForm.query.trim()) { ElMessage.warning('请输入检索关键词'); return }
  searchBusy.value = true
  try {
    searchResults.value = await searchKb(searchTarget.value.id, searchForm.query.trim(), Number(searchForm.topK) || 5)
  } catch { /* 拦截器已提示 */ } finally {
    searchBusy.value = false
  }
}

async function toggleStatus(kb) {
  const next = kb.status === 'disabled' ? 'draft' : kb.status === 'ready' ? 'disabled' : 'ready'
  try {
    await updateKb(kb.id, { status: next })
    await reg.loadCategory('kbs')
  } catch { /* 拦截器已提示 */ }
}

async function onDelete(kb) {
  try {
    await ElMessageBox.confirm(
      `删除知识库「${kb.name}」会连同其全部切块与任务挂载一并清理。确定删除？`,
      '删除知识库',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await removeKb(kb.id)
    ElMessage.success('知识库已删除')
    await reg.loadCategory('kbs')
  } catch { /* 拦截器已提示 */ }
}
</script>

<template>
  <div class="rc">
    <div class="rc-head">
      <span class="rc-title">知识库</span>
      <span v-if="list.length" class="rc-count">{{ list.length }}</span>
      <el-button class="rc-add" size="small" type="primary" :icon="Plus" @click="openNew">
        新建知识库
      </el-button>
    </div>

    <div v-loading="reg.loading" class="rc-body">
      <el-empty v-if="!reg.loading && !list.length" description="暂无知识库" :image-size="64">
        <el-button size="small" type="primary" @click="openNew">创建第一个知识库</el-button>
      </el-empty>

      <div v-else class="rc-list">
        <div v-for="kb in list" :key="kb.id" class="rc-item">
          <div class="rc-item-main no-btn">
            <div class="rc-txt">
              <div class="rc-line1">
                <span class="rc-name">{{ kb.name }}</span>
                <el-tag size="small" effect="plain" :type="statusMeta(kb.status).type">
                  {{ statusMeta(kb.status).label }}
                </el-tag>
                <el-tag v-if="kb.space_id" size="small" type="info" effect="plain">
                  空间：{{ pickSpace(kb.space_id) }}
                </el-tag>
              </div>
              <div class="rc-sub">
                切块 {{ kb.chunk_size ?? 400 }} 字符{{ kb.embedding_provider ? ' · 向量 ' + kb.embedding_provider : ' · 纯关键词' }}
              </div>
            </div>
          </div>
          <div class="rc-ops">
            <el-button text size="small" :loading="uploading && uploadTargetId === kb.id" @click="pickUpload(kb)">
              上传文档
            </el-button>
            <el-button text size="small" @click="openSearch(kb)">检索</el-button>
            <el-button text size="small" @click="toggleStatus(kb)">{{ kb.status === 'ready' ? '停用' : '启用' }}</el-button>
            <el-button text size="small" @click="openEdit(kb)">编辑</el-button>
            <el-button text size="small" type="danger" @click="onDelete(kb)">删除</el-button>
          </div>
        </div>
      </div>
    </div>

    <input ref="fileInput" type="file" class="rc-file" accept=".txt,.md" @change="onFileChosen" />

    <el-dialog v-model="dialogOpen" :title="editingId === null ? '新建知识库' : '编辑知识库'" width="520px" append-to-body>
      <el-form label-width="96px" label-position="left">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="128" placeholder="如：runbook-2025" />
        </el-form-item>
        <el-form-item label="归属空间">
          <el-select v-model="form.spaceId" clearable filterable placeholder="不选=全局资料">
            <el-option v-for="sp in spaces" :key="sp.id" :label="sp.name" :value="sp.id" />
          </el-select>
          <div class="rc-hint">全局库可被所有空间任务引用</div>
        </el-form-item>
        <el-form-item label="向量化">
          <el-input v-model="form.embeddingProvider" maxlength="128" placeholder="空=纯关键词检索（本期默认）" />
        </el-form-item>
        <el-form-item label="切块大小">
          <el-input-number v-model="form.chunkSize" :min="100" :max="2000" :step="100" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status">
            <el-option label="草稿" value="draft" />
            <el-option label="就绪" value="ready" />
            <el-option label="停用" value="disabled" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="searchOpen" :title="`检索「${searchTarget?.name || ''}」`" width="600px" append-to-body>
      <div class="rc-search-bar">
        <el-input v-model="searchForm.query" placeholder="输入关键词，回车检索" clearable @keyup.enter="runSearch" />
        <el-input-number v-model="searchForm.topK" :min="1" :max="20" />
        <el-button type="primary" :loading="searchBusy" @click="runSearch">检索</el-button>
      </div>
      <div v-if="!searchBusy && searchResults.length === 0" class="rc-search-empty">
        <el-empty v-if="!searchForm.query" description="输入关键词开始检索" :image-size="48" />
        <el-empty v-else description="无命中切块" :image-size="48" />
      </div>
      <div v-else class="rc-hits">
        <div v-for="(h, i) in searchResults" :key="h.chunk_id ?? i" class="rc-hit">
          <div class="rc-hit-meta">
            <span class="rc-hit-file">{{ h.filename }}</span>
            <span v-if="h.score" class="rc-hit-score">score {{ Number(h.score).toFixed(3) }}</span>
          </div>
          <pre class="rc-hit-text">{{ h.content }}</pre>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.rc { display: flex; flex-direction: column; height: 100%; min-width: 0; }
.rc-head { display: flex; align-items: center; gap: 8px; padding: 2px 2px 10px; }
.rc-title { font-size: 13px; font-weight: 600; }
.rc-count { font-size: 11px; color: var(--ls-fg-dim); background: rgba(127,132,148,.18); border-radius: 999px; padding: 0 6px; }
.rc-add { margin-left: auto; }
.rc-body { flex: 1 1 auto; min-height: 0; overflow-y: auto; }
.rc-list { display: flex; flex-direction: column; gap: 4px; }
.rc-item { border: 1px solid var(--ls-border); border-radius: 8px; background: var(--ls-bg); padding: 9px 10px 8px; }
.rc-item-main.no-btn { display: flex; }
.rc-txt { flex: 1 1 auto; min-width: 0; }
.rc-line1 { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.rc-name { font-size: 13px; font-weight: 600; }
.rc-sub { font-size: 12px; color: var(--ls-fg-dim); margin-top: 2px; }
.rc-ops { display: flex; align-items: center; gap: 2px; margin-top: 6px; flex-wrap: wrap; }
.rc-file { display: none; }
.rc-hint { font-size: 11px; color: var(--ls-fg-dim); line-height: 1.3; margin-top: 2px; }
.rc-search-bar { display: flex; gap: 8px; }
.rc-search-empty { margin-top: 8px; }
.rc-hits { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; max-height: 48vh; overflow-y: auto; }
.rc-hit { border: 1px solid var(--ls-border); border-radius: 6px; padding: 8px 10px; }
.rc-hit-meta { display: flex; align-items: center; gap: 10px; }
.rc-hit-file { font-size: 12px; font-weight: 600; }
.rc-hit-score { font-size: 11px; color: var(--ls-fg-dim); }
.rc-hit-text { margin: 6px 0 0; white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.55; background: rgba(127,132,148,.1); border-radius: 4px; padding: 6px 8px; max-height: 140px; overflow-y: auto; }
</style>
