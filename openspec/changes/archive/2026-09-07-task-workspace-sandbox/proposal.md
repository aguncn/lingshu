## Why

AgentScope 内置写/执行类工具（`Bash`/`PowerShell`）默认以进程当前目录为 cwd 运行——此前智能体生成的 `Write/PowerShell` 产物直接散落到**仓库根**（`现代诗-生于七十年代.md` 等孤儿文件即证据），跨任务互相污染、按任务无法回溯其产物。`data/spaces/<space_id>/<task_id>/` 的目录体系与扫描已存在（P2），但运行时不收敛进去。

本变更实现「**一次任务一个连续工作目录**」的沙箱：工具进程 cwd 收敛到该任务目录、系统提示声明工作目录并指引把产物放进去；同任务多轮问答共享同一目录（可续改上一轮产物），目录随任务删除清理。浏览器手工验收通过，现回填规范并归档。

## What Changes

- **工具进程 cwd 收敛（软沙箱）** `services/agent_runtime.py`：`_builtin_tools(cwd=None)` 给 `Bash(cwd=cwd)` 与 `PowerShell(cwd=cwd)` 传任务目录（构造支持 `cwd=`，Windows/非 Windows 一致）。Read/Write/Edit 仍要求绝对路径、无法硬约束 cwd，因此这是**软沙箱**：shell 相对路径即相对任务目录；越界写仍由既有 permission_mode 二次确认闸门兜底（strict=全确认、limited=Write/Edit 全确认、trusted 用户自担，语义不变）。
- **装配即建目录**：`build()` 在组装 Agent 前经 `file_store.ensure_task_dir(space_id, task_id)` 幂等创建任务目录并取绝对路径 `workdir`（依赖 `current_app`，恒在应用上下文内被调——ChatSession 于请求线程 create、测试各有 app ctx）；建目录失败是真实 IO 错误，**向上抛由端点转 SSE error**，而非静默回落到进程 cwd 继续在仓库根制造散落文件。运行描述 `desc.workdir` 暴露该目录供审计/调试核对。
- **提示注入工作目录**：`_task_context_block(task, workdir)` 追加一行 `- 工作目录：<绝对路径>`，并说明「本任务生成或修改的文件请放入该工作目录：Read/Write/Edit 给出其中的绝对路径；Bash/PowerShell 已在该目录下执行，相对路径即相对工作目录」。
- 无 schema 变更、无迁移；前端文件列表沿用既有 `GET /api/tasks/<id>/files`（本就扫任务目录），任务删除的目录清理为既有级联语义。

## Capabilities

### New Capabilities
<!-- 无新增能力。 -->

### Modified Capabilities
- `agentscope-runtime`: 装配对话运行时为任务创建/沿用 `data/spaces/<space_id>/<task_id>/` 工作目录，把内置命令/执行工具进程 cwd 与其收敛，并在系统提示中声明该工作目录与写入指引。

## Impact

- 后端：`services/agent_runtime.py`（`_builtin_tools(cwd=)`、`_task_workdir`/建目录、`_task_context_block` 注入工作目录、`build()` 传参、`desc.workdir`）、`services/file_store.py`（既有 `ensure_task_dir`，不改）。
- 测试：新增 `backend/tests/test_sandbox_workdir.py`（Bash/PowerShell 实例 cwd 断言、任务上下文含工作目录、注入临时 DATA_DIR 后 `build()` 创建任务目录、`desc.workdir` 指对该目录）；既有 `test_runtime_services` 中假设无参 `_builtin_tools()` 的断言随签名更新。
- 前端/数据：无改动、无迁移。仓库根既有孤儿产物为历史 Agent 残留，不迁移；沙箱生效后不再新增。

## 验证

- `uv run pytest backend/tests/ -q` 全绿（含新增 test_sandbox_workdir 与既有 runtime 回归）。
- 手工：配真模型跑一轮让 Agent 生成文件，产物出现在 `data/spaces/<space_id>/<task_id>/`（不再落仓库根）；同任务第二轮可读改第一轮产物；`GET /api/tasks/<id>/files` 能列出。
