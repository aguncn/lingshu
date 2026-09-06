<script setup>
// 文件树（spec R5 / design D7）：任务文件 = 工作文件（kind=file，任务目录落盘）+ 资料引用
// （kind=ref，集中库引用、字节在库）。两区展示，点条目按 kind 分流预览；引用可由此添加。
import { Document, Files, Link, Picture } from '@element-plus/icons-vue'
import { computed, ref } from 'vue'

import { useTaskStore } from '../../stores/task'
import { fileKind, formatBytes } from '../../utils/file'
import EmptyState from '../common/EmptyState.vue'
import FilePreviewDialog from './FilePreviewDialog.vue'
import LibraryAttachDialog from './LibraryAttachDialog.vue'

const task = useTaskStore()

const files = computed(() => task.activeTaskFiles)
const activeTaskId = computed(() => task.activeTaskId)
// 容错：合并接口给每行带 kind；老缓存行无 kind 按工作文件处理
const workFiles = computed(() => files.value.filter((f) => f.kind !== 'ref'))
const refFiles = computed(() => files.value.filter((f) => f.kind === 'ref'))

const previewOpen = ref(false)
const previewFile = ref(null)
const attachOpen = ref(false)

// 同类同名的两行也可能共存（同名工作文件 + 同名库引用）→ key 必须带身份
function keyOf(f) {
  return f.kind === 'ref' ? `ref-${f.id}` : `file-${f.path ?? f.filename}`
}

function iconOf(f) {
  const kind = fileKind(f.filename, f.mime)
  if (kind === 'image') return Picture
  if (kind === 'text') return Document
  return Files
}

function openPreview(f) {
  previewFile.value = f
  previewOpen.value = true
}

function reload() {
  if (activeTaskId.value) task.loadFiles(activeTaskId.value)
}
</script>

<template>
  <div class="ft">
    <div class="ft-head">
      <span class="ft-title">文件</span>
      <span v-if="files.length" class="ft-count">{{ files.length }}</span>
    </div>

    <div v-loading="task.filesLoading" class="ft-body">
      <EmptyState
        v-if="!task.filesLoading && !files.length"
        description="暂无文件"
        tip="工作文件由上传/智能体产出落盘；资料可在细节栏「资料」分区添加引用"
        retry
        @retry="reload"
      />

      <template v-else>
        <!-- 工作文件 -->
        <div v-if="workFiles.length" class="ft-sec">
          <div class="ft-sec-head">
            <span class="ft-sec-title">工作文件</span>
            <span class="ft-sec-count">{{ workFiles.length }}</span>
          </div>
          <ul class="ft-list">
            <li
              v-for="f in workFiles"
              :key="keyOf(f)"
              class="ft-item"
              @click="openPreview(f)"
            >
              <el-icon class="ft-item-icon"><component :is="iconOf(f)" /></el-icon>
              <div class="ft-item-main">
                <span class="ft-item-name ellipsis">{{ f.filename }}</span>
                <span class="ft-item-size text-dim">{{ formatBytes(f.size) }}</span>
              </div>
            </li>
          </ul>
        </div>

        <!-- 资料引用 -->
        <div class="ft-sec">
          <div class="ft-sec-head">
            <span class="ft-sec-title">资料引用</span>
            <span class="ft-sec-count">{{ refFiles.length }}</span>
            <el-tooltip content="从集中资料库挂载到当前任务" placement="left">
              <el-button
                class="ft-sec-add"
                text
                size="small"
                :icon="Link"
                title="添加引用"
                @click="attachOpen = true"
              >添加</el-button>
            </el-tooltip>
          </div>
          <ul v-if="refFiles.length" class="ft-list">
            <li
              v-for="f in refFiles"
              :key="keyOf(f)"
              class="ft-item"
              @click="openPreview(f)"
            >
              <el-icon class="ft-item-icon ft-ref-icon"><component :is="Files" /></el-icon>
              <div class="ft-item-main">
                <span class="ft-item-name ellipsis">{{ f.filename }}</span>
                <span class="ft-item-size text-dim">
                  {{ formatBytes(f.size) }}
                  <el-tag v-if="f.shared" size="small" type="warning" effect="plain">共享</el-tag>
                </span>
              </div>
            </li>
          </ul>
          <div v-else class="ft-sec-empty text-dim">未引用资料 · 点击「添加」从资料库挂载</div>
        </div>
      </template>
    </div>

    <FilePreviewDialog
      v-model="previewOpen"
      :task-id="activeTaskId"
      :file="previewFile"
    />
    <LibraryAttachDialog v-model="attachOpen" @attached="reload" />
  </div>
</template>

<style scoped>
.ft { display: flex; flex-direction: column; height: 100%; min-width: 0; }
.ft-head { flex: none; display: flex; align-items: center; gap: 6px; padding: 0 12px; height: 34px; border-bottom: 1px solid var(--ls-border); }
.ft-title { font-size: 12px; color: var(--ls-fg-dim); letter-spacing: 0.5px; }
.ft-count { font-size: 11px; color: var(--ls-fg-dim); background: rgba(127, 132, 148, 0.18); border-radius: 999px; padding: 0 6px; }
.ft-body { flex: 1 1 auto; min-height: 0; overflow-y: auto; }
.ft-sec { padding: 8px 0 2px; }
.ft-sec + .ft-sec { border-top: 1px dashed var(--ls-border); }
.ft-sec-head { display: flex; align-items: center; gap: 6px; padding: 0 10px 2px; }
.ft-sec-title { font-size: 11px; color: var(--ls-fg-dim); letter-spacing: 0.5px; }
.ft-sec-count { font-size: 10px; color: var(--ls-fg-dim); opacity: 0.8; }
.ft-sec-add { margin-left: auto; font-size: 12px; height: auto; padding: 0 2px; }
.ft-sec-empty { padding: 8px 10px; font-size: 11.5px; }
.ft-list { list-style: none; margin: 0; padding: 2px 6px; }
.ft-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; cursor: pointer; }
.ft-item:hover { background: var(--ls-border); }
.ft-item-icon { flex: none; color: var(--ls-accent); font-size: 16px; }
.ft-ref-icon { color: #7a8494; }
.ft-item-main { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.ft-item-name { font-size: 12.5px; }
.ft-item-size { font-size: 11px; display: flex; align-items: center; gap: 4px; }
</style>
