## ADDED Requirements

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
