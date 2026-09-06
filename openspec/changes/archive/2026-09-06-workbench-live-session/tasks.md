## 1. 会话 SSE 桥与历史读取（api/chat.js）

- [x] 1.1 新增 `streamChat(taskId, message, {signal, onEvent})`：fetch `POST /api/tasks/<id>/chat` 消费 `text/event-stream`，按 `\n\n` 切出 `data:` 帧并 `JSON.parse` 回调 `onEvent`，脏帧跳过不中断；HTTP 非 200 抛出携带后端 message 的 Error
- [x] 1.2 新增 `sendChatDecision(taskId, data)`：封装 `POST /tasks/<id>/chat/decision`（`{run_id, confirm_id, allow}`），静默请求，失败上抛
- [x] 1.3 新增 `listChatMessages(taskId)`：封装 `GET /tasks/<id>/messages`，返回升序消息（role/content/model/created_at），供历史回放

## 2. 会话状态与流控制（stores/task.js）

- [x] 2.1 消息按任务隔离：`messages/chatLoaded/_msgVer` state 与 `activeMessages` getter；`ensureHistory(taskId,{force})` 从服务端拉权威历史映射为气泡，用 `_msgVer` 版本比对防止迟到覆盖新一轮乐观气泡，失败给空态不置已加载
- [x] 2.2 `sendMessage(text)`：清上次错误气泡→乐观上屏 user+assistant(live)→置 `streaming/chatStreamTaskId`→SSE `onEvent` 分发→`finally` 清态并按 `!sawError` 以权威历史对齐；返回 `!sawError` 供输入框决定保留原文
- [x] 2.3 `_onChatEvent`：`text_delta` 追加进直播中助手气泡（打字机）；`confirm_request` 置 `confirm` 卡片态；`error` 事件/异常把占位助手转为红色错误气泡
- [x] 2.4 `decideConfirm(allow)`：先收起卡片防双击，经 decision 接口回执；拒绝给 ElMessage；404/已消费兜底提示；放行后同一条 SSE 连接继续收后续文本
- [x] 2.5 `abortChat()` 与 `busy` getter：`chatAbort.abort()` 断开当前连接→后端 cancel run，清 `streaming/confirm/chatStreamTaskId` 并对旧任务以权威历史对齐；`busy = streaming || confirm` 供禁发
- [x] 2.6 `selectTask` 先 `abortChat()` 再载入新任务历史/文件树/caps/模型，切换无残留

## 3. 视图接线与占位清理（ChatPane / PromptInput）

- [x] 3.1 ChatPane 会话态渲染 store 气泡：用户右/助手左、助手"正在思考"光标与元信息行（时间·模型·流式中）、`is-error` 红色报错气泡；无消息/未选任务给 EmptyState；流末渲染"放行/拒绝"确认卡片并调用 `decideConfirm`
- [x] 3.2 PromptInput：发送/回车经 `task.sendMessage`，成功清空、失败还原原文；`busy` 禁发并给"停止"→`task.abortChat()` 与 busyHint；展示当前任务与模型绑定弱提示
- [x] 3.3 移除会话区"智能体会话将在 P8 接入 / 待接入"占位横幅与过时文案，切任务/空会话只剩规范空态
- [x] 3.4 `cd frontend && npm run build` 通过（产物可被 5173 开发态正常代理消费）
