## Why

任务挂载的技能与知识库目前只停留在「数据挂载」，运行时并未真正**可调用**：

1. **技能 = 常驻指令注入、不可调用**：`agent_runtime` 把挂载且启用的 `skill_md` 全文拼进系统提示（`_skills_block`）。模型不是「按需用技能」，而是「开场就背着全部技能全文」——token 昂贵、技能多时互相稀释；且技能从不出现在助手回合的调用摘要里（追溯最多只能标「已装配」，永远到不了「已调用」）。
2. **知识库完全不进运行时**：`build()` 只消费 skills/experts，任务挂载的 `TaskKb` 只存数据；已有的关键词检索（`registry_kb.search_kb` → `KnowledgeChunk` top-k）没有暴露给模型，知识库问答只能靠「人在会话里贴文本」。

本变更实现「技能/知识库可调用化」：把两类能力装配为该运行**可调用的只读工具**——技能工具按需取回完整分步指令后模型按其执行；知识库检索工具（复用现有关键词 search，只检任务挂载库）把带来源的 top-k 文本块喂给模型供引用。二者走既有 `tool_call`/`tool_result` 事件通道，**自动接入会话追溯模型**（提案 1/session-trace-ui）：一旦被调用，就自动出现在该回合的 trace 与摘要行，无需另建记录机制。

## What Changes

- **agentscope-runtime（技能改为按需取用）**：移除挂载技能 `skill_md` 的常驻系统提示注入；每个「启用且 `skill_md` 非空」的挂载技能改为一个**只读技能取用工具**（如 `skill_<slug>`，描述含技能名与用途），Agent 判断任务相关时调用以取回完整分步指令、再按步骤执行；调用即产生 `tool_call`/`tool_result`，自动进 trace/摘要。
- **agentscope-runtime（知识库检索工具挂载）**：新增只读检索工具（如 `knowledge_search`，入参 `query`/可选 `top_k`），在**任务已挂载且可用的全部知识库**上执行关键词检索（复用既有切块/计分实现，不引入向量库），合并返回 top-k 文本块且每条带来源（库/文件/块序/分值）供模型引用来源；未挂载可用库时工具仍装配、空命中给明确提示。
- **只读语义与权限**：两类工具为只读，在 `strict`/`limited`/`trusted` 任何档位下都**不触发二次确认**（写/执行类确认行为不变）；调用照常写 `tool_call` 审计。
- **workbench-ui（追溯/摘要呈现）**：助手回复调用摘要行与过程明细把技能取用（`skill_` 前缀）聚为「技能」桶、知识库检索（`knowledge_search`）聚为「知识库」桶，与既有命令/文件/MCP/工具桶并列；「已装配但未调用」的技能/知识库仍以弱化标记区分，绝不混同于「已调用」。
- 无数据迁移、无新增外部依赖。

## Capabilities

### New Capabilities
<!-- 无新增能力。 -->

### Modified Capabilities
- `agentscope-runtime`: 技能由「常驻指令注入」改为「按需取用的只读技能工具」；知识库以只读检索工具进入运行时。
- `workbench-ui`: 调用摘要与过程明细对技能/知识库工具做区分呈现（新分类桶）。

## Impact

- 后端：`services/agent_runtime.py`（移除技能指令注入、装配技能/检索只读工具、desc 快照）、`services/registry_kb.py`（跨挂载库合并关键词检索）、`backend/tests/`（新工具单测 + 权限/改挂载用例）。
- 前端：`utils/trace.js`（`classifyTool`/`summarizeSteps` 增技能/知识库桶）、`components/layout/AssistantTrace.vue`（分类文案/弱化标记）。
- 行为回归点：`agent_runtime` 的系统提示不再含技能全文——涉及既有场景模板/注入用例的断言需同步（技能指令改由工具按需返回）。
- 依赖：复用 session-trace-ui 的 trace 通道（提案 1）；复用 registry_kb 关键词检索。
- 后端/数据：无迁移。
