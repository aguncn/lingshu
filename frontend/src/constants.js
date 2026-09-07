// 受控枚举 → 展示文案 / ElTag 类型。取值白名单与 backend/models.py 顶部常量保持一致。
// 组件层统一走这里映射，避免在模板里散落魔法字符串。

export const STATUS_META = {
  open: { label: '待处理', type: 'info' },
  in_progress: { label: '进行中', type: 'warning' },
  done: { label: '已完成', type: 'success' },
}

export const VISIBILITY_META = {
  private: { label: '私有', type: 'info' },
  team: { label: '团队', type: 'primary' },
  public: { label: '公开', type: 'success' },
}

export const TASK_TYPE_META = {
  fault: { label: '故障', type: 'danger' },
  change: { label: '变更', type: 'warning' },
  alert: { label: '告警', type: 'danger' },
  general: { label: '常规', type: 'info' },
}

export const PROVIDER_TYPE_META = {
  openai: { label: 'OpenAI', type: 'primary' },
  deepseek: { label: 'DeepSeek', type: 'success' },
  dashscope: { label: 'DashScope', type: 'warning' },
  local: { label: '本地', type: 'info' },
}

// —— 任务权限模式（task-permission-modes，取值白名单对齐 backend/models.TASK_PERMISSION_MODES）——
// 三档决定「模型调用工具时是否需人工二次确认」；细节可调（运行中的 run 不受影响，下次发送生效）。
export const PERMISSION_MODE_META = {
  strict: {
    label: '严格',
    type: 'danger',
    desc: '所有写/执行类工具（Bash/Write/Edit/PowerShell）都要确认，安全但频繁打断',
  },
  limited: {
    label: '有限',
    type: 'warning',
    desc: '只读与一般命令自动放行；仅删除/覆盖命令与修改本地文件（Write/Edit）时确认一次',
  },
  trusted: {
    label: '完全信任',
    type: 'success',
    desc: '全程无人工确认，模型按系统提示约束自我把关（信任模型行为）',
  },
}

export const PERMISSION_MODE_ORDER = ['strict', 'limited', 'trusted']

// —— P5 registry-center 枚举徽标（取值白名单对齐 backend/models.py 顶部常量）——
export const EXPERT_ROLE_META = {
  'ops-sme': { label: '运维专家', type: 'primary' },
  general: { label: '通用', type: 'info' },
}

export const KB_STATUS_META = {
  draft: { label: '草稿', type: 'info' },
  ready: { label: '就绪', type: 'success' },
  disabled: { label: '停用', type: 'danger' },
}

export const MCP_TRANSPORT_META = {
  stdio: { label: 'stdio', type: 'info' },
  http: { label: 'http', type: 'primary' },
}

// —— P6 library scope（列表过滤）——
export const LIBRARY_SCOPE_META = [
  { value: 'all', label: '全部' },
  { value: 'global', label: '全局' },
  { value: 'shared', label: '共享' },
  { value: 'space', label: '空间' },
]

// 未知取值兜底：仍渲染成 info 徽标而非报错
export function metaOf(map, value) {
  return (value && map[value]) || { label: value ?? '—', type: 'info' }
}
