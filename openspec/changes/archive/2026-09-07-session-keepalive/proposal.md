## Why

P8 会话能力已交付（见归档 2026-09-06-agentscope-runtime、workbench-live-session），但运行生命周期存在三个使用缺陷：

1. **切走即中断**：原前端「选中任务切换即 abortChat 断开 SSE」，正在后台跑的 run 被白白取消——切走再回来时进行中的任务丢进度、丢待确认，必须重新发送整条消息。
2. **断连语义未定型**：后端把「SSE 连接关闭」等同「取消」会杀掉仍可完成的 run；反过来若断连后 run 停在一个无人认领的确认上，活动槽被永久占用，该任务此后每次再发起 chat 都会 409（即最初遇到的卡死）。
3. **确认不可恢复**：二次确认卡只在本地 SSE 流上出现；页面刷新、或另一窗口/标签页打开同一任务后，既看不到「有 run 在等回执」，也无法继续回执——只能中断该 run 重发。

本变更实现「**运行保活 + 确认可恢复**」：切走不杀 run、返回即见实时进度与确认；显式「停止」才是唯一真正的取消；断连的 run 后台跑完自释放槽位；无人认领的待确认 run 由守护按超时自动回收，杜绝永久 409。浏览器手工验收通过，现将行为回填进规范并归档。

## What Changes

- **agentscope-runtime（运行生命周期契约）**：
  - SSE 断开由「取消」改为「脱离」：连接关闭只结束本次帧读取，worker 线程继续把 run 跑完，并在收尾（push `done`/`error` 之后）自注销注册槽位；
  - 读端仅在「读到终端帧自然结束」时幂等释放槽位，保证结束后立即可再发起 chat，且不误释放仍在后台跑的 run；
  - 流空闲超时发 SSE 注释帧 `: ping` 心跳，避免长连接被代理/浏览器按空闲掐断；
  - 新增 `GET /api/tasks/<id>/chat/status`（active / run_id / waiting / confirm 摘要）与 `POST /api/tasks/<id>/chat/stop`（幂等显式停止）；
  - 新增孤儿回收守护：停驻待确认且消费端超过闲置宽限（600s）无打点的会话被自动取消、槽位释放。
- **workbench-ui（会话运行态与确认恢复）**：前端会话跟踪改为「每任务独立 run 注册」——切换任务不再中止进行中 SSE，返回即恢复直播与确认卡；页面刷新/异地窗口打开经 `/chat/status` 采纳远端 run 并以轮询推进、结束时以权威历史对齐；「停止」只作用于当前选中任务并真取消；确认卡独立于历史是否载入而可见可回执。
- 无数据迁移、无新增外部依赖。

## Capabilities

### New Capabilities
<!-- 无新增能力。 -->

### Modified Capabilities
- `agentscope-runtime`: 会话生命周期契约补「断开=脱离 / 心跳 / status / stop / 孤儿回收」。
- `workbench-ui`: 会话区运行态补「每任务 run 注册、跨任务保活、确认可恢复、显式停止」。

## Impact

- 后端：`services/agent_session.py`（心跳、断开不取消、worker 自注销、status/stop、reaper）、`api/runtime.py`（chat/status、chat/stop 端点、generate finally 幂等释放）。
- 前端：`api/chat.js`（status/stop 封装、跳过心跳帧）、`stores/task.js`（每任务 run 注册、adoptRun、轮询、stopChat、确认卡恢复）。
- 测试：`backend/tests/` 补生命周期用例；前端 `npm run build` 通过。
- 后端/数据：无改动、无迁移。
