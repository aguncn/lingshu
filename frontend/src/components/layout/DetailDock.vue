<script setup>
// 可折叠细节栏（spec R6 / design D2、D7）：默认收起、可展开收起，六分区——模型 / 技能 /
// 资料 / MCP / 工作空间 / 权限模板。P4~P6 后端已交付：技能与 MCP 展示当前任务真实挂载
// （caps），资料分区展示已引用的库文件并支持增删引用；权限模板仍为远期占位。
import { ArrowRight, Delete, EditPen, Plus } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'

import { detachLibraryFile } from '../../api/library'
import { formatBytes } from '../../utils/file'
import { metaOf, TASK_TYPE_META } from '../../constants'
import { useModelStore } from '../../stores/model'
import { useRegistryStore } from '../../stores/registry'
import { useSpaceStore } from '../../stores/space'
import { useTaskStore } from '../../stores/task'
import { useUiStore } from '../../stores/ui'
import EmptyState from '../common/EmptyState.vue'
import VisibilityTag from '../common/VisibilityTag.vue'
import CapMountDialog from './CapMountDialog.vue'
import LibraryAttachDialog from './LibraryAttachDialog.vue'
import ModelPanel from './ModelPanel.vue'

const ui = useUiStore()
const task = useTaskStore()
const space = useSpaceStore()
const model = useModelStore()
const reg = useRegistryStore()

const activeTask = computed(() => task.activeTask)
const workspace = computed(() =>
  activeTask.value ? space.byId[activeTask.value.space_id] ?? null : null,
)
const boundProvider = computed(() =>
  model.config ? model.providerById(model.config.provider_id) : null,
)
const typeLabel = computed(() =>
  activeTask.value ? metaOf(TASK_TYPE_META, activeTask.value.task_type).label : '',
)

// —— 挂载对话框开关（技能/MCP tile 共用同一全量编辑器，避免某类改动清空其余挂载）——
const capMountOpen = ref(false)
const attachOpen = ref(false)

// —— 名称 join 依赖注册表列表：冷启动补拉一次（getter 有缓存，空转 cheap）——
onMounted(() => {
  reg.ensureLoaded()
})

// 某个 id 的实体是否“可用”（停用/未就绪仍展示但弱化，允许挂载后在运行时忽略）
function itemOk(kind, item) {
  if (!item) return false
  if (kind === 'kbs') return item.status === 'ready'
  return !!item.enabled
}

const KIND_META = {
  skills: { title: '技能', empty: '未挂载技能', map: () => reg.bySkillId },
  mcps: { title: 'MCP', empty: '未挂载 MCP', map: () => reg.byMcpId },
  kbs: { title: '知识库', empty: '未挂载知识库', map: () => reg.byKbId },
  experts: { title: '专家', empty: '未挂载专家', map: () => reg.byExpertId },
}

// 挂载行：id → {id,name,ok}；注册表没拉全时用 #id 兜底，不空白
function mountsOf(kind) {
  const ids = task.caps[kind] || []
  const byId = KIND_META[kind].map()
  return ids.map((id) => {
    const it = byId[id]
    return { id, name: it ? it.name : `#${id}`, ok: it ? itemOk(kind, it) : false }
  })
}

// 资料分区：任务文件树里 kind=ref 的行（来自集中库的引用，字节在库、盘上无副本）
const libRefs = computed(() =>
  (task.activeTaskFiles || []).filter((f) => f.kind === 'ref' || f.library_file_id != null),
)

async function refreshFiles() {
  if (task.activeTaskId) await task.loadFiles(task.activeTaskId)
}

async function removeRef(row) {
  try {
    await detachLibraryFile(task.activeTaskId, row.id)
    await refreshFiles() // 引用移除后文件树与资料分区同步
  } catch { /* 拦截器已提示 */ }
}

const PERM_TIP = '任务权限 / 角色模板属后续后端能力，本期不提供配置'
</script>

<template>
  <div class="dd" :class="{ open: ui.detailOpen }">
    <!-- 收起/展开 开关行（常驻可见） -->
    <button type="button" class="dd-toggle" @click="ui.detailOpen = !ui.detailOpen">
      <el-icon class="dd-caret" :class="{ open: ui.detailOpen }"><ArrowRight /></el-icon>
      <span class="dd-toggle-label">细节</span>
      <template v-if="activeTask">
        <span class="dd-toggle-task ellipsis">· {{ activeTask.title }}（{{ typeLabel }}）</span>
      </template>
      <span class="dd-toggle-meta">
        <template v-if="boundProvider">
          <span class="dd-bound-dot" />
          模型已绑：{{ boundProvider.name }}
        </template>
        <span v-else-if="activeTask && !model.configLoading" class="text-dim">未绑定模型</span>
      </span>
    </button>

    <!-- 展开体：六分区 -->
    <div v-show="ui.detailOpen" class="dd-body">
      <EmptyState
        v-if="!activeTask"
        description="选择任务后在此查看与配置细节"
        tip="模型绑定、工作空间、技能/资料/MCP/权限模板分区将随选中任务刷新"
      />

      <div v-else class="dd-grid">
        <!-- 模型：实连 P3 -->
        <section class="dd-tile">
          <h4 class="dd-tile-title">模型</h4>
          <ModelPanel />
        </section>

        <!-- 工作空间 -->
        <section class="dd-tile">
          <h4 class="dd-tile-title">工作空间</h4>
          <template v-if="workspace">
            <div class="ws-name">{{ workspace.name }}</div>
            <div class="ws-meta">
              <VisibilityTag :value="workspace.visibility" />
              <span class="text-dim ws-desc">{{ workspace.description || '（无描述）' }}</span>
            </div>
            <div class="ws-id text-dim">空间 #{{ workspace.id }}</div>
          </template>
          <EmptyState v-else description="空间信息缺失" image-size="40" />
        </section>

        <!-- 技能：caps.skills 真实挂载 -->
        <section class="dd-tile">
          <h4 class="dd-tile-title">
            <span>技能</span>
            <el-button class="dd-tile-act" text size="small" :icon="EditPen" @click="capMountOpen = true">
              编辑挂载
            </el-button>
          </h4>
          <div v-loading="task.capsLoading" class="dd-tile-body">
            <template v-if="mountsOf('skills').length">
              <el-tag
                v-for="m in mountsOf('skills')"
                :key="m.id"
                size="small"
                effect="plain"
                :class="{ off: !m.ok }"
                class="dd-mount"
                disable-transitions
              >{{ m.name }}<template v-if="!m.ok"><i> · 停用</i></template></el-tag>
            </template>
            <div v-else class="dd-empty">未挂载技能</div>
          </div>
          <p class="dd-note">知识库/专家挂载在编辑器内一并调整</p>
        </section>

        <!-- MCP：caps.mcps 真实挂载 -->
        <section class="dd-tile">
          <h4 class="dd-tile-title">
            <span>MCP</span>
            <el-button class="dd-tile-act" text size="small" :icon="EditPen" @click="capMountOpen = true">
              编辑挂载
            </el-button>
          </h4>
          <div v-loading="task.capsLoading" class="dd-tile-body">
            <template v-if="mountsOf('mcps').length">
              <el-tag
                v-for="m in mountsOf('mcps')"
                :key="m.id"
                size="small"
                effect="plain"
                :class="{ off: !m.ok }"
                class="dd-mount"
                disable-transitions
              >{{ m.name }}<template v-if="!m.ok"><i> · 停用</i></template></el-tag>
            </template>
            <div v-else class="dd-empty">未挂载 MCP</div>
          </div>
        </section>

        <!-- 资料：任务已引用的库文件（kind=ref）增删 -->
        <section class="dd-tile">
          <h4 class="dd-tile-title">
            <span>资料</span>
            <el-button class="dd-tile-act" text size="small" :icon="Plus" @click="attachOpen = true">
              添加
            </el-button>
          </h4>
          <div v-if="libRefs.length" class="dd-refs">
            <div v-for="r in libRefs" :key="r.id" class="dd-ref">
              <span class="dd-ref-name ellipsis" :title="r.filename">{{ r.filename }}</span>
              <el-tag v-if="r.shared" size="small" type="warning" effect="plain">共享</el-tag>
              <span class="dd-ref-size text-dim">{{ formatBytes(r.size) }}</span>
              <el-button
                class="dd-ref-del"
                text
                size="small"
                :icon="Delete"
                title="解除引用"
                @click="removeRef(r)"
              />
            </div>
          </div>
          <div v-else class="dd-empty">未引用库资料</div>
        </section>

        <!-- 权限模板：远期占位 -->
        <section class="dd-tile">
          <h4 class="dd-tile-title">权限模板</h4>
          <EmptyState description="权限模板未接入" :tip="PERM_TIP" image-size="40" />
        </section>
      </div>
    </div>

    <!-- 挂载编辑 / 资料引用 弹层 -->
    <CapMountDialog v-model="capMountOpen" />
    <LibraryAttachDialog v-model="attachOpen" @attached="refreshFiles" />
  </div>
</template>

<style scoped>
.dd { flex: none; border-top: 1px solid var(--ls-border); background: var(--ls-panel); }
.dd-toggle {
  display: flex; align-items: center; gap: 6px; width: 100%; height: 34px; padding: 0 16px;
  border: none; background: transparent; color: var(--ls-fg); font-size: 12.5px; cursor: pointer; text-align: left;
}
.dd-toggle:hover { background: var(--ls-border); }
.dd-caret { transition: transform 0.18s; color: var(--ls-fg-dim); }
.dd-caret.open { transform: rotate(90deg); }
.dd-toggle-label { font-weight: 600; }
.dd-toggle-task { max-width: 320px; color: var(--ls-fg-dim); }
.dd-toggle-meta { margin-left: auto; display: flex; align-items: center; gap: 6px; font-size: 12px; }
.dd-bound-dot { width: 8px; height: 8px; border-radius: 50%; background: #67c23a; }
.dd-body {
  max-height: 400px; overflow-y: auto; padding: 12px 16px 16px; border-top: 1px dashed var(--ls-border);
}
.dd-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 12px; }
.dd-tile {
  display: flex; flex-direction: column; min-width: 0; padding: 10px 12px;
  border: 1px solid var(--ls-border); border-radius: 8px; background: var(--ls-bg);
}
.dd-tile-title { display: flex; align-items: center; gap: 6px; margin: 0 0 8px; font-size: 12px; font-weight: 600; color: var(--ls-fg-dim); letter-spacing: 0.5px; }
.dd-tile-act { margin-left: auto; font-size: 12px; height: auto; padding: 0 4px; }
.dd-tile-body { min-height: 26px; display: flex; flex-wrap: wrap; gap: 6px; align-content: flex-start; }
.dd-mount { cursor: default; }
.dd-mount.off { opacity: 0.55; }
.dd-mount i { font-style: normal; opacity: 0.75; }
.dd-empty { font-size: 12px; color: var(--ls-fg-dim); line-height: 24px; }
.dd-note { margin: 8px 0 0; font-size: 11px; color: var(--ls-fg-dim); }
.dd-refs { display: flex; flex-direction: column; gap: 2px; }
.dd-ref { display: flex; align-items: center; gap: 6px; font-size: 12.5px; min-width: 0; }
.dd-ref-name { flex: 1 1 auto; }
.dd-ref-size { flex: none; font-size: 11px; }
.dd-ref-del { flex: none; padding: 0; }
.ws-name { font-size: 14px; font-weight: 600; }
.ws-meta { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.ws-desc { font-size: 12px; }
.ws-id { margin-top: 6px; font-size: 11px; }
</style>
