<script setup>
// MCP 连接器中心（P5 AD-02）：列表 + 新建/编辑（transport 条件字段）+ 启停/trust + 行内『测试』。
// 安全：env/headers 值 Fernet 密文入库、出口只给键名 → 编辑时不回显旧值，
//   「填写即整体替换 / 勾选清除即置空 / 留空保持不变」三种语义。
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import { createMcp, removeMcp, testMcp, updateMcp } from '../../api/mcps'
import { MCP_TRANSPORT_META, metaOf } from '../../constants'
import { useRegistryStore } from '../../stores/registry'

const reg = useRegistryStore()
const list = computed(() => reg.mcps)

const dialogOpen = ref(false)
const editingId = ref(null)
const saving = ref(false)
// 测试结果弹层 { open, ok, data }：初始即对象，避免模板 v-model="test.open" 在空 ref 上求值崩溃
const test = ref({ open: false, ok: true, data: {} })

const form = reactive({
  name: '', transport: 'stdio', command: '', argsText: '', url: '',
  envText: '', envClear: false, headersText: '', headersClear: false,
  trust: false, enabled: true,
})

function resetForm() {
  form.name = ''
  form.transport = 'stdio'
  form.command = ''
  form.argsText = ''
  form.url = ''
  form.envText = ''
  form.envClear = false
  form.headersText = ''
  form.headersClear = false
  form.trust = false
  form.enabled = true
}

function parseArgs(text) {
  return text.split('\n').map((x) => x.trim()).filter(Boolean)
}

// key=value 多行 → 对象；空 → null（沿用 undefined 语义由调用方区分）
function parseKeyValue(text) {
  const lines = text.split('\n').map((x) => x.trim()).filter(Boolean)
  if (!lines.length) return null
  const obj = {}
  for (const line of lines) {
    const idx = line.indexOf('=')
    if (idx <= 0) continue // 无 '=' 或空键名：跳过该行，不误伤整段
    obj[line.slice(0, idx).trim()] = line.slice(idx + 1).trim()
  }
  return obj
}

function openNew() {
  editingId.value = null
  resetForm()
  dialogOpen.value = true
}

function openEdit(mcp) {
  editingId.value = mcp.id
  form.name = mcp.name || ''
  form.transport = mcp.transport || 'stdio'
  form.command = mcp.command || ''
  form.argsText = (mcp.args || []).join('\n')
  form.url = mcp.url || ''
  form.envText = ''
  form.envClear = false
  form.headersText = ''
  form.headersClear = false
  form.trust = !!mcp.trust
  form.enabled = !!mcp.enabled
  dialogOpen.value = true
}

async function submit() {
  if (!form.name.trim()) { ElMessage.warning('name 不能为空'); return }
  if (form.transport === 'stdio' && !form.command.trim()) {
    ElMessage.warning('stdio 传输必须提供启动 command'); return
  }
  if (form.transport === 'http' && !form.url.trim()) {
    ElMessage.warning('http 传输必须提供 url'); return
  }
  const base = {
    name: form.name.trim(),
    transport: form.transport,
    enabled: form.enabled,
  }
  // transport 端专属字段只在创建/切到该端时下发；避免 http 保留陈旧 command 语义歧义
  if (form.transport === 'stdio') {
    base.command = form.command.trim()
    const args = parseArgs(form.argsText)
    if (args.length) base.args = args
    else if (editingId.value !== null) base.args = []
  } else {
    base.url = form.url.trim()
  }
  // env/headers：编辑态三语义（留空不变 / 填写替换 / 勾选清除）
  if (editingId.value === null) {
    const env = parseKeyValue(form.envText)
    const headers = parseKeyValue(form.headersText)
    if (env) base.env = env
    if (headers) base.headers = headers
  } else {
    const env = parseKeyValue(form.envText)
    if (form.envClear) base.env = null
    else if (env) base.env = env
    const headers = parseKeyValue(form.headersText)
    if (form.headersClear) base.headers = null
    else if (headers) base.headers = headers
  }
  if (form.trust) base.trust = true // 仅新建/编辑时允许置 true；false 不改（trust 门控语义归 P8）

  saving.value = true
  try {
    if (editingId.value === null) await createMcp(base)
    else await updateMcp(editingId.value, base)
    ElMessage.success(editingId.value === null ? '连接器已创建' : '连接器已更新')
    dialogOpen.value = false
    await reg.loadCategory('mcps')
  } catch { /* 拦截器已提示 */ } finally {
    saving.value = false
  }
}

async function toggleEnabled(mcp) {
  try {
    await updateMcp(mcp.id, { enabled: !mcp.enabled })
    await reg.loadCategory('mcps')
  } catch { /* 拦截器已提示 */ }
}

async function runTest(mcp) {
  // 注意：切勿把 test 置回 null——模板 v-model="test.open" 会在 await 间隙以 null 渲染崩溃
  try {
    const data = await testMcp(mcp.id)
    test.value = { open: true, ok: !!data.ok, data }
  } catch (e) {
    test.value = { open: true, ok: false, data: { reason: e?.message || '测试调用失败' } }
  }
}

async function onDelete(mcp) {
  try {
    await ElMessageBox.confirm(
      `删除连接器「${mcp.name}」后，相关任务挂载将一并清理。确定删除？`,
      '删除 MCP 连接器',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await removeMcp(mcp.id)
    ElMessage.success('连接器已删除')
    await reg.loadCategory('mcps')
  } catch { /* 拦截器已提示 */ }
}

function transportLabel(t) { return metaOf(MCP_TRANSPORT_META, t).label }
</script>

<template>
  <div class="rc">
    <div class="rc-head">
      <span class="rc-title">MCP 连接器</span>
      <span v-if="list.length" class="rc-count">{{ list.length }}</span>
      <el-button class="rc-add" size="small" type="primary" :icon="Plus" @click="openNew">
        新建连接器
      </el-button>
    </div>

    <div v-loading="reg.loading" class="rc-body">
      <el-empty v-if="!reg.loading && !list.length" description="暂无 MCP 连接器" :image-size="64">
        <el-button size="small" type="primary" @click="openNew">创建第一个连接器</el-button>
      </el-empty>

      <div v-else class="rc-list">
        <div v-for="m in list" :key="m.id" class="rc-item">
          <div class="rc-item-main no-btn">
            <div class="rc-txt">
              <div class="rc-line1">
                <span class="rc-name">{{ m.name }}</span>
                <el-tag size="small" effect="plain">{{ transportLabel(m.transport) }}</el-tag>
                <el-tag size="small" :type="m.enabled ? 'success' : 'info'">
                  {{ m.enabled ? '启用' : '停用' }}
                </el-tag>
              </div>
              <div class="rc-sub">
                {{ m.transport === 'stdio' ? (m.command || '—') : (m.url || '—') }}
              </div>
              <div class="rc-sub">
                环境变量 {{ (m.env_keys || []).length }} · 请求头 {{ (m.headers_keys || []).length }}
                <el-tag v-if="m.trust" size="small" type="warning" effect="plain">trust</el-tag>
              </div>
            </div>
          </div>
          <div class="rc-ops">
            <el-button text size="small" @click="runTest(m)">测试</el-button>
            <el-switch size="small" :model-value="!!m.enabled" @change="toggleEnabled(m)" />
            <el-button text size="small" @click="openEdit(m)">编辑</el-button>
            <el-button text size="small" type="danger" @click="onDelete(m)">删除</el-button>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialogOpen" :title="editingId === null ? '新建 MCP 连接器' : '编辑 MCP 连接器'" width="600px" append-to-body>
      <el-form label-width="92px" label-position="left">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="128" placeholder="如：db-ops-mcp" />
        </el-form-item>
        <el-form-item label="传输方式">
          <el-radio-group v-model="form.transport">
            <el-radio-button value="stdio">stdio（本地命令）</el-radio-button>
            <el-radio-button value="http">http（远程端点）</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <template v-if="form.transport === 'stdio'">
          <el-form-item label="启动命令" required>
            <el-input v-model="form.command" maxlength="256" placeholder="如：npx -y @modelcontextprotocol/server-xxx" />
          </el-form-item>
          <el-form-item label="启动参数">
            <el-input v-model="form.argsText" type="textarea" :rows="3" placeholder="每行一个参数（可选）" />
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="端点 URL" required>
            <el-input v-model="form.url" maxlength="512" placeholder="http(s)://host:port/mcp" />
          </el-form-item>
        </template>

        <template v-if="editingId === null">
          <el-form-item label="环境变量">
            <el-input v-model="form.envText" type="textarea" :rows="3" placeholder="每行 KEY=value（可选，整体加密存储）" />
          </el-form-item>
          <el-form-item label="请求头">
            <el-input v-model="form.headersText" type="textarea" :rows="3" placeholder="每行 KEY=value，如 Authorization=Bearer xxx（可选）" />
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="环境变量">
            <el-input v-model="form.envText" type="textarea" :rows="3"
              :placeholder="`现有键：${(editingId ? list.find((x) => x.id === editingId)?.env_keys || [] : []).join('、') || '无'}\n留空=保持不变；填写=整体替换`" />
            <div class="rc-clear"><el-checkbox v-model="form.envClear">清除全部环境变量</el-checkbox></div>
          </el-form-item>
          <el-form-item label="请求头">
            <el-input v-model="form.headersText" type="textarea" :rows="3"
              :placeholder="`现有键：${(editingId ? list.find((x) => x.id === editingId)?.headers_keys || [] : []).join('、') || '无'}\n留空=保持不变；填写=整体替换`" />
            <div class="rc-clear"><el-checkbox v-model="form.headersClear">清除全部请求头</el-checkbox></div>
          </el-form-item>
        </template>

        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="test.open" title="MCP 连通性测试" width="520px" append-to-body>
      <template v-if="test.ok">
        <el-alert type="success" :closable="false" show-icon title="连接成功" />
        <p v-if="test.data.tools && test.data.tools.length" class="rc-test-note">
          暴露 {{ test.data.tool_count ?? test.data.tools.length }} 个工具：
        </p>
        <ul v-if="test.data.tools && test.data.tools.length" class="rc-tools">
          <li v-for="(t, i) in test.data.tools" :key="i">
            <code>{{ t.name }}</code>
            <span v-if="t.description" class="text-dim"> — {{ t.description }}</span>
          </li>
        </ul>
      </template>
      <el-alert v-else type="error" :closable="false" show-icon title="连接失败" :description="test.data.reason" />
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
.rc-sub { font-size: 12px; color: var(--ls-fg-dim); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rc-ops { display: flex; align-items: center; gap: 2px; margin-top: 6px; }
.rc-clear { margin-top: 2px; }
.rc-test-note { font-size: 13px; }
.rc-tools { margin: 6px 0 0; padding-left: 18px; font-size: 12.5px; }
.rc-tools code { background: rgba(127,132,148,.15); padding: 0 4px; border-radius: 3px; }
</style>
