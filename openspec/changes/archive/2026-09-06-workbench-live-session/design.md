## Context

P8（`agentscope-runtime`）后端已交付：`POST /api/tasks/<id>/chat` 返回单行 JSON SSE 帧（`text_delta` / `thinking_delta` / `tool_call` / `tool_result` / `confirm_request` / `error` / `done`），`POST /api/tasks/<id>/chat/decision` 提交危险工具回执，`GET /api/tasks/<id>/messages` 升序返回权威历史；后端为 Flask 同步进程，用 worker 线程 + 队列桥接 AgentScope 异步事件流，同任务同时只有一条活动会话。前端会话需求原归 `workbench-ui`，本变更把它从 P8 前占位语义回填为真会话（动机见 proposal.md）。

## Goals / Non-Goals

**Goals:**
- 浏览器呈现真实会话：发送→SSE 打字机→结束→服务端历史对齐。
- 全站同一时刻只跑一条前台对话流；切任务即干净中断旧流，不留悬挂 run。
- 危险工具二次确认在会话流内联完成，放行后同连接续流。
- 会话视图与输入框交互在任务切换时无串扰、无残留。

**Non-Goals（沿用 P8 语义，另期排）:**
- `thinking_delta`、`tool_call`/`tool_result` 不在会话区单独渲染（本期只呈现最终产物文本）。
- 时间线（`ElTimeline`）仍为 R3 占位，不消费会话/审计事件。
- 多任务并行多路会话 / 会话并发控制由后端注册表保证，前端不强做并发队列。

## Decisions

- **D1 用 fetch + ReadableStream 消费 SSE，而非 axios/EventSource。** axios 不支持流式读取；EventSource 只支持 GET 且难带鉴权与请求体。fetch 逐段 `read()` 拼缓冲、按 `\n\n` 切帧、跳过脏帧——流式与错误语义（AbortError=主动取消）都由它承载。备选 SSE 库徒增依赖，单人项目不引入。
- **D2 会话状态收进 Pinia `task` store，按 `taskId` 隔离消息**，与"右栏一次只呈现一个任务"的外壳一致：`activeMessages` 取当前任务气泡，`selectTask` 先 `abortChat()` 再载历史/文件树/caps/模型。备选局部组件状态会在切任务时丢失或串扰，store 便于"成功一轮后统一以服务端历史对齐"。
- **D3 乐观上屏 + 权威历史兜底，用消息版本号防迟到覆盖。** 发送即推 user+assistant(live) 两气泡，结束/取消后 `ensureHistory(force)` 以服务端历史整体替换乐观气泡（含真实时间/模型）。`_msgVer` 计数快照比对：拉历史期间若新一轮已上屏则放弃本次覆盖，避免清掉刚发的消息。
- **D4 单帧契约与流式渲染。** 每帧 `data: {json}` 单行（帧内控制字符已转义），前端按空行切帧后 `JSON.parse`，失败帧直接跳过不中断整流。`text_delta` 追加进"直播中"助手气泡；`confirm_request` 置 `confirm` 态、末尾渲染卡片。
- **D5 二次确认回执走独立短请求，流保持挂起。** 卡片按钮 `POST /chat/decision`（带 `run_id`/`confirm_id`/`allow`），后端唤醒 worker 续跑，前端继续在同一 SSE 连接收后续帧；`confirm` 先清空防双击（重复回执后端 404，兜底为 ElMessage 提示）。拒绝仅回执，不做前端回滚。
- **D6 busy 禁发 + 「停止」。** `busy = streaming || confirm`：发送/回车禁用，输入区给"停止"→ `AbortController.abort()` 断开连接，后端感知断开 cancel run；`busy` 提示当前等待的是哪把工具。
- **D7 失败语义分级。** `AbortError`＝主动取消，静默并按权威历史收尾；HTTP 非 200 或流内 `error` 事件＝真失败，助手占位气泡转红色错误文案、输入框保留原文可重发（`sendMessage` 返回 `!sawError` 供 PromptInput 决定是否清空）。
- **D8 组件只做展示与触发。** `ChatPane.vue` 消费 store 气泡渲染（含 `is-error` 态、"正在思考"闪烁光标、消息元信息行），`PromptInput.vue` 只取文本调 `task.sendMessage`/`task.abortChat`；新建 `api/chat.js` 桥只做网络层，业务逻辑全在 store action，沿用视图/组件/api/store 分层约定。

## Risks / Trade-offs

- [迟到权威历史覆盖新一轮乐观气泡] → 版本号 `_msgVer` 快照比对，不一致即放弃本次覆盖（D3）。
- [双击/超时导致回执 404] → 卡片先收起防重，404 降级为提示并让收尾逻辑对齐历史（D5）。
- [取消依赖 fetch 取消语义，个别环境连接未必即时断开] → 以服务端权威历史兜底对齐，不留假气泡。
- [同任务并发第二条会话（后端 409 拒绝）] → 前端 busy 禁发已防大部分；万一到达，非 200 错误气泡展示后端 message，输入保留。
- [流式期间页面长连接占用] → 仅存在于用户主动发起会话期间；切任务/停止即 abort 释放。

## Migration Plan

纯前端行为替换，无数据迁移：前端重编译（`npm run build`）即可随下一版发布；后端仍是 P8 已验收端点，无回滚面。旧占位行为被新会话完全取代，无灰度兼容需要。

## Open Questions

无。会话后端行为由已验收的 `agentscope-runtime` 主规范约束，前端此变更仅消费其既有端点契约，无悬而未决项。
