## Purpose

智能体运行时：把任务绑定的模型（ModelProvider+ModelConfig）与已挂载能力（技能 / MCP / 专家）组装为可对话的 Agent，通过 SSE 提供流式对话、危险工具二次确认、历史消息读取与运行时审计——消费 P2~P5 的数据，供后续 P9 场景模板与前端会话区接入。

## ADDED Requirements

### Requirement: 会话发起与任务模型解析

系统 SHALL 提供 `POST /api/tasks/<id>/chat`（请求体 JSON 含非空 `message`）发起一次智能体对话：任务不存在 → 404 JSON；body 缺 `message` 或为空 → 400 JSON。任务的运行模型 SHALL 来自其已绑定的 ModelConfig（消费 P3）：无有效绑定、或所绑供应商无可用密钥、或模型不可构造时，不得静默失败——响应 SHALL 以 `text/event-stream` 开启并首先发出一个 `error` 类型事件（含可读原因）后结束，不产生对话消息副作用。密钥解析 SHALL 优先取运行环境提供的对应供应商环境变量密钥（如 `LINGSHU_<供应商>_API_KEY`），否则解密库内 Fernet 密文（`LINGSHU_MASTER_KEY`/`.env`）；任何出口不得含密钥明文。

#### Scenario: 任务不存在或请求非法

- **WHEN** 用户对不存在的任务 id 发起 chat，或请求体缺少/为空 `message`
- **THEN** 分别返回 404 与 400（JSON），不建立会话、不写任何记录

#### Scenario: 无可用模型时给出可读错误

- **WHEN** 用户对未绑定模型、或所绑供应商无可用密钥的任务发起 chat
- **THEN** 响应为 `text/event-stream`，首个事件为 `error`（消息含可读原因），随后流正常结束；Messages 与 AuditLog 不出现该次伪对话

### Requirement: 流式对话事件契约与会话生命周期

系统 SHALL 以 SSE（`text/event-stream`，UTF-8）逐条返回事件，每条 `data:` 为一个 JSON 对象，含 `type` 字段与 `run_id`。事件类型至少含：`text_delta`（助手回答增量文本）、`text`（助手整段文本）、`thinking_delta`、`tool_call`（含工具名与参数）、`tool_result`（含工具名、成败与摘要）、`confirm_request`（见「危险工具二次确认」）、`error`、`done`。流 SHALL 以 `done` 事件收尾并结束连接。同一任务同一时刻 SHALL 至多有一个活动的会话运行：已有一个运行中会话时再次发起 chat → 409 JSON（可读消息）；连接关闭/流结束后该任务即可再次发起。`run_id` SHALL 标识一次从发起到 `done` 的完整运行，供确认回执与消息/审计关联。

#### Scenario: 正常对话打字机流式返回

- **WHEN** 用户向已绑定可用模型的任务发送一条消息
- **THEN** 响应为 SSE，依序出现 0..n 个 `text_delta`/`thinking_delta`，末尾出现 `done` 后连接结束；全部事件带同一 `run_id` 且为合法 UTF-8 JSON

#### Scenario: 单任务并发互斥

- **WHEN** 某任务已有会话正在流式运行，用户再次对其发起 chat
- **THEN** 返回 409 JSON 与可读消息；原会话不受影响，结束后可再次正常发起

### Requirement: 任务挂载能力注入

系统 SHALL 在组装对话 Agent 时消费任务的挂载能力（P4/P5 数据），并在一次运行中生效：已挂载且可用的技能（TaskSkill）其指令文档 SHALL 注入 Agent 的指令上下文使其可遵循；已挂载且可用的专家（TaskExpert）其系统人设 SHALL 参与角色塑造（单专家人设；多专家协作编排不在本提案）；已挂载且可用的 MCP 连接器（TaskMcp）SHALL 被实例化为该运行可调用的工具集（消费 P5 的 transport/env 配置，密钥解密且不回显）。Agent 调用工具时流上出现对应 `tool_call`/`tool_result` 事件。停用/未就绪的挂载实体 SHALL 被跳过，不阻断对话。无任何挂载时 SHALL 仍能进行不依赖工具的普通问答。

#### Scenario: 挂载工具可被调用并流出事件

- **WHEN** 某任务挂载了一个可用 MCP 连接器后发起对话，Agent 决定调用其某工具
- **THEN** 流上出现该工具的 `tool_call`（含工具名与参数）与随后的 `tool_result`（含成败与摘要）；密钥值不出现于任何事件

#### Scenario: 技能与专家人设生效、停用实体被跳过

- **WHEN** 某任务挂载了技能与专家（人设文本）、另挂了一个停用的 MCP，随后发起对话
- **THEN** Agent 的组装输入含技能指令与专家人设（模型收到的系统提示可观察）；停用连接器不出现于可用工具；无挂载的任务仍可完成普通问答

### Requirement: 危险工具二次确认

系统 SHALL 对内置命令执行/写类工具（Bash/Write/Edit 及等价物）的调用默认执行二次确认：Agent 请求此类工具时不得立即执行，流上 SHALL 先发出 `confirm_request`（含该次运行的 `run_id`、`confirm_id`、工具名、将执行的动作摘要与原因），运行进入等待确认态。系统 SHALL 提供 `POST /api/tasks/<id>/chat/decision`（body：`run_id`、`confirm_id`、`allow` 布尔）回执：`allow=true` → 放行并执行，随后流上出现该工具的 `tool_result` 并继续；`allow=false` → 拒绝执行，Agent 收到「用户拒绝」的结果并继续（绝不执行该工具）。`run_id`/`confirm_id` 不存在或已失效 → 404 JSON。确认回执 SHALL 不要求用户重新发起 chat 即可恢复同一运行继续输出。放行/拒绝结果 SHALL 写入审计（见「运行时审计」）。

#### Scenario: 放行后工具执行并继续

- **WHEN** Agent 请求执行 Write 类工具，用户随后对该 `confirm_id` 回执 `allow=true`
- **THEN** 同一运行继续流出该工具 `tool_result` 并推进至 `done`；工具确实执行；审计含该放行决策

#### Scenario: 拒绝后工具不执行、Agent 继续

- **WHEN** Agent 请求执行 Bash 类工具，用户回执 `allow=false`
- **THEN** 该工具绝不执行（无副作用）；Agent 收到拒绝结果并最终正常收尾；审计含该拒绝决策；对失效的 `run_id`/`confirm_id` 回执返回 404

### Requirement: 对话历史持久化与读取

系统 SHALL 将每次运行的输入与最终助手文本持久化为消息记录（角色 user/assistant、文本内容、时间戳、所属任务、可选 `run_id`）：用户消息在收到请求时记录；助手文本以流上 `text`/`text_delta` 拼接的最终内容在 `done` 时记录。因模型错误而未产生最终文本的运行 SHALL 只保留用户消息、不产生伪助手消息。系统 SHALL 提供 `GET /api/tasks/<id>/messages` 按时间升序返回该任务全部消息（含 role/content/created_at），无历史 → 200 空数组；任务不存在 → 404。

#### Scenario: 一次对话后历史可读回

- **WHEN** 用户完成一次成功对话后请求 GET /api/tasks/<id>/messages
- **THEN** 返回 200，含该条用户消息与助手消息，助手内容与 SSE 收到的最终文本一致，顺序按时间

#### Scenario: 空历史与模型失败不产生伪助手消息

- **WHEN** 用户请求无历史的任务 messages，或在模型错误（首事件 error）后请求
- **THEN** 无历史 → 200 空数组；模型错误那次对话只出现用户消息、无助手消息

### Requirement: 运行时审计

系统 SHALL 为每次对话运行记录审计条目：模型调用（model_call，含模型标识与近似用量，不含密钥与完整敏感参数）、工具执行（tool_call，含工具名与执行成败）、以及二次确认决策（confirm_decision，含 confirm_id、工具名与 allow/deny 结果）各写一条 `AuditLog` 记录，字段含所属任务、动作、目标、时间戳与可读结果；确认决策以 `runtime`/`user` 区分触发方。任何记录 SHALL 不含密钥明文或敏感密文值，工具参数过长/敏感时截断或脱敏。任务不存在或参数非法时不产生审计。

#### Scenario: 一次带工具调用的对话产生完整审计

- **WHEN** 用户完成一次含确认与工具执行的对话运行
- **THEN** AuditLog 出现对应的 model_call、confirm_decision（user 触发、含 allow/deny）、tool_call（含成败）记录且均可关联到该任务/run；逐条核查无密钥明文
