# Design — skill-kb-callable：技能/知识库可调用化

## D1 技能改为「按需取用的只读工具」

现状 `_compose_system_prompt` 把每个启用且非空 `skill_md` 的技能全文拼进系统提示。改为：

- **不再常驻注入**：系统提示只保留角色（专家/基础人设）+ 任务上下文（+ 域模板段），不再追加 `_skills_block` 技能指令段。
- **每个可用技能 = 一个只读 FunctionTool**：内部工具名 `skill_<slug>`（slug = 技能名归一化为 ASCII 小写标识符；冲突或无法归一化时回退 `skill_<id>`，保证唯一合法）。描述 = `技能「<name>」：<description 或通用说明>。调用返回该技能完整分步操作指引，供你按步骤执行。` 工具体（sync，仅读库）返回该技能 `skill_md` 文本。
- 装配判据沿用既有门控：挂载（TaskSkill）且技能 `enabled` 且 `skill_md` 非空；停用/无指令 → 不出现为工具、不阻断。
- 通过 `agentscope.tool.FunctionTool(func, name=..., description=..., is_read_only=True)` 包成工具实例，随既有 `Toolkit(tools=[...])` 一起注册；其 schema 参数为空（无入参）。
- 结果沿既有事件通道：`ToolCallEnd`→`tool_call`、`ToolResultEnd`→`tool_result` → 服务端 trace 与 SSE 自动含该技能调用（提案 1 追溯模型自动承接），前端摘要据此分类（见 D4）。

## D2 知识库检索工具（复用现有关键词 search）

- 新增只读工具 `knowledge_search`：入参 `query: string`（必填）、`top_k: int`（可选、默认 5、上限 10，越界收敛）。描述说明语料范围 = 本任务已挂载且可用的知识库、返回带来源文本块、结果须引用来源。
- **合并检索**：`registry_kb` 现只提供单库 `search_kb(kb_id, query, top_k)`。新增 `search_kbs(kb_ids, query, top_k)`：对每个库调用既有关键词计分（切块子串命中 + 整句加权），各库取 top，再按 (score, 来源) 全局归并取 top-k；不引入新检索实现、不引向量库。
- **装配快照**：`build()` 时取任务挂载且 `KnowledgeBase.status=='ready'` 的库 id 列表闭包进工具；工具体（sync，worker 已处于 app_context）按 `query`/`top_k` 检索并返回纯文本：每条 `[来源: <库名>/<文件名> 第<n>块 得分<x>] 内容…`，供模型引用来源。
- 任务未挂载任何可用库：工具仍装配（能力清单可观察），调用返回「本任务未挂载可用知识库 / 无命中」式明确文本，不报错。

## D3 权限与审计（只读工具不触发二次确认）

- 技能取用与知识库检索均为只读；AgentScope 权限中间件对只读工具不产生 `RequireUserConfirmEvent`（写/执行类 Bash/Write/Edit/PowerShell 的 confirm 语义与档位映射不变）。在 strict/limited/trusted 下均以单测覆盖「不弹确认、直接返回」。
- 调用照常写 `tool_call` 审计（既有 `_map_event` ToolResultEnd 分支），无新审计类型；结果摘要截断沿用服务端单事件截断上限（不入密钥、不超长）。

## D4 追溯/摘要呈现（workbench-ui 前端分类）

- `utils/trace.js`：`classifyTool` 在既有 command/file/mcp/tool 之外增两桶——工具名以 `skill_` 前缀 → `skill`（标签「技能」）、工具名 == `knowledge_search` → `kb`（标签「知识库」）；`BUCKET_ORDER`/`summarizeSteps` 纳入新桶。其余未知仍落 `tool` 兜底，口径不变。
- `AssistantTrace.vue`/`ChatPane.vue`：装配弱化标记沿用 caps 计数（技能×n、知识库×n、MCP×n），措辞对齐「知识库」（当前 kbs 挂载对应 KnowledgeBase）；已被调用的技能/检索只出现在摘要「技能/知识库」桶，不双计。

## D5 装配面 desc 与改挂载生效

- `build()` 返回 desc 增/改：技能不再以「注入名」出现，改出 `skill_tools`（可用技能工具清单）；`kb` 检索工具是否装配进 desc。每次会话按任务当前挂载快照装配：运行中改挂载只影响之后新发起的 run。

## 风险与对策

- **只读工具在 DEFAULT 权限下是否会被问确认**（依赖 AgentScope 实现）：apply 首步以最小探针确认；若仍触发，则在装配层给这两类工具挂「只读免确认」规则/分组兜底。已列入 tasks 1.2 先验证。
- **工具名合法性/唯一**：slug 归一化失败回退 `skill_<id>`；描述携带人类可读技能名，前端摘要以工具名归类。
- **技能改按需后模型可能不主动调用**：技能名与用途进工具描述即是被发现面；描述缺省用统一提示。手工验收需挂技能实测一次取用。
- **skill_md / 检索结果超大**：技能工具返回全文给模型、SSE 的 tool_result 摘要仍按服务端截断上限收敛（既有 `_RESULT_LIMIT`）；检索 top_k 有上限。
- **回归**：既有「系统提示含技能指令」的测试/域模板注入断言需同步为「技能经工具取用」。
