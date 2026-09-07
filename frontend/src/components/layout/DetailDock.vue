<script setup>
// 「个性设置」卡片（原细节栏 R6 / D2、D7）：由输入框底部「个性设置」链接展开（ui.detailOpen）。
// 平时零占用；展开时以圆角卡片夹在消息区与输入框之间。
// 权限/模型/空间 都在外面有了更顺手的入口（顶栏彩框下拉、空间创建时定型），这里不再重复放——
// 只留真正要逐个配的：四类能力挂载（技能/MCP/RAG/运维专家）与 资料（库引用）。
// 每张能力 tile 的「编辑挂载」只编辑本类（单类对话框，不动其余三类，避免全量覆盖误清空）。
// 套用了运维专家档案的任务（C5 建任务自动 apply）在此一眼可见其装配效果（挂载专家/技能/MCP/RAG）。
import { ArrowDown, Delete, EditPen, Plus } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'

import { detachLibraryFile } from '../../api/library'
import { formatBytes } from '../../utils/file'
import { useRegistryStore } from '../../stores/registry'
import { useTaskStore } from '../../stores/task'
import { useUiStore } from '../../stores/ui'
import EmptyState from '../common/EmptyState.vue'
import CapMountDialog from './CapMountDialog.vue'
import LibraryAttachDialog from './LibraryAttachDialog.vue'

const ui = useUiStore()
const task = useTaskStore()
const reg = useRegistryStore()

const activeTask = computed(() => task.activeTask)

// —— 挂载编辑开关：capKind 记当前正在编辑哪一类，CapMountDialog 只呈现该类候选 ——
const capKind = ref('skills') // skills | mcps | kbs | experts
const capOpen = ref(false)
const attachOpen = ref(false)

// —— 名称 join 依赖注册表：冷启动补拉一次（getter 有缓存，空转 cheap）——
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
  kbs: { title: 'RAG', empty: '未挂载 RAG', map: () => reg.byKbId },
  experts: { title: '运维专家', empty: '未挂载运维专家', map: () => reg.byExpertId },
}
// 四类挂载 tile 共用一套渲染（caps.skills/mcps/kbs/experts 真实挂载）
const MOUNT_KINDS = ['skills', 'mcps', 'kbs', 'experts']

// 挂载行：id → {id,name,ok}；注册表没拉全时用 #id 兜底，不空白
function mountsOf(kind) {
  const ids = task.caps[kind] || []
  const byId = KIND_META[kind].map()
  return ids.map((id) => {
    const it = byId[id]
    return { id, name: it ? it.name : `#${id}`, ok: it ? itemOk(kind, it) : false }
  })
}

function openCap(kind) {
  capKind.value = kind
  capOpen.value = true
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
</script>

<template>
  <!-- 平时零占用；由输入框底部「个性设置」链接展开（ui.detailOpen） -->
  <div v-if="ui.detailOpen" class="dd">
    <div class="dd-card">
      <!-- 卡片头：标题 + 当前任务名 + 收起钮（也点链接可收起） -->
      <div class="dd-head">
        <span class="dd-head-title">个性设置</span>
        <template v-if="activeTask">
          <span class="dd-head-sep text-dim">·</span>
          <span class="dd-head-task ellipsis" :title="activeTask.title">{{ activeTask.title }}</span>
        </template>
        <el-button
          class="dd-head-close"
          text
          circle
          :icon="ArrowDown"
          title="收起个性设置"
          @click="ui.detailOpen = false"
        />
      </div>

      <div class="dd-body">
        <EmptyState
          v-if="!activeTask"
          description="选择任务后在此查看与配置个性设置"
          tip="四类能力的挂载与资料引用将随选中任务刷新"
        />

        <div v-else class="dd-grid">
          <!-- 四类能力挂载：技能/MCP/知识库/运维专家（caps 真实挂载；套用专家档案经 apply 装配后在此呈现）。
               每类的「编辑挂载」只编辑本类候选（见 CapMountDialog：仅本类多选，保存不影响其它类） -->
          <section v-for="kind in MOUNT_KINDS" :key="kind" class="dd-tile">
            <h4 class="dd-tile-title">
              <span>{{ KIND_META[kind].title }}</span>
              <el-button class="dd-tile-act" text size="small" :icon="EditPen" @click="openCap(kind)">
                编辑挂载
              </el-button>
            </h4>
            <div v-loading="task.capsLoading" class="dd-tile-body">
              <template v-if="mountsOf(kind).length">
                <el-tag
                  v-for="m in mountsOf(kind)"
                  :key="m.id"
                  size="small"
                  effect="plain"
                  :class="{ off: !m.ok }"
                  class="dd-mount"
                  disable-transitions
                >{{ m.name }}<template v-if="!m.ok"><i> · 停用</i></template></el-tag>
              </template>
              <div v-else class="dd-empty">{{ KIND_META[kind].empty }}</div>
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
        </div>
      </div>
    </div>

    <!-- 单类挂载编辑 / 资料引用 弹层 -->
    <CapMountDialog v-model="capOpen" :kind="capKind" />
    <LibraryAttachDialog v-model="attachOpen" @attached="refreshFiles" />
  </div>
</template>

<style scoped>
/* 个性设置卡片：平时不占位（根 v-if），展开时夹在消息区与输入框之间 */
.dd {
  flex: none;
  padding: 4px 16px 10px;
}
.dd-card {
  display: flex;
  flex-direction: column;
  max-height: 56vh;
  border: 1px solid var(--ls-border);
  border-radius: 12px;
  background: var(--ls-panel);
  box-shadow: 0 2px 8px rgba(20, 30, 50, 0.06);
  overflow: hidden;
}
.dd-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
  height: 36px;
  padding: 0 6px 0 14px;
  border-bottom: 1px solid var(--ls-border);
}
.dd-head-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ls-accent);
  letter-spacing: 0.5px;
}
.dd-head-sep {
  font-size: 12px;
}
.dd-head-task {
  font-size: 12.5px;
  color: var(--ls-fg-dim);
  min-width: 0;
}
.dd-head-close {
  margin-left: auto;
  color: var(--ls-fg-dim);
  flex: none;
}
.dd-body {
  overflow-y: auto;
  padding: 12px 16px 16px;
}
.dd-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 12px; }
.dd-tile {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--ls-border);
  border-radius: 8px;
  background: var(--ls-bg);
}
.dd-tile-title { display: flex; align-items: center; gap: 6px; margin: 0 0 8px; font-size: 12px; font-weight: 600; color: var(--ls-fg-dim); letter-spacing: 0.5px; }
.dd-tile-act { margin-left: auto; font-size: 12px; height: auto; padding: 0 4px; }
.dd-tile-body { min-height: 26px; display: flex; flex-wrap: wrap; gap: 6px; align-content: flex-start; }
.dd-mount { cursor: default; }
.dd-mount.off { opacity: 0.55; }
.dd-mount i { font-style: normal; opacity: 0.75; }
.dd-empty { font-size: 12px; color: var(--ls-fg-dim); line-height: 24px; }
.dd-refs { display: flex; flex-direction: column; gap: 2px; }
.dd-ref { display: flex; align-items: center; gap: 6px; font-size: 12.5px; min-width: 0; }
.dd-ref-name { flex: 1 1 auto; }
.dd-ref-size { flex: none; font-size: 11px; }
.dd-ref-del { flex: none; padding: 0; }
</style>
