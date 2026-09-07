<script setup>
// 技能中心（P5 AD-01）：列表 + 新建/编辑（name/desc/SKILL.md/enabled）+ 启停 + 删除。
// skill_md 变更由后端 version+1（record 指令文本迭代）；本面板展示版本号。
// 数据源 = registry store 的 skills，本组件不直接持列表。
import { CaretBottom, CaretRight, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import { createSkill, removeSkill, updateSkill } from '../../api/skills'
import { useRegistryStore } from '../../stores/registry'

const reg = useRegistryStore()
const list = computed(() => reg.skills)

const dialogOpen = ref(false)
const editingId = ref(null) // null=新建；有值=编辑该技能
const expandedId = ref(null) // 展开某行预览 SKILL.md
const saving = ref(false)

const form = reactive({ name: '', description: '', skill_md: '', enabled: true })

function resetForm() {
  form.name = ''
  form.description = ''
  form.skill_md = ''
  form.enabled = true
}

function openNew() {
  editingId.value = null
  resetForm()
  dialogOpen.value = true
}

function openEdit(skill) {
  editingId.value = skill.id
  form.name = skill.name || ''
  form.description = skill.description || ''
  form.skill_md = skill.skill_md || ''
  form.enabled = !!skill.enabled
  dialogOpen.value = true
}

async function submit() {
  if (!form.name.trim()) {
    ElMessage.warning('name 不能为空')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      skill_md: form.skill_md,
      enabled: form.enabled,
    }
    if (editingId.value === null) await createSkill(payload)
    else await updateSkill(editingId.value, payload)
    ElMessage.success(editingId.value === null ? '技能已创建' : '技能已更新')
    dialogOpen.value = false
    await reg.loadCategory('skills')
  } catch (e) {
    // 拦截器已弹后端 message（如重名 400）
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(skill) {
  try {
    await updateSkill(skill.id, { enabled: !skill.enabled })
    await reg.loadCategory('skills')
  } catch { /* 拦截器已提示 */ }
}

async function onDelete(skill) {
  try {
    await ElMessageBox.confirm(
      `删除技能「${skill.name}」后，所有任务对该技能的挂载将一并清理（DB 级联）。确定删除？`,
      '删除技能',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await removeSkill(skill.id)
    ElMessage.success('技能已删除')
    await reg.loadCategory('skills')
  } catch { /* 拦截器已提示 */ }
}
</script>

<template>
  <div class="rc rc-skills">
    <div class="rc-head">
      <span class="rc-title">技能库</span>
      <span v-if="list.length" class="rc-count">{{ list.length }}</span>
      <el-button class="rc-add" size="small" type="primary" :icon="Plus" @click="openNew">
        新建技能
      </el-button>
    </div>

    <div v-loading="reg.loading" class="rc-body">
      <el-empty
        v-if="!reg.loading && !list.length"
        description="暂无技能"
        :image-size="64"
      >
        <el-button size="small" type="primary" @click="openNew">创建第一个技能</el-button>
      </el-empty>

      <div v-else class="rc-list">
        <div v-for="s in list" :key="s.id" class="rc-item">
          <button type="button" class="rc-item-main" @click="expandedId = expandedId === s.id ? null : s.id">
            <el-icon class="rc-caret">
              <CaretRight v-if="expandedId !== s.id" /><CaretBottom v-else />
            </el-icon>
            <div class="rc-txt">
              <div class="rc-line1">
                <span class="rc-name">{{ s.name }}</span>
                <el-tag size="small" effect="plain" type="info">v{{ s.version }}</el-tag>
                <el-tag size="small" :type="s.enabled ? 'success' : 'info'">
                  {{ s.enabled ? '启用' : '停用' }}
                </el-tag>
              </div>
              <div v-if="s.description" class="rc-sub">{{ s.description }}</div>
            </div>
          </button>

          <div class="rc-ops">
            <el-switch
              size="small"
              :model-value="!!s.enabled"
              @change="toggleEnabled(s)"
            />
            <el-button text size="small" @click="openEdit(s)">编辑</el-button>
            <el-button text size="small" type="danger" @click="onDelete(s)">删除</el-button>
          </div>

          <pre v-if="expandedId === s.id" class="rc-md">{{ s.skill_md || '（无 SKILL.md 内容）' }}</pre>
        </div>
      </div>
    </div>

    <el-dialog
      v-model="dialogOpen"
      :title="editingId === null ? '新建技能' : '编辑技能'"
      width="560px"
      append-to-body
    >
      <el-form label-width="86px" label-position="left">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：sql-analysis" maxlength="128" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="一句话说明用途（可选）" maxlength="512" />
        </el-form-item>
        <el-form-item label="SKILL.md">
          <el-input
            v-model="form.skill_md"
            type="textarea"
            :rows="8"
            placeholder="技能指令全文（Markdown）。内容变更时后端自动版本 +1"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* 各 center 共用一套 .rc 卡片网格样式（C4：行 → 卡；dark 兼容走 CSS 变量） */
.rc { display: flex; flex-direction: column; height: 100%; min-width: 0; }
.rc-head { display: flex; align-items: center; gap: 8px; padding: 2px 2px 10px; }
.rc-title { font-size: 13px; font-weight: 600; }
.rc-count { font-size: 11px; color: var(--ls-fg-dim); background: rgba(127,132,148,.18); border-radius: 999px; padding: 0 6px; }
.rc-add { margin-left: auto; }
.rc-body { flex: 1 1 auto; min-height: 0; overflow-y: auto; }
.rc-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; align-content: start; }
.rc-item { display: flex; flex-direction: column; border: 1px solid var(--ls-border); border-radius: 8px; background: var(--ls-bg); }
.rc-item-main { display: flex; align-items: flex-start; gap: 6px; width: 100%; padding: 10px 12px 6px; border: none; background: transparent; color: var(--ls-fg); text-align: left; cursor: pointer; }
.rc-caret { margin-top: 2px; flex: none; color: var(--ls-fg-dim); }
.rc-txt { flex: 1 1 auto; min-width: 0; }
.rc-line1 { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.rc-name { font-size: 13px; font-weight: 600; }
.rc-sub { font-size: 12px; color: var(--ls-fg-dim); margin-top: 2px; }
.rc-ops { display: flex; align-items: center; gap: 2px; padding: 6px 10px 8px 12px; margin-top: 6px; border-top: 1px dashed var(--ls-border); flex-wrap: wrap; }
.rc-md { margin: 0 10px 10px 12px; padding: 10px; background: #0d1117; color: #d6dde8; border-radius: 6px; font-family: Consolas, monospace; font-size: 11.5px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; max-height: 240px; overflow-y: auto; }

/* —— C6 版末：每类能力一套强调色（技能=violet，var(--cc) 见 index.css）。卡片 = 顶缘彩线 + 浅彩卡底，
     名称行与底部操作行刻意压淡、让中间描述句着色出挑，hover 轻浮起给「可交互」注意 —— */
.rc-list { grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 14px; row-gap: 14px; }
.rc-item {
  border-top: 2px solid var(--cc);
  background: var(--cc-soft);
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}
.rc-item:hover { border-color: var(--cc); box-shadow: 0 4px 14px rgba(15, 23, 42, 0.1); transform: translateY(-1px); }
.rc-name { color: var(--ls-fg-dim); }
.rc-sub { color: var(--cc); font-weight: 600; }
.rc-count { color: var(--cc); background: var(--cc-soft2); }
</style>
