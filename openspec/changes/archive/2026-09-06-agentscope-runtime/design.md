## Context

- 现状：P1~P7 已交付任务/模型/挂载/资料库的数据与管理面，但**无任何运行时代码**——`backend/` 无一处 `import agentscope`；无 `Message`/`AuditLog` 表（`schema_version`=5）。复用入口已确认：`model_service.get_task_config(task_id)`（含 provider_id/model_name/temperature/max_tokens）、`model_service.get_provider_or_raise()`（含 `api_key_enc`）、`capability.load_mounted(task_id)`（任务挂载四类）、`crypto.decrypt()`（Fernet，`LINGSHU_MASTER_KEY`/.env）；MCP 连接器敏感配置（env/headers）为密文列、出口只给键名。
- 设计 §7 的代码片段是**早期示意、与已装 AgentScope 不一致**：真实版本是 `agentscope 2.0.7.post1`（pyproject 已锁），API 以本设计「已核对事实」为准，spec 契约不受影响。

## Goals / Non-Goals

**Goals**：可跑通的对话运行时——任务模型解析、Agent+Toolkit 组装（含挂载能力）、SSE 流式事件、危险工具二次确认、历史落库、运行时审计；全部可离线测试（打桩模型，不依赖真实 API key / 外网 / 真实 MCP 进程）。

**Non-Goals**：知识库检索注入（RAG，P9 场景模板）；多专家 `composed_of` 编排（P1，仅单专家 system_prompt）；前端会话区接线（后续前端 change）；P10 全量写操作审计（本提案只落模型/工具/确认事件）；自动化/定时触发。

## Decisions

### D1 运行时装配所需的「已核对」AgentScope 2.0.7.post1 API
关键事实（probe 于 `.venv`，apply 期若再漂移以本地包为准并回写本设计）：
- 模型：`OpenAIChatModel(credential=OpenAICredential(*, api_key: SecretStr, base_url: str|None, ...), model: str, parameters: OpenAIChatModel.Parameters|None, stream: bool, ...)`。`base_url` 支持 OpenAI 兼容端点（DeepSeek / ccswitch）；温度/长度类生成参数放 `parameters`（属性名 apply 核对）。
- Agent：`Agent(name, system_prompt, model, toolkit, middlewares=[...], react_config=ReActConfig(...), injection_config=..., model_config=..., context_config=..., state=...)`。无独立 `ReActAgent`；给出 `toolkit` + `react_config` 即走 ReAct。公开方法 `reply_stream(inputs)`/`reply(inputs)`/`observe`/`compress_context`。
- 消息/事件：`Msg` 内容为 typed block；事件对象（`agentscope.event`）含 `TextBlockDeltaEvent/ThinkingBlockDeltaEvent/ToolCallStartEvent/ToolResult.../RequireUserConfirmEvent/RequireExternalExecutionEvent/UserInterruptEvent/ReplyEndEvent` 等。
- Toolkit：`Toolkit(tools=[...], mcps=[MCPClient...], ...)`；内置工具直接可 import：`agentscope.tool` 的 `Bash/Read/Write/Edit/Glob/Grep`（Windows 下另有 `PowerShell`）。
- MCP：`agentscope.mcp` 的 `MCPClient` + `StdioMCPConfig`/`HttpMCPConfig`，经 Toolkit 注册（`mcps=[...]`）。
- Permission：`agentscope.permission` 的 `PermissionEngine/PermissionMode/PermissionRule/PermissionBehavior`。

### D2 模型装配：ModelProvider+ModelConfig → 可运行模型
`model_factory.py`：
1. `config = model_service.get_task_config(task_id)`；无 → 抛可读错（由端点转为 SSE `error`）。
2. `provider = model_service.get_provider_or_raise(config["provider_id"])`。
3. 密钥解析顺序：若存在匹配该供应商的环境变量覆盖（`LINGSHU_<NAME>_API_KEY`，NAME 取供应商名大写化，如 `LINGSHU_DEEPSEEK_API_KEY`）→ 用之；否则 `crypto.decrypt(provider.api_key_enc)`；两者皆无 → 可读错。
4. 组 `OpenAICredential(api_key=SecretStr(key), base_url=provider.base_url)` 与 `OpenAIChatModel(credential=..., model=config.model_name or provider.default_model, parameters=<temperature/max_tokens 若有则注入>)`。
5. 出口/日志不含密钥明文（`SecretStr` 自带脱敏）。
- 备选：直接用 `CredentialFactory` 注册供应商模板 → 多一层映射但同样可行；单人单供应商常用 env 覆盖，选用直构 + env 优先级最简。

### D3 Agent 组装与系统提示拼接（AgentRuntime.build）
`agent_runtime.py::build()`：消费任务 + 模型 + `capability.load_mounted(task_id)`（P4）+ 挂载实体明细（P5 skill_md / P3 专家 system_prompt / MCP 配置）：
- **system_prompt 拼接序**：基础运维助手人设 → 任务上下文（任务标题/空间/类型）→ 挂载技能 `skill_md`（v0.3 语义：技能=指令段注入，§7.4）→ 挂载专家 `system_prompt`（单专家，优先于基础人设的角色部分）。（知识库检索段留 P9。）
- **Toolkit**：内置工具全量（Bash/Read/Write/Edit/Glob/Grep；Windows 运行环境加 PowerShell 等价）→ 挂载且启用的 MCP 经 `mcp_client.py` 实例化注册。停用/未就绪实体跳过（与 caps 语义一致）。
- 工具元数据（名称/描述）可只读导出供审计/测试断言，不属密钥。
- `build()` 返回 (agent, 描述 dict)；可测试：用打桩模型断言 `system_prompt` 含技能与专家文本、toolkit 含挂载工具与内置工具名。

### D4 SSE 驱动与二次确认：park/continue 会话环（§7.6 旧骨架不足以支持 confirm）
2.0.7 的 `reply_stream` 是 **park/continue**：Agent 需要外部确认/执行时，流先 `yield` 一个 `RequireUserConfirmEvent` 并**返回（暂停该次 reply）**；运行方必须**另一次** `agent.reply_stream(UserConfirmResultEvent(...))` 续跑同一会话（Agent 内在 memory/state 记住待办工具调用）。§7.6 的「单生成器只转发、永不再喂入」无法完成确认，故驱动采用：
- **每任务至多一个活动 Session**（内存注册表 `task_id → Session`，含：agent、持有线程+独立 asyncio loop、`msg_queue`（→SSE）、`decision_queue`（收确认回执）、当前 `run_id`、agent state/memory）。发起 chat 时已有活动 Session → 409（spec R2）。
- 驱动循环（worker 线程内跑独立 loop）：`input = UserMsg(...)` → `async for evt in agent.reply_stream(input)`：
  - 文本/思考/工具事件 → 序列化进 `msg_queue`；
  - 遇 `RequireUserConfirmEvent` → 广播 `confirm_request`（含确认所需动作摘要），然后**停在等待**：从 `decision_queue` 取用户回执（带超时/可中断）；取到后 `input = UserConfirmResultEvent(...)` 续跑（放行则工具执行、拒绝则 Agent 收拒绝结果）；
  - 遇 `RequireExternalExecutionEvent`：本提案不引入外部执行器（内置工具与 MCP 工具注册进 Toolkit 即由 Agent 内部执行），此类事件视为不应出现；若出现则记审计并按拒绝处理，避免悬挂。
  - 终态事件 / `ReplyEndEvent` → 广播 `done`，持久化助手最终文本。
- Flask SSE：`Response(stream_with_context(gen()))`；`gen()` 从 `msg_queue` 读并 `yield "data: " + json.dumps(evt) + "\n\n"`；连接断开（生成器 close/异常）→ 通知 worker 走 teardown（向 loop 投 `UserInterruptEvent` 取消在跑的 reply、关 MCP 客户端、移除注册表项），保证「流结束后可再次发起」。
- 事件 → SSE 类型映射（表）：`TextBlockDelta→text_delta`、`ThinkingBlockDelta→thinking_delta`、`ToolCall…→tool_call`、`ToolResult…→tool_result`、`RequireUserConfirmEvent→confirm_request`、`ReplyEnd→done`；统一附 `run_id`。文本由 delta 累积成最终 `text`。
- 线程模型备选：换 `waitress/gevent` 或多 worker → 引入并发复杂度；单人单线程 + 每任务独占 worker 线程最简且够用。确认回执经 `POST /chat/decision` 投递到 `decision_queue`（跨请求唤醒），无需同一条 HTTP 连接回写。

### D5 危险工具二次确认的接法与护栏
- 目标可观察行为（spec R4）：Bash/Write/Edit 被请求时先 `confirm_request`、未放行不执行。接法分两层，apply 期以 2.0.7 实机为准（两层都保留在 spec 契约内）：
  1. **PermissionEngine**：给内置写/执行类工具配 confirm 模式规则（`agentscope.permission`），使触发时 agent 产出 `RequireUserConfirmEvent`；
  2. 若工具层以 `requires_confirm` 等属性直接声明，则以工具声明为准配置，避免引擎与工具双重触发。
- 护栏：同一 `confirm_id` 只可回执一次（消费后失效 → 404）；决策写审计（allow/deny、触发方 user）；`decision` 端点对失效 run/confirm → 404（spec R4）。拒绝路径把「用户已拒绝」作为工具结果喂回 Agent，避免 Agent 以为工具成功。
- 备选：运行时把 `PermissionMode` 直接设 auto/deny → 丢失「二次确认」能力，违背用户诉求；不取。

### D6 数据模型与迁移：Message + AuditLog
`migrations/0006_agent_runtime.sql`（migrate.py 升至 schema 6；风格对齐 0004/0005）：
- `messages(id, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, run_id TEXT, model TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)` + `idx_messages_task_id`。
- `audit_log(id, task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL, run_id TEXT, actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT, result TEXT, detail TEXT, created_at TEXT NOT NULL)` + `idx_audit_log_task_id`。列保持通用以兼容 P10 全量审计扩展（P10 再覆盖 spaces/tasks/… 写操作与列表端点）。
- `models.py` 新增 `Message`/`AuditLog`（`to_dict` 出口可控）；`message.py` 封装记录/列表、`audit.py` 封装记录（含字段白名单、长参数截断与密钥脱敏）。
- SQLite 布尔/文本约定与既有迁移一致（`PRAGMA foreign_keys=ON` 每连接已启用，级联可靠）。

### D7 测试策略（全离线）
- **打桩模型**：以脚本化回复的 FakeModel（实现 `reply_stream` 异步生成器：先 `text_delta`，或先请求工具→由真实 Toolkit 执行→再收尾文本；或触发一次工具确认后由测试驱动 `/decision`）替真实模型跑**真实 Agent+Toolkit+驱动**，从而覆盖：事件流映射、MCP 工具注册（不真 spawn——用 `StdioMCPConfig` 指向不存在命令断言注册不崩溃，或整块 mock）、确认 park/continue、消息落库、审计落库。无需网络/API key。
- 鉴权/错误路径：404/400/409、无模型→首事件 error、重复 chat 409。
- 集成冒烟（可选、带 key 才跑）：`LINGSHU_*_API_KEY` 存在时对种子任务发「你好」，断言收到文本与 done；无 key 自动 skip。

## Risks / Trade-offs

- [2.0.7 park/continue 续跑的确切调用形态（reply_stream 再次入参与 loop 编排）与 Permission→`RequireUserConfirmEvent` 的实际钩子] → D4/D5 保留接口级契约，apply 首日以最小打桩 Agent 先打通「确认→放行→继续」，跑通后再接真实 Permission；发现漂移即回写本设计。
- [`parameters` 字段名/温度注入位置随版本不同] → D2 以 `parameters=` 为目标，apply 期用 `inspect.signature` 核对（已核对 `OpenAIChatModel.Parameters` 存在）。
- [MCP stdio 真实进程在测试环境拉起/清理] → 测试不真实 spawn；运行期 Session teardown 对已连接 MCP 客户端 LIFO close（§7.2）。
- [会话驻留线程/loop 资源泄漏或断连悬挂] → 每任务单 Session + SSE 断开即 teardown（投 `UserInterruptEvent`、清注册表、close 客户端）；decision 带超时防永久等。
- [审计/事件误带密钥] → audit 字段白名单 + 参数截断；模型/工具事件不含 env/header/API key（spec R3/R6 有断言测试）。
- [运行时真实模型调用在 CI 不可用] → 全量测试打桩离线；真实 key 冒烟标记 skip。

## Migration Plan

- 新增 `backend/migrations/0006_agent_runtime.sql`（`messages`、`audit_log` + 索引）；`migrate.py` 启动自动按序执行升至 `schema_version=6`（真实库 5→6，一次性，无向下迁移，单人本地可重建）。
- 新端点注册 `runtime_bp`（`url_prefix=/api`）于 `app.py`；不触碰既有路由与表。
- 交付顺序：迁移/模型 → message/audit 服务 → model_factory → mcp_client → build() → 驱动+SSE → 端点 → 审计接线 → 全量测试。

## Open Questions

以下可在 apply 期间用打桩实验确定、不影响 spec 契约或任务拆分，故不开新 artifact：
- D2 `OpenAIChatModel.Parameters` 中温度/最大 token 的确切字段名与传入形态。
- D5 PermissionEngine 与工具 `requires_confirm` 二者中由谁产出 `RequireUserConfirmEvent`（以实机最小实验为准，契约不变）。
- D4 是否需要在 `RequireUserConfirmEvent` 之外单独处理 `HintBlockEvent`/`ThinkingBlockEvent` 的合并粒度（仅影响事件细分，不影响 done/text 契约）。
