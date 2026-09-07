## 1. 会话生命周期改造：断开=脱离（services/agent_session.py）

- [x] 1.1 断开不再取消：`events()` 仅以「读到终端帧 / 显式取消 / 脱离」结束；worker `_worker` 的 finally 在 push `done`/`error` 之后自注销 `unregister(task_id)`，覆盖「run 已结束但消费端早已脱离、没读到 done」的泄漏面
- [x] 1.2 空闲心跳：`events()` 读循环超过 `_HEARTBEAT_SECONDS`(10s) 无帧时发 SSE 注释帧 `": ping"`；每轮刷新 `_last_consumer_seen` 作活跃打点
- [x] 1.3 孤儿回收：`touch()`/`is_parked()`/`current_confirm()`/`done_consumed` + 单例守护线程 `_ensure_reaper`/`_reap_once`，按 `_CONSUMER_TTL`(600s) 自动 cancel「停驻待回执且无打点」的孤儿会话
- [x] 1.4 SSE 读端幂等释放：`generate()` finally 仅当 `sess.done_consumed` 才 `unregister(task_id)`（worker 已先注销则为空操作）

## 2. 运行查询与显式停止端点（api/runtime.py）

- [x] 2.1 `GET /api/tasks/<id>/chat/status`：无活动会话 → `{active:false}`；有 → `{active:true, run_id, waiting}`，`waiting` 时附 `confirm` 摘要（confirm_id/name/action/reason，截断不含密钥）；任务不存在 → 404；每次查询 `touch()` 刷新回收判据
- [x] 2.2 `POST /api/tasks/<id>/chat/stop`：真取消当前 run（`cancel()` + `dispose()` join + `unregister()` 兜底），返回 `{ok:true}`；无活动会话幂等 ok；任务不存在 → 404

## 3. 前端运行态重构：每任务 run 注册与保活（api/chat.js / stores/task.js）

- [x] 3.1 `chat.js` 增 `getChatStatus`/`stopChat` 封装；`streamChat` 解析跳帧（忽略 `: ping` 心跳帧等非 `data:` 行）
- [x] 3.2 `task store` 重构：模块级 `sseControllers`(taskId→AbortController) + state `runs`(taskId→{confirm})；`streaming/confirm/polling/busy` 全部改为「当前选中任务」的派生 getter；`selectTask` 不再 abort 本地流，`_leaveViewOf` 只清理「非 live（无控制器）」的已采纳任务
- [x] 3.3 `adoptRun`：进入任务时有本地流 → 直接返回；否则 `GET /chat/status`——无活动 run → 复位运行态并载权威历史；有活动 run（刷新/异地启动，帧不可回放）→ 置运行记录与确认卡、`ensureHistory` 载已落库消息、起 2s 轮询推进直至结束 force 对齐
- [x] 3.4 `stopChat` 只作用当前选中任务：abort 本地流 + 清 runs/轮询 + `POST /chat/stop` + force 权威历史；其它任务后台流不受影响；确认卡数据来源兼容「本地流 confirm_request 或 status.confirm」，独立于历史载入

## 4. 测试与收尾

- [x] 4.1 后端补单测：断开不取消/心跳帧出现/done 幂等释放/reaper 超时回收/status 与 stop 端点契约
- [x] 4.2 `cd frontend && npm run build` 通过；浏览器手工验收（切走返回恢复直播与确认、刷新/他窗口恢复确认并回执、停止幂等、孤儿 409 超时回收后可再发起）
