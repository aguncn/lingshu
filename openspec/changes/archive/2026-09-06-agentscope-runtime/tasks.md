## 1. 数据模型与迁移

- [x] 1.1 models.py 新增 `Message`（task_id FK→tasks ON DELETE CASCADE、role、content、run_id、model、时间戳）与 `AuditLog`（task_id FK→tasks ON DELETE SET NULL、run_id、actor、action、target、result、detail、created_at），均带 `to_dict()` 出口白名单；中文注释说明 why（Message 存每任务对话历史；AuditLog 列通用以兼容 P10 全量审计）
- [x] 1.2 迁移 `migrations/0006_agent_runtime.sql`（DDL 风格对齐 0004/0005）：建 `messages`/`audit_log` + `idx_messages_task_id`/`idx_audit_log_task_id`；`migrate.py` 应用后真实库 schema_version=6
- [x] 1.3 `services/message.py`（add_user/add_assistant/list_by_task 升序、空→[]）与 `services/audit.py`（record(task_id, run_id, actor, action, target, result, detail)；detail 超长截断、含密钥值过滤/脱敏）；单测覆盖

## 2. 模型装配（ModelFactory）

- [x] 2.1 `services/model_factory.py`：`resolve_model(task_id)`——取 `model_service.get_task_config` + `get_provider_or_raise`；密钥解析 env 覆盖（`LINGSHU_<供应商名大写>_API_KEY`）优先、否则 `crypto.decrypt(api_key_enc)`，皆无→可读错；组 `OpenAICredential(api_key, base_url)` + `OpenAIChatModel(credential, model, parameters=<temperature/max_tokens>)`（parameters 字段名以 `inspect.signature` 核对）；出口不含密钥明文
- [x] 2.2 model_factory 单测：env 覆盖优先于库内密文、无 key→可读错、temperature/max_tokens 注入（打桩 env + mock）

## 3. MCP 客户端装配

- [x] 3.1 `services/mcp_client.py`：按挂载 MCPConnector 配置（transport stdio/http、命令/url、env/headers 密文经 `crypto.decrypt` 后注入、trust/enabled 语义）构造 `MCPClient`（`StdioMCPConfig`/`HttpMCPConfig`）；提供注册函数与 teardown close（LIFO）；密钥值不入日志/事件。已核对：MCPClient 强制 stdio stateful（否则 pydantic 校验拒）、http 可无状态；构造纯配置零副作用，真连接留会话期（`connect_clients` 撤下失败者、`attach_to_toolkit` 供 group 6 接）
- [x] 3.2 mcp_client 测试：对指向不存在命令的 stdio 配置断言注册不崩溃且不真拉起；enabled=false 跳过；http 配置构造字段正确（整块 mock 客户端）

## 4. Agent 组装与系统提示拼接

- [x] 4.1 `services/agent_runtime.py::build(task_id)`：读任务 + `capability.load_mounted`；拼 system_prompt（基础运维人设→任务上下文→挂载技能 skill_md→挂载专家 system_prompt）；Toolkit=内置工具（Bash/Read/Write/Edit/Glob/Grep，Windows 加 PowerShell）+ 挂载 MCP；停用/未就绪实体跳过；返回 (agent, 描述 dict)。已核对：MCP 分流 http 无状态直接 live、stdio（强制 stateful）deferred 待会话 connect 后 attach；desc 下划线键 `_deferred` 内嵌待连接客户端对象供会话消费，`require_deferred_clients` 取回
- [x] 4.2 build 测试（FakeModel 打桩，不联网）：断言注入的 system 含技能指令与专家人设；toolkit 含内置工具名与挂载 MCP 工具（注入整块 mock 客户端离线证明）；无挂载任务仍可组普通 Agent；任务无模型→可读错

## 5. 危险工具二次确认接法

- [x] 5.1 用最小打桩 Agent 先验证 2.0.7 确认协议：请求 Bash/Write/Edit 时产出 `RequireUserConfirmEvent` 且 reply 暂停；以 `UserConfirmResultEvent` 续跑放行/拒绝两条路径均可继续到终态（确认实际钩子在 PermissionEngine 还是工具声明，见 design D5/Open Questions）——实验结论：钩子在 **PermissionEngine**；`AgentState` 默认 `PermissionContext(mode=DEFAULT)` 已使 Write/Edit/非只读 Bash 自动 ASK（Read/Glob/Grep 与只读 bash 走只读快速通道 ALLOW）；`build()` 显式置 DEFAULT 以防默认漂移。放行→工具真执行+`tool_result(success)`，拒绝→`tool_result(denied)` 绝不执行，两者都续跑至 `done`
- [x] 5.2 按 5.1 结论把 Permission confirm 规则/工具声明接通到 build()：内置写/执行类工具默认二次确认；拒绝路径把「用户拒绝」结果喂回 Agent 且绝不执行
- [x] 5.3 确认护栏：同一 confirm_id 只可回执一次、失效 run/confirm→404；放行/拒绝写审计（actor=user）——并入端点测试

## 6. SSE 驱动与会话生命周期

- [x] 6.1 `agent_runtime.py` 驱动：每任务单活动 Session（内存注册表）；worker 线程+独立 asyncio loop + msg_queue/decision_queue；park/continue 环（spec R2/R4 事件类型与 run_id；confirm_request 后从 decision_queue 取回执续跑）；done 收尾并落助手文本
- [x] 6.2 事件→SSE 类型映射（text_delta/text/thinking_delta/tool_call/tool_result/confirm_request/error/done）与序列化（UTF-8 JSON、`data:` 行）；SSE 生成器 + teardown（连接断开/流结束→cancel 唤醒决策等待与流循环、close MCP、释放注册表，任务可再次发起）；并发 chat→409。设计注：断开时不向模型流投 UserInterruptEvent——连接已无消费者，cancel（置取消位 + 注入取消回执）即等价收尾且不产生伪消息；`events()` 以终端帧（done/error）为收尾判据而非线程存活，避免快脚本下漏掉已入队的 done
- [x] 6.3 驱动单测（FakeModel + 真实 Agent/Toolkit）：打字机文本事件序与 done；确认放行/拒绝续跑；连接断开后任务可再次发起

## 7. 对话端点与历史

- [x] 7.1 `api/runtime.py`（blueprint url_prefix=/api，注册入 app.py）：`POST /api/tasks/<id>/chat`（JSON {message}；404/400/409；无模型→SSE 首事件 error 后结束，不落伪消息）；`POST /api/tasks/<id>/chat/decision`（run_id/confirm_id/allow）；`GET /api/tasks/<id>/messages`（升序；空→[]；404）
- [x] 7.2 集成测试：一次对话（FakeModel）后 messages 含 user+assistant 且与 SSE 文本一致；模型失败只留 user；decision 对失效 id→404

## 8. 审计接线

- [x] 8.1 驱动内接线：model_call（模型标识+近似用量，不含密钥）、tool_call（工具名+成败）、confirm_decision（allow/deny，actor user/runtime）写 AuditLog；detail 截断/脱敏
- [x] 8.2 审计测试：一次含确认+工具调用运行后 AuditLog 出现三类记录且可关联 task/run；无密钥明文

## 9. 全量回归与收尾

- [x] 9.1 `uv run pytest backend/tests/ -q` 全绿（93 passed，含既有用例无回归）；前端未改动，`npm run build` 不受影响
- [x] 9.2 （可选、有真实 key 才跑）dev 冒烟：对种子任务 `curl -N POST /api/tasks/<id>/chat` 收文本+done。本期无真实 key，冒烟跳过——离线 FakeModel 集成测试（7.2）已覆盖同一路径（SSE 事件序 + done）
