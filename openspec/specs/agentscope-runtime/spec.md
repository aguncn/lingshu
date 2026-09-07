# agentscope-runtime Specification

## Purpose
智能体运行时：把任务绑定的模型（ModelProvider+ModelConfig）与已挂载能力（技能 / MCP / 运维专家人设 / RAG）组装为可对话的 Agent，通过 SSE 提供流式对话、危险工具二次确认、历史消息读取与运行时审计——消费 P2~P5 数据，支撑前端会话区接入。

## Requirements

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

系统 SHALL 在组装对话 Agent 时消费任务的挂载能力（P4/P5 数据），并在一次运行中生效：已挂载且可用的技能（TaskSkill，技能启用且带指令文本）SHALL 以**按需取用的只读技能工具**形态挂载——其完整指令文档不再常驻系统提示，而是由 Agent 判断任务相关时调用该技能工具、取回分步指令后按其执行（见「技能与知识库可调用工具挂载」）；已挂载的专家（TaskExpert）其系统人设 SHALL 参与角色塑造（单专家人设；多专家协作编排不在本提案），人设文本 SHALL **优先取该专家挂载时的快照 `task_expert.persona_snapshot`**（C5 起套用运维专家档案时即定格），快照为空（C5 之前的老挂载行、或挂载时已停用而未被定格）时回退取该专家当前 `enabled` 且非空 `system_prompt`，快照与 live 均无/停用则跳过该专家（不阻断、不注入空人设）；已挂载且可用的 MCP 连接器（TaskMcp）SHALL 被实例化为该运行可调用的工具集（消费 P5 的 transport/env 配置，密钥解密且不回显）；已挂载且可用的知识库（TaskKb）SHALL 以只读「知识库检索工具」生效（复用关键词检索，见「技能与知识库可调用工具挂载」）。Agent 调用工具（含技能取用与知识库检索）时流上出现对应 `tool_call`/`tool_result` 事件，并进入该助手回合的过程 trace。停用/未就绪的挂载实体 SHALL 被跳过，不阻断对话。无任何挂载时 SHALL 仍能进行不依赖工具的普通问答。

#### Scenario: 挂载工具可被调用并流出事件

- **WHEN** 某任务挂载了一个可用 MCP 连接器后发起对话，Agent 决定调用其某工具
- **THEN** 流上出现该工具的 `tool_call`（含工具名与参数）与随后的 `tool_result`（含成败与摘要）；密钥值不出现于任何事件

#### Scenario: 技能与专家人设生效、停用实体被跳过

- **WHEN** 某任务挂载了技能与专家（挂载时定格了人设快照）、另挂了一个停用的 MCP，随后发起对话
- **THEN** Agent 的可用工具含该技能的取用工具，停用连接器不出现于可用工具，系统提示含专家人设（为该专家挂载时的快照文本，可观察）而不含技能指令全文；套用档案后再修改/停用该档案，人设仍取快照不变；Agent 调用技能工具后其分步指令出现在工具结果并可据其执行；无挂载的任务仍可完成普通问答

### Requirement: 技能与知识库可调用工具挂载

系统 SHALL 把任务挂载且可用的技能与知识库装配为该运行**可调用的只读工具**，并使这些调用被既有事件与过程 trace 捕获：

- **技能取用工具**：每个「挂载且技能启用且 `skill_md` 非空」的技能 SHALL 对应一个只读工具（内部名 `skill_<slug>`，slug 由技能名归一化而来、冲突/无法归一化时回退 `skill_<id>` 保证唯一），其描述 SHALL 含该技能的人类可读名与用途（缺省给通用说明）；Agent 调用该工具 SHALL 返回该技能完整分步指令文本。工具出现即代表该技能「已装配」；未被调用不得进入摘要的「已调用」集合。
- **知识库检索工具**：任务挂载且可用（`status=ready`）的知识库 SHALL 由一个只读检索工具（`knowledge_search`）覆盖——入参 `query` 必填、可选 `top_k`（有上限），在**该任务已挂载的全部可用知识库**上执行关键词检索（复用既有切块/关键词计分实现，不引入向量库），合并返回 top-k 文本块；每条结果 SHALL 带来源标识（库名/文件名/块序/分值）供模型引用来源。任务未挂载任何可用知识库时 SHALL 仍装配其余能力，该工具被调用时 SHALL 返回明确的「无可用库/无命中」文本而非报错。

两类工具 SHALL 均为只读：在 `strict`/`limited`/`trusted` 任何权限档下都不触发二次确认（`confirm_request`），写/执行类工具的确认档位语义 SHALL 不受影响；两类工具的调用 SHALL 照常写 `tool_call` 审计，并在流上以 `tool_call`/`tool_result` 事件出现、进入该助手回合过程 trace。装配 SHALL 按任务当前挂载/档位即时快照：运行中调整任务挂载不影响正在运行的 run，只作用于之后新发起的 run。工具调用与结果的摘要 SHALL 不含密钥明文、超长按服务端既有截断上限收敛。

#### Scenario: 技能按需取用进事件与 trace

- **WHEN** 任务挂载了启用且带指令文本的技能，Agent 判断任务匹配并调用该技能工具
- **THEN** 该技能完整分步指令作为工具结果返回、模型按其执行；流上出现该技能的 `tool_call`/`tool_result`；该助手回合 trace 含此调用步骤；未被调用的技能只以「已装配」呈现、不进入调用摘要

#### Scenario: 停用或无指令技能不出现为工具

- **WHEN** 某挂载技能被停用，或 `skill_md` 为空
- **THEN** 该技能不出现为可用工具/技能清单，不阻断对话发起

#### Scenario: 检索工具跨挂载库合并返回带来源结果

- **WHEN** 任务挂载两个可用知识库（各含相关切块），Agent 调用 `knowledge_search`
- **THEN** 合并返回 top-k 文本块，每条带来源（库名/文件名/块序/分值）；未命中或库无内容时返回明确的空结果文本而非报错；结果不含密钥等敏感值

#### Scenario: 只读工具在任何权限档都不触发二次确认

- **WHEN** `strict`/`limited`/`trusted` 下模型调用技能取用或知识库检索工具
- **THEN** 均不出现 `confirm_request`、工具直接返回结果；同一次运行里写/执行类工具（Bash/Write/Edit/PowerShell）的确认行为不受影响

#### Scenario: 改挂载对后续 run 生效

- **WHEN** 运行中调整任务挂载（新增/移除技能或知识库）后再发起新对话
- **THEN** 正在运行的 run 按原装配快照不受影响；新 run 的可用技能工具与检索语料反映新的挂载

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

### Requirement: 助手回合过程 trace 记录与随消息返回

系统 SHALL 将一次成功运行的助手消息，连同其所属回合的有序过程 trace 一并持久化，并经 `GET /api/tasks/<id>/messages` 随该助手消息返回。一次「助手回合」= 自收到一条用户消息后模型开始回复，至该条助手最终文本完成（一次 run 结束）之间的过程。

过程 trace SHALL 为有序步骤列表，步骤类型至少覆盖：模型思考片段（thinking）、工具调用（tool_call：工具名 + 入参摘要）、工具结果（tool_result：工具名 + 成败 + 结果摘要）、二次确认决策（confirm：工具名 + 用户放行/拒绝）。工具入参与结果 SHALL 为摘要级——不含任何密钥明文或敏感密文值；超长内容按服务端既有的单事件摘要截断上限收敛。无任何工具/思考/确认的纯文本回复，其 trace SHALL 为空或省略。

trace 只在运行成功且产生助手最终文本时记录：模型错误/中断且无最终文本的运行 SHALL 只保留用户消息，不产生助手消息及其 trace。`GET /messages` 响应中的 trace 为助手消息的**可选新增字段**：无 trace 记录的旧消息不返回该字段；除该字段外响应与既有契约保持一致（向后兼容，旧客户端不受影响）。

#### Scenario: 含工具调用的对话返回可回看的 trace

- **WHEN** 用户完成一次成功的、期间调用了命令/MCP 工具（可含二次确认）并产出最终文本的对话，随后 GET /api/tasks/<id>/messages
- **THEN** 该助手消息携带与流上事件先后一致的 trace，可依次还原 thinking、tool_call（名 + 入参摘要）、tool_result（名/成败/结果摘要）与确认决策；内容不含密钥明文

#### Scenario: 纯文本回复 trace 为空、失败运行不产生伪 trace

- **WHEN** 用户完成一次无工具/思考的纯问答成功对话；另有一次模型错误（流首事件 error）的运行
- **THEN** 纯问答那条助手消息 trace 为空或省略该字段；模型错误运行只出现用户消息、无助手消息与 trace；无历史任务仍返回 200 空数组

#### Scenario: 旧消息与旧客户端向后兼容

- **WHEN** 读取一条 trace 记录存在之前即已存在的助手消息，或旧版前端消费 GET /messages
- **THEN** 该消息不含 trace 字段仍可正常渲染为纯文本气泡；新增可选字段不破坏既有字段解析

### Requirement: 会话运行保活、显式停止与孤儿回收

系统 SHALL 把 SSE 连接断开视为对本次「消费」的**脱离**而非对运行的取消：连接被关闭或生成器异常 SHALL 只结束该连接的帧读取，worker 线程 SHALL 继续把当前 run 跑完，并在收尾处先推送 `done`/`error` 终端事件、随后自注销该任务的活动槽位（此后该任务即可再次发起 chat）。系统 SHALL 仅当某个 SSE 消费端「读到终端事件自然结束」时幂等释放该任务槽位：保证结束后立即可再发起，且绝不误释放仍在后台运行的 run。流空闲超过心跳间隔（10s）无事件帧时，系统 SHALL 发送 SSE 注释帧 `: ping` 以维持长连接不被代理/浏览器按空闲掐断；消费端 SHALL 忽略非 `data:` 行（心跳帧不视作事件）。

系统 SHALL 提供 `GET /api/tasks/<id>/chat/status` 供运行态查询：无活动会话 → 200 `{"active":false}`；存在活动会话 → 200 含 `active:true`、`run_id`、`waiting`（是否正等待用户回执）；`waiting=true` 时 SHALL 附 `confirm`（含 `confirm_id`/`name`/`action`/`reason`，摘要级、不含密钥），供前端重显确认卡；任务不存在 → 404。查询 SHALL 刷新该会话的活跃打点，作为「有人正在看」的判据。用户 SHALL 可就返回的 `confirm` 直接经既有 `POST /api/tasks/<id>/chat/decision` 回执，恢复同一 run 继续输出，无需重新发起 chat。

系统 SHALL 提供 `POST /api/tasks/<id>/chat/stop` 显式停止：取消当前 run（标记取消 + 收敛 worker + 释放槽位）并返回 200 `{"ok":true}`；无活动会话时 SHALL 幂等返回 `{"ok":true}`；任务不存在 → 404。「停止」是唯一真正的取消路径，与 SSE 脱离相区别。

系统 SHALL 以进程内单例守护定期扫描会话注册表：凡「正停驻等待用户回执（park）」且其消费端活跃打点超过闲置宽限（600s）未刷新的孤儿会话，SHALL 被自动取消并释放槽位，避免其永久占用活动槽导致该任务此后发起 chat 永久 409。

#### Scenario: 断连后 run 继续跑完并可再次发起

- **WHEN** 用户发起对话后关闭标签/切走导致 SSE 断连，worker 仍在后台把 run 跑完
- **THEN** run 不被取消：正常完成时落助手消息并自注销槽位；用户返回/重开后经 `/chat/status` 可见 active（run 结束前）或经消息历史读到最终回复，并可立即再次发起 chat

#### Scenario: 待确认 run 断连可经 status+decision 恢复

- **WHEN** 后台 run 停在待用户回执确认、用户刷新页面后请求 `/chat/status`
- **THEN** 返回 `active:true`、`waiting:true` 并附该确认的 `confirm` 摘要；用户对该 `confirm_id` 回执 allow/deny 后同一 run 继续（放行则该工具执行），无需重新发起 chat；批内其余待确认按序浮现

#### Scenario: 显式停止真取消且幂等

- **WHEN** 用户对运行中任务请求 `/chat/stop`；随后对已无活动会话的任务再次请求
- **THEN** 第一次真正取消该 run、槽位释放、返回 `{"ok":true}`，任务可再次发起；第二次幂等返回 `{"ok":true}`

#### Scenario: 待确认/长思考空闲期心跳保活

- **WHEN** 运行停驻（等待用户回执或模型长思考）期间超过 10s 无事件帧
- **THEN** 流上出现 SSE 注释帧 `": ping"`；消费端忽略该帧、连接不被空闲掐断，待确认连接保持可写

#### Scenario: 孤儿 park 会话超时自动回收

- **WHEN** 某 run 停在待回执确认，且其消费端超过 600s 无任何打点（无人查看/回执）
- **THEN** reaper 自动取消该 run、槽位释放；此后该任务再次发起 chat 不再因残留活动槽而 409

### Requirement: 内置工具调用权限档位映射

系统 SHALL 在组装对话 Agent 时按任务的 `permission_mode` 把内置工具调用的二次确认档位映射进 AgentScope 权限上下文：`strict` → 默认模式——内置写/执行类工具（Bash/Read/Write/Edit/Glob/Grep/PowerShell）被请求即产 `confirm_request`，用户放行才执行（与旧行为逐字一致）；`trusted` → 完全信任——全程不请求人工确认、工具直接执行；`limited` → 有限——只读与一般命令自动放行，仅「修改/新建本地文件的 Write/Edit」及「命令中出现删除/覆盖类操作」请求一次确认。未知/缺失取值 SHALL 兜底最严的 `strict`。

`limited`/`trusted` 的映射 SHALL 采用「`BYPASS` 默认全放 + 少量 ask 规则命中才确认」的负向枚举（无法正向穷举安全命令），并因此以「信任模型行为」为前提：`BYPASS` SHALL 跳过工具自带的 bypass-immune 引擎级安全确认（如 `rm -rf /` 之类保护），相关兜底由系统提示约束承担。删除/覆盖类判定对 Bash SHALL 用命令子串规则（`rm`/`rmdir`/`unlink`/`shred`/`mv`/`cp`/`sed -i` 等）；对 PowerShell SHALL 以命令内容做**大小写不敏感**的子串匹配（覆盖 `remove-item`/`del`/`erase`/`move-item`/`copy-item`/`set-content`/`out-file` 等；等价别名与内联改写属启发式边界——命中则多确认一次（安全向）、漏判则少确认一次，不作精确分类承诺）。工具自身 `DENY` 规则与用户 ask/deny 规则 SHALL 仍保留生效。

权限模式 SHALL 在每次会话发起时按任务当前值即时取用（装配即快照）：运行中改动任务 `permission_mode` 不影响正在运行的 run，只作用于之后新发起的 run。

#### Scenario: strict 与旧行为逐字一致

- **WHEN** 任务 `permission_mode` 为 `strict`（或缺省）发起含写/执行类工具的对话
- **THEN** 与默认模式一致：写/执行类工具被请求即出现 `confirm_request`，放行后执行并流出 `tool_result`、拒绝则不执行；审计均记录

#### Scenario: trusted 全程免人工确认

- **WHEN** 任务 `permission_mode` 为 `trusted` 发起含写/执行类工具的对话
- **THEN** 工具调用不出现 `confirm_request`、直接执行并流出 `tool_result`；审计记录工具执行

#### Scenario: limited 仅对危险子集确认

- **WHEN** 任务 `permission_mode` 为 `limited` 发起对话，模型依次执行只读命令（如 Grep）、`Bash "rm -rf /tmp/x"` 删除命令与一次 Write 写文件
- **THEN** 只读与一般命令自动放行无确认；`rm`（命中删除子串）与 Write 各出现一次 `confirm_request`，放行后才执行；PowerShell `Remove-Item` 同样命中（大小写不敏感）

#### Scenario: 运行中改档只影响后续 run

- **WHEN** 用户在任务运行中 `PATCH` 其 `permission_mode`（如 `strict`→`trusted`），随后再发一条新消息
- **THEN** 正在运行的 run 按原档不受影响；新发起的 run 按新档装配（装配描述中 `permission_mode` 反映新值，无确认请求）

### Requirement: 任务工作空间沙箱与生成文件收敛

系统 SHALL 在组装一次对话运行时，为该任务建/沿用其**工作空间沙箱目录**（`data/spaces/<space_id>/<task_id>/` 的绝对路径，以应用配置的数据根为准），使智能体本次运行生成的产物落在任务目录而非进程/仓库根。具体：

- **目录生命周期**：`build()` 于装配前 SHALL 幂等创建该任务目录（不存在则建、已存在则沿用同一绝对路径）——同一任务多轮问答共享同一目录，可续读/改写上一轮产物；目录随任务删除级联清理（既有删除语义）。任务目录创建失败属真实 IO 错误，SHALL 使本次会话以可读错误结束（`error` 事件收尾、不产生消息副作用），**不得**静默回落到进程 cwd 继续运行。
- **工具进程 cwd 收敛（软沙箱）**：内置命令/执行工具 `Bash` 与 `PowerShell` SHALL 以该任务目录为工作目录构造（`cwd=<workdir>`），命令进程在其中执行、相对路径即相对任务目录；Windows/非 Windows 行为一致。`Read`/`Write`/`Edit` 仍要求绝对路径、不随 cwd 改变，故沙箱为软约束——越过任务目录的写/执行仍由既有权限档位的二次确认闸门兜底（`strict`/`limited`/`trusted` 语义不变），不做额外硬拦截。
- **提示声明工作目录**：该运行的系统提示 SHALL 声明 `工作目录：<绝对路径>`，并给出指引——本任务生成或修改的文件应放入该工作目录，`Read/Write/Edit` 使用其中的绝对路径、`Bash/PowerShell` 已在该目录下执行、相对路径即相对工作目录；使模型自主把产物收敛到任务目录。
- **产物可被回看**：沙箱生效后，一次运行落到任务目录的文件 SHALL 经既有 `GET /api/tasks/<id>/files`（扫描任务目录）被前端文件抽屉列出示人。运行装配描述 SHALL 携带该次 `workdir` 供审计/调试核对，不含密钥。

#### Scenario: 工具进程在任务目录下执行

- **WHEN** 装配某任务的对话运行时，任务目录已建（或首次被建）
- **THEN** 内置 `Bash`/`PowerShell` 工具的 cwd 为该任务目录的绝对路径；Agent 用相对路径执行命令/写相对文件时落在该目录内，而非进程/仓库根

#### Scenario: 同任务多轮共享目录可续改产物

- **WHEN** 任务第一轮生成文件后，同任务再次发起对话并引用上一轮产物
- **THEN** 目录沿用同一路径、上一轮文件仍在其中可见（`GET /files` 可列出），模型可读改续作；不同任务的目录互不相通

#### Scenario: 目录不可建时以错误结束、不散落根目录

- **WHEN** 任务工作目录无法创建（真实 IO 失败，如数据根不可写/路径非法）
- **THEN** 本次会话不建立、以可读 `error` 事件结束、不产生对话消息副作用；不静默回落到进程 cwd 把产物写到仓库根

#### Scenario: 系统提示声明工作目录并指引收敛

- **WHEN** 检查某次运行的装配系统提示
- **THEN** 提示含「当前任务」段，其中列出 `工作目录：<该任务绝对路径>`，并说明写入指引（Read/Write/Edit 用其中绝对路径、Bash/PowerShell 已在该目录下执行）；装配描述含该次 `workdir`、不含密钥

#### Scenario: 越界写仍走权限闸门

- **WHEN** 模型尝试用 `Write`/`Bash` 写到任务目录之外（绝对路径越界）
- **THEN** 沙箱不额外放行也不额外拦截：按任务权限档位走既有二次确认语义——`strict` 全量确认、`limited` 对 Write/Edit 与删除/覆盖类命令确认、`trusted` 放行，审计照常记录，行为与改动前一致
