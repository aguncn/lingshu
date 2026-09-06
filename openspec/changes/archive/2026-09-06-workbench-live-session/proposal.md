## Why

P8（capability `agentscope-runtime`）已交付智能体真会话后端：`POST /api/tasks/<id>/chat` 的 SSE 事件流、`POST /api/tasks/<id>/chat/decision` 二次确认回执、`GET /api/tasks/<id>/messages` 历史读取，并经真实 DeepSeek 调用验证（thinking/text 增量 → done）。但 `workbench-ui` 主规范中「会话输入框与占位会话」与「会话区…P8 接入前展示为空态占位」仍停留在 P8 前"本地占位消息"描述，浏览器里实际已是流式真会话——规范落后于已交付代码，需回填对齐，否则验收口径与实现脱节。

## What Changes

- **会话区**：从"P8 接入前空态占位"改为——选中任务后经 `GET /api/tasks/<id>/messages` 读取服务端权威历史并升序渲染为用户/助手气泡（含时间与所用模型标识）；无历史时显示稳定空态。
- **会话输入**：从"本地占位消息 + '智能体会话将在后续接入'提示"改为——发送经 `POST /api/tasks/<id>/chat`（`text/event-stream`）发起真会话：用户消息与助手占位气泡立即上屏，助手文本随流式事件打字机式追加，会话结束以服务端权威历史对齐。
- **会话过程控制**：流式/等待确认期间禁发并展示"停止"（断开 SSE、后端取消当前 run）；助手触发危险写/执行类工具时渲染"放行/拒绝"确认卡片并回执 `POST /api/tasks/<id>/chat/decision`；模型不可用/运行异常时助手气泡转为可见错误态且失败时保留输入框原文供重发。
- **规范清理**：移除 `workbench-ui` 中两处 "P8 接入前 / 待接入" 的过时语义表述。文件树、时间线（R3 占位）、顶部模板条等其余需求行为不变，不属本变更。
- 不涉及任何后端/接口改动，纯前端行为 + 规范对齐；消费 P8 已交付端点。

## Capabilities

### New Capabilities
<!-- 无新增能力。 -->

### Modified Capabilities
- `workbench-ui`: 把「会话区与任务文件树」中"P8 接入前空态占位"改为读取 `GET /messages` 权威历史并渲染气泡；把「会话输入框与占位会话」整条占位语义替换为「会话输入与智能体实时会话」（SSE 流式/二次确认/停止/失败保留输入）。会话能力前端需求原即属 `workbench-ui`，主规范据此回填为 P8 真会话语义。

## Impact

- 前端：`frontend/src/api/chat.js`（新增 fetch+ReadableStream 的 SSE 桥与 decision/messages 封装）、`frontend/src/stores/task.js`（真会话 state/actions）、`components/layout/ChatPane.vue`（气泡流式渲染 + 确认卡片）、`components/layout/PromptInput.vue`（禁发/停止/失败保留输入）。
- 依赖：复用 `agentscope-runtime`（P8）已交付端点与 `agent_session` 会话注册表语义；前端 `npm run build` 应通过。
- 后端/数据：无改动，无迁移。
