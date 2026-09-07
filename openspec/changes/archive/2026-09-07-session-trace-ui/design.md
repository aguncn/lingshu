## Context

动机见 proposal.md。现状关键约束：

- 会话链路 `agent_session.ChatSession` 已把 `thinking_delta / tool_call / tool_result / confirm` 映射为 SSE 帧并写入 AuditLog，但 `Message`（models.py:596）只存纯文本 `role/content`；`GET /messages` 由 `message_svc.list_messages` 原样返回 `to_dict()`。
- 每次运行 `_drive` 只在成功且产生文本时写**一条**助手消息（agent_session.py:163–169，`_assistant_text` 拼接）；单任务单活动会话、一次 chat = UI 一个助手回合。因此 trace 天然可按「一条助手消息」归属。
- 摘要/截断约定已存在：`_DETAIL_LIMIT=1000`（参数）、`_RESULT_LIMIT=2000`（结果），密钥值任何出口禁出；SSE 与审计共用同一工具入参来源。
- 前端 `stores/task.js` 只消费 `text_delta / confirm_request / error`，`thinking/tool` 事件被丢弃（task.js:279 注释），结束后以 `GET /messages` 权威历史覆盖乐观气泡。
- 迁移器：`migrations/NNNN_*.sql` 按编号只执行一次，现最大 0007。

## Goals / Non-Goals

**Goals:**
- 把「已发生但易失」的运行过程固化为助手消息的可选结构化 trace，读取侧向后兼容。
- 前端会话区把助手回复渲染为「独立成行摘要行 + 正文」，可内嵌展开过程；流式期间实时累积并呈动态进行态。
- 会话正文字号 token 化并默认缩小；明/暗一致。
- SSE 事件契约、AuditLog 语义保持不动。

**Non-Goals:**
- 不改 SSE 事件类型；不改 AuditLog 结构；不接会话/审计时间线页签（workbench 时间线另行排期）。
- 技能/资料库**可调用化**、知识库检索工具挂载 = proposal 2，本设计不做。
- 不做字号用户级设置项（仅默认档位缩小为 token）。

## Decisions

### D1 存储：`messages` 增可空 JSON 列 `trace`（迁移 0008）

`ALTER TABLE messages ADD COLUMN trace TEXT;`（SQLite 以 TEXT 存 JSON，nullable）。`Message.trace` 用 SQLAlchemy `db.JSON`；`to_dict()` 仅当非 None 才输出 `"trace"`。

- 理由：trace 是助手消息自身属性（同 `model`/`run_id`），随消息行原子写入、读取免 join，天然贴合「可选新增字段、旧行 NULL 即向后兼容」的 spec 契约。
- 备选（弃）：独立子表 `message_steps` 更利于逐条增删与未来时间线复用，但本期 API/UI 均按「整条助手消息」读写，先不引入多表关联与排序复杂度；将来时间线接入需更细粒度时再迁移。

### D2 捕获点与步骤形态：worker 侧维护有序 `_steps`

在 `ChatSession` 增加有序步骤缓冲，按**事件完成序** append（保证与 SSE 顺序一致）：

| 触发 | 步骤 | 内容 |
|---|---|---|
| `ThinkingBlockDeltaEvent` 归并成连续块，遇下一个非思考事件 / run 结束先闭合 | `{kind:"thinking", text}` | 思考全文归并为一块 |
| `ToolCallEndEvent`（参数已齐） | `{kind:"tool_call", name, args}` | 入参摘要，沿用 `_DETAIL_LIMIT` |
| `ToolResultEndEvent` | `{kind:"tool_result", name, ok, summary}` | 成败+结果摘要，沿用 `_RESULT_LIMIT` |
| 二次确认回执（`_await_decisions`） | `{kind:"confirm", name, decision:"allow"\|"deny"}` | 独立步骤，记录用户放行/拒绝 |

> 实测事件顺序（与 SSE 一致）：AgentScope 在确认前先把模型要调用的工具作为 `tool_call` 事件流出
> （`ToolCallEnd` → 步骤），随后才 `RequireUserConfirmEvent` park（决策落 `confirm` 步骤），
> 续跑后**无论放行与否都会回一个 `tool_result` 结果帧**——放行 = `ok:true` 真实执行；
> 拒绝 = 工具不产生任何写副作用，但 runtime 仍回 `ok:false`、摘要为「用户拒绝」的结果帧。
> 故 trace 顺序恒为 `tool_call → confirm → tool_result`（拒绝无副作用的 tool_result 记 `ok:false`），
> 与流上事件先后一致，回看/刷新不出现 SSE 与历史不一致。

最终文本不进入步骤（消息 `content` 已存）；`_assistant_text` 拼接逻辑不变。工具入参/结果与 SSE、AuditLog 同源，**不新增任何密钥/敏感出口**。

- 备选（弃）：直接记录含 `text_delta` 的原始事件序列——体积大且与 `content` 冗余。

### D3 落库与读取：扩展 `add_assistant_message`，API 层零改动

`_drive` 成功分支改为 `message_svc.add_assistant_message(..., trace=steps or None)`；`message_svc.add_message` 增可选 `trace` 透传给 `Message`。`list_messages` 走 `to_dict()` 自动带出；纯文本/失败回合存 None → 响应省略 `trace` 字段。`api/runtime.py` 无需改动。

### D4 前端状态：store 实时累积 steps，服务端权威兜底

- `_onChatEvent` 新增分支：`thinking_delta` 累积进 live 气泡的 thinking 缓冲；`tool_call / tool_result` append 到 live 气泡 `steps` 并刷新派生摘要；确认回执沿用现有卡片路径，放行/拒绝同时写回该气泡 tool_call 步骤的 decision。
- 气泡扩展字段：`steps?: TraceStep[]`、`thinkingLive?: boolean`。结束成功的 `ensureHistory(force)` 用服务端 trace 覆盖乐观气泡 → 摘要/过程与 `GET /messages` 一致（spec 场景三）；主动中断/error 保留 live 气泡与已累积 steps（错误态），下次发送被权威历史覆盖。
- 摘要行**由 trace 派生**（前端纯函数，不冗余存储）：按类型桶聚合——命令（Bash/PowerShell）、文件（Read/Write/Edit/Glob/Grep）、MCP（名前缀匹配挂载连接器）、工具（未知兜底）、确认次数。分类函数集中在工具模块一处，未知一律落「工具」，避免分类口径漂移。
- 「已装配」弱标记读 `task.caps`（skills/mcps/kbs 计数），与「已调用」分开展示，不混同。

### D5 组件与样式

- 新增 `components/layout/AssistantTrace.vue`：入参 steps + assembled，渲染摘要行、就地展开步骤表、流式 “…” 进行态与「查看过程」入口；用于 ChatPane 的 assistant 气泡与 live 气泡。备选（弃）全内联进 ChatPane——ChatPane 已 336 行，拆组件便于复用与稳定。
- 字号：`styles/index.css` 设计令牌区增 `--ls-font-size-msg`（默认 13px，收敛原 13.5px 写死值），`.cp-bubble` 的 `font-size` 改引用该变量，`line-height:1.6` 保持，明/暗自动沿用。

## Risks / Trade-offs

- **步骤顺序/归并竞态**（thinking 紧邻首段文本、deny 工具后流继续）→ 捕获在 worker 单线程内、按事件完成序 append；thinking 以「下一事件到来」为闭合触发点；后端测试覆盖纯文本 / 拒绝 / 多工具三径。
- **trace 体积与敏感**：工具参数可能长或含路径类信息 → 沿用 `_DETAIL_LIMIT/_RESULT_LIMIT`，设计层面禁止新增密钥出口；测试逐条断言不含 api_key。
- **JSON 列 NULL 兼容**：迁移后旧行 NULL、to_dict 仅非 None 输出 → 读兼容；补后端测试。
- **摘要分类口径漂移**（新增内置工具 / MCP 工具名前缀变化）→ 分类函数收敛一处 + 未知兜底「工具」；spec 只承诺「按类型去重/聚合、区分已装配与已调用」，不承诺精确标签枚举，避免过度承诺。

## Migration Plan

- 新增 `backend/migrations/0008_message_trace.sql`（`ALTER TABLE messages ADD COLUMN trace TEXT;`）。
- 应用：`run_migrations()` 随启动 / 测试 fixture 自动按编号执行一次。
- 回滚：本期无已发布数据约束，开发期删该行重跑即可；对既有审计与历史消息无影响。
