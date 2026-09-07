## 1. 后端：trace 数据模型与消息读写

- [x] 1.1 新增 `backend/migrations/0008_message_trace.sql`（`ALTER TABLE messages ADD COLUMN trace TEXT;`），并在 `models.py` 的 `Message` 增 `trace = db.Column(db.JSON)`、`to_dict()` 仅当非 None 才输出 `"trace"` 键。验收：启动/测试触发 `run_migrations()` 后 messages 表含 trace 列；旧行与 None 行 `to_dict()` 不含该键。
- [x] 1.2 `services/message.py`：`add_message/add_user_message/add_assistant_message` 增可选 `trace` 参数并落库，`list_messages` 经 `to_dict()` 自动带出。验收：新增单测——含 trace 的助手消息 round-trip 后结构与入参一致、无 trace 时响应省略该字段、旧契约字段不变。

## 2. 后端：回合内过程捕获与落库

- [x] 2.1 `ChatSession` 增有序步骤缓冲：`_map_event` 在 `ToolCallEndEvent`/`ToolResultEndEvent` 时按事件完成序 append `tool_call`（名+入参，沿用 `_DETAIL_LIMIT`）与 `tool_result`（名+成败+摘要，沿用 `_RESULT_LIMIT`）步骤；`thinking_delta` 归并为连续 thinking 块、遇下一非思考事件或 run 结束闭合。SSE 事件推送与现有审计路径保持逐字不变。验收：单测用假事件序列断言 `_steps` 顺序与内容、thinking 归并正确、纯文本回合 steps 为空。
- [x] 2.2 二次确认写回：`_await_decisions` 收到用户 allow/deny 时追加独立 `confirm` 步骤（`{kind:"confirm", name, decision}`），先闭合悬挂 thinking。因 AgentScope 无论放行与否都会回一个结果帧（放行 ok=true 真实执行；拒绝 ok=false「用户拒绝」、无任何写副作用），tool_result 步骤照常 append——trace 顺序恒为 `tool_call → confirm → tool_result`，与 SSE 一致。验收：单测断言 allow 路径 confirm 步骤带 `decision:"allow"`、其前后分别为 tool_call 与 ok=true 的 tool_result；deny 路径 confirm 带 `decision:"deny"`、目标文件未被创建、tool_result ok=false（拒绝路径无写副作用而非无 result 步骤）。
- [x] 2.3 done 落 trace：`_drive` 成功分支改调 `add_assistant_message(..., trace=<steps or None>)`；模型错误/中断且无最终文本的运行仍只留用户消息。`api/runtime.py` 不改动。验收：含工具成功运行经 `GET /messages` 助手消息带与 SSE 顺序一致的 trace；纯文本回合 trace 为 None（响应省略）；error run 无助手消息与 trace。

## 3. 前端：会话状态累积与摘要派生

- [x] 3.1 `stores/task.js`：`_onChatEvent` 新增 `thinking_delta` 累积、`tool_call/tool_result` append 到 live 助手气泡的 `steps`；live 气泡扩展 `steps`/`thinkingLive` 字段；`decideConfirm` 放行/拒绝把 decision 写回该气泡对应 tool_call 步骤。既有 text_delta/confirm/error/中断路径行为不变。验收：mock onEvent 事件序列断言 live 气泡 steps 顺序与 SSE 一致、放行后 decision=allow。
- [x] 3.2 `ensureHistory` 把服务端返回的 `trace` 映射进历史气泡；无 trace 的旧消息正常渲染为纯文本且不渲染摘要行。验收：构造含/不含 trace 的 `/messages` 响应断言上屏结果与不报错。
- [x] 3.3 新增前端摘要派生工具（集中分类 + 兜底）：将 steps 按类型桶聚合生成一行摘要文本——命令（Bash/PowerShell）、文件（Read/Write/Edit/Glob/Grep）、MCP（工具名前缀匹配挂载连接器名）、未知一律落「工具」，并输出「已装配（技能/资料库/MCP 计数）」弱标记数据。验收：单测/断言给定 steps 的摘要文本与分类，未知工具落「工具」桶。

## 4. 前端：会话展示组件与样式

- [x] 4.1 新增 `components/layout/AssistantTrace.vue`：渲染独立一行的调用摘要、「查看过程」就地展开/收起的有序步骤明细（thinking / tool_call 入参 / tool_result 成败 / decision）、流式动态 "…" 进行态、「已装配」弱标记（与已调用分开展示）。验收：展开收起、弱标记、进行态均按设计呈现、展开态不跨任务残留。
- [x] 4.2 `ChatPane.vue` 集成：assistant 气泡顶部为独立成行的摘要行、正文在下、不同回复以摘要行为界不粘连；live 气泡流式期间正文未产出首段文本时显示动态 "…"、摘要随工具实时累积；错误气泡路径保持不变。验收：手工过 spec 场景 1–4（摘要独立行/展开过程/流式进行态与实时摘要/刷新回看一致）。
- [x] 4.3 字号令牌：`styles/index.css` 设计令牌增 `--ls-font-size-msg`（默认 13px，收敛原 13.5px 写死值），`.cp-bubble` 的 `font-size` 改引用该变量，`line-height` 不变。验收：明/暗两态下正文为令牌档位、较改动前更小且对比可读。

## 5. 验收与回归

- [x] 5.1 全量回归 + 手工清单：`uv run pytest backend/tests/ -q` 全绿（含新增 message trace 用例与既有 agentscope-runtime/message 用例不回归）；前后端起服务联跑，逐项过 spec 五个场景（含失败运行不产生伪 trace、旧消息/旧客户端向后兼容）。
