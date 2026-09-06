## Why

P1~P7 已交付的只是「数据 + 界面 + 管理面」：任务/模型/挂载能力齐备，但没有运行时把它们变成真正会思考、会调用工具的智能体对话。本提案补齐 AgentScope 运行时底座（参照设计 §7.1~7.7）：把任务的模型绑定 + 挂载能力（技能/MCP/专家）组装成 `Agent`，把 `reply_stream()` 事件流桥接成 Flask SSE，用 Permission（危险操作二次确认）与审计兜底安全——让平台第一次「能跑起来对话」。知识库挂载的检索注入与多专家编排分属 P9/P1，不在本提案。

## What Changes

- **运行时服务层**（新 `backend/services/`）：`model_factory.py`（ModelProvider+ModelConfig → OpenAI 兼容模型，Fernet 解密 + 环境变量覆盖）、`agent_runtime.py`（`AgentRuntime.build()` 读取任务/模型/挂载组装 `Agent`+`Toolkit`，以及线程+队列的 SSE 事件流驱动）、`mcp_client.py`（按任务挂载的 MCPConnector 实例化 StdIO/HTTP 客户端并注册）、`audit.py`（模型调用/工具调用/确认决策 → `AuditLog`）、`message.py`（对话落库/读取）。
- **新端点**：`POST /api/tasks/<id>/chat`（SSE 流式对话）、`POST /api/tasks/<id>/chat/decision`（危险工具二次确认的放行/拒绝回执）、`GET /api/tasks/<id>/messages`（历史消息）。
- **数据模型**：新增 `Message`（每任务对话历史）与 `AuditLog`（运行时审计）；迁移 `migrations/0006_agent_runtime.sql`。
- **安全**：内置命令执行/写类工具（Bash/Write/Edit）默认 `confirm` 二次确认，未放行不执行；确认与工具/模型调用写 `AuditLog`。密钥沿用 Fernet（`LINGSHU_MASTER_KEY`/`.env`），不明文出入运行时。
- **消费 P2~P5**：任务（Task）、模型（ModelProvider/ModelConfig）、挂载（TaskSkill/TaskMcp/TaskExpert → 技能指令段、MCP 客户端、专家人设注入）。

## Capabilities

### New Capabilities

- `agentscope-runtime`: 智能体运行时——把任务绑定的模型与挂载能力组装为 Agent，提供 SSE 流式对话、危险工具二次确认、对话历史与运行时审计的 REST 契约。

### Modified Capabilities

（无。`workbench-ui` 会话区占位逻辑仍成立：本提案纯后端，UI 消费 SSE 的接线属后续前端 change。）

## Impact

- 后端新模块：`services/model_factory.py`、`services/agent_runtime.py`、`services/mcp_client.py`、`services/audit.py`、`services/message.py`、`api/runtime.py`（blueprint `/api`）；`models.py` 增 `Message`/`AuditLog`；`migrate.py` 升 schema_version 至 6。
- 依赖：`agentscope>=2.0.7.post1`（已在 pyproject）。运行时按 AgentScope **2.0.7.post1 实际 API** 实现（`Agent(name,system_prompt,model,toolkit,middlewares,…)` + `OpenAICredential(api_key,base_url)` + `reply_stream()` 的 **park/continue 确认协议**——与设计 §7.6 旧骨架示意有出入，见 design.md D2/D4）。
- 测试：新增 `backend/tests/test_runtime.py`（模型/Agent 打桩离线）；既有 pytest 全绿。
- 不改动：知识库检索注入（P9）、多专家编排（P1）、前端会话接线（后续）、P10 全量写操作审计（本提案只记运行时事件）。
