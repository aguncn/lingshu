// 会话助手回合摘要/追溯的纯函数收敛处（session-trace-ui，design D4/D5）。
// 分类口径在此唯一实现：命令/文件按内置工具名精确匹配，MCP 按「工具名前缀命中任一已挂载
//   连接器（id/名）」判定，**未知一律落「工具」桶**——避免多组件各自猜导致口径漂移
//   （spec 只承诺按类型聚合、区分已装配与已调用，不承诺精确标签枚举，见 change Risks）。
// 统一步骤形态（服务端 trace 与 live 流式共用同构对象，保证回看与流上一致）：
//   {kind:'thinking',  text}                         —— 思考片段
//   {kind:'tool_call', name, args, decision?}        —— 工具调用；decision 由确认决策折叠而来
//   {kind:'tool_result',name, ok, summary}           —— 工具结果成败摘要
// 服务端 trace 里独立的 {kind:'confirm'} 在此折叠进紧随其前的 tool_call.decision，
// 使 live 与历史渲染同一形状；该字段不影响任何服务端契约。

// 内置命令/文件工具名（与 AgentRuntime 内置 toolkit 对齐）
const COMMAND_TOOLS = new Set(['Bash', 'PowerShell'])
const FILE_TOOLS = new Set(['Read', 'Write', 'Edit', 'Glob', 'Grep'])
// skill-kb-callable：技能取用工具统一 `skill_` 前缀；知识库检索工具固定名 knowledge_search。
// 检索工具名与技能前缀在本分类层是保留语义，判定先于 MCP 前缀匹配，避免挂载连接器同名误归。
const KB_SEARCH_TOOL = 'knowledge_search'
const SKILL_PREFIX = 'skill_'
// 桶展示顺序（摘要行按此排序，稳定可读）
const BUCKET_ORDER = ['command', 'file', 'skill', 'kb', 'mcp', 'tool']
const BUCKET_LABEL = { command: '命令', file: '文件', skill: '技能', kb: 'RAG', mcp: 'MCP', tool: '工具' }

/** 工具名 → 桶：'command' | 'file' | 'skill' | 'kb' | 'mcp' | 'tool'（未知兜底 'tool'）；空名 → null */
export function classifyTool(name, mcpKeys = []) {
  const n = name == null ? '' : String(name)
  if (!n) return null
  if (COMMAND_TOOLS.has(n)) return 'command'
  if (FILE_TOOLS.has(n)) return 'file'
  if (n === KB_SEARCH_TOOL) return 'kb'
  if (n.startsWith(SKILL_PREFIX)) return 'skill'
  // MCP：工具名前缀命中任一已挂载连接器 key（agent 工具常带 <server>_ 前缀）
  if (mcpKeys.some((k) => k != null && String(k) && n.startsWith(String(k)))) return 'mcp'
  return 'tool'
}

/**
 * 服务端 GET /messages 的 trace → 气泡 steps（confirm 折叠）。
 * 对无 trace / 旧消息返回 []（调用方照常渲染纯文本，不报错）。
 */
export function normalizeTrace(trace) {
  if (!Array.isArray(trace) || !trace.length) return []
  const out = []
  for (const s of trace) {
    if (!s || typeof s !== 'object') continue
    switch (s.kind) {
      case 'thinking': {
        const text = (s.text || '').trim()
        if (text) out.push({ kind: 'thinking', text })
        break
      }
      case 'tool_call':
        out.push({ kind: 'tool_call', name: s.name || '', args: s.args, decision: undefined })
        break
      case 'confirm': {
        // 折叠到紧邻的工具调用步骤上（展示「已放行/已拒绝」）；无前置工具调用则忽略
        const prev = out.length ? out[out.length - 1] : null
        if (prev && prev.kind === 'tool_call') prev.decision = s.decision === 'deny' ? 'deny' : 'allow'
        break
      }
      case 'tool_result':
        out.push({ kind: 'tool_result', name: s.name || '', ok: !!s.ok, summary: s.summary || '' })
        break
      default:
        break // 未知步骤类型容错跳过（向前兼容新增类型）
    }
  }
  return out
}

/**
 * 由气泡 steps 派生「一行调用摘要」：只呈现真实已调用的工具（按桶去重），
 * 并统计被用户拒绝的次数；无任何调用 → { has:false, text:'' }。
 * 例：steps=[Bash, Bash, Read, confirm(deny)] → has, text="命令 Bash·文件 Read·拒绝×1"。
 */
export function summarizeSteps(steps, { mcpKeys = [] } = {}) {
  const byBucket = Object.fromEntries(BUCKET_ORDER.map((k) => [k, {}])) // kind -> Map<name, count>
  let confirms = 0
  let denies = 0
  for (const s of steps || []) {
    if (!s) continue
    if (s.kind === 'tool_call' && s.name) {
      const bucket = classifyTool(s.name, mcpKeys) || 'tool'
      const map = byBucket[bucket]
      map[s.name] = (map[s.name] || 0) + 1
      if (s.decision === 'deny') denies += 1
    } else if (s.kind === 'confirm') {
      // 历史 trace 未折叠时也能兜底统计（normalizeTrace 通常已折叠）
      confirms += 1
      if (s.decision === 'deny') denies += 1
    }
  }
  const groups = BUCKET_ORDER
    .map((kind) => {
      const names = Object.keys(byBucket[kind])
      if (!names.length) return null
      return { kind, label: BUCKET_LABEL[kind], names, counts: byBucket[kind] }
    })
    .filter(Boolean)
  // 每桶一行：先桶标签，再逐工具名（同名多次 ×次数）
  const parts = groups.map((g) => {
    const toks = g.names.map((name) => (g.counts[name] > 1 ? `${name}×${g.counts[name]}` : name))
    return `${g.label} ${toks.join('、')}`
  })
  if (denies > 0) parts.push(`拒绝×${denies}`)
  const text = parts.join(' · ')
  return { has: groups.length > 0, text, groups, confirms, denies }
}

/**
 * 由 SSE 事件流式累积一个 live 气泡（原地更新），产出与服务端 trace 归一化后同构的 steps。
 * 供 store 调用（同一形状集中于此，纯函数便于 Node 断言；跑完仍以服务端权威 trace 覆盖）。
 * 事件→累积：
 *   thinking_delta → thinking 缓冲 + thinkingLive；text_delta → 先闭合思考再追加正文；
 *   tool_call → 闭合思考 + 追加 {kind:'tool_call',name,args}；
 *   tool_result → 闭合思考 + 追加 {kind:'tool_result',name,ok,summary}；
 *   confirm_request → 记录待确认的 tool_call 步骤（_pendingTool），供 decideStep 写回 decision。
 */
export function flushLiveThinking(bubble) {
  const text = (bubble._tb || '').trim()
  bubble._tb = ''
  bubble.thinkingLive = false
  if (text) bubble.steps.push({ kind: 'thinking', text })
}

export function foldTraceEvent(bubble, evt) {
  if (!bubble) return bubble
  if (!Array.isArray(bubble.steps)) bubble.steps = []
  switch (evt.type) {
    case 'text_delta':
      flushLiveThinking(bubble)
      bubble.content = (bubble.content || '') + (evt.delta || '')
      break
    case 'thinking_delta':
      bubble._tb = (bubble._tb || '') + (evt.delta || '')
      bubble.thinkingLive = true
      break
    case 'tool_call':
      flushLiveThinking(bubble)
      bubble.steps.push({ kind: 'tool_call', name: evt.name || '', args: evt.arguments })
      break
    case 'tool_result':
      flushLiveThinking(bubble)
      bubble.steps.push({
        kind: 'tool_result',
        name: evt.name || '',
        ok: !!evt.ok,
        summary: evt.summary || '',
      })
      break
    case 'confirm_request':
      // 标记该气泡最后一个 tool_call 为待确认（一次只挂一个确认卡片，与后端一致）
      for (let i = bubble.steps.length - 1; i >= 0; i--) {
        if (bubble.steps[i].kind === 'tool_call') {
          bubble._pendingTool = bubble.steps[i]
          break
        }
      }
      break
    default:
      break
  }
  return bubble
}

/** 二次确认回执：把 decision 写回待确认的 tool_call 步骤（返回是否命中）。 */
export function decideStep(bubble, allow) {
  if (bubble && bubble._pendingTool) {
    bubble._pendingTool.decision = allow ? 'allow' : 'deny'
    bubble._pendingTool = null
    return true
  }
  return false
}
