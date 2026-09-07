> 任务工作空间沙箱（C2）：代码已实现、`uv run pytest backend/tests/ -q` 全绿，逐条回填验收口径。纯后端，无迁移、无前端改动。

## 1. 内置工具进程 cwd 收敛

- [x] 1.1 `services/agent_runtime.py` `_builtin_tools(cwd=None)`：把 `cwd` 透传给 `Bash(cwd=cwd)` 与 `PowerShell(cwd=cwd)`（Windows 分支经 `_askable_powershell_cls` 子类同样传 cwd）；`None` 回落进程 cwd（兼容无参调用与测试）。验收：构造出的 Bash/PowerShell 实例 cwd 为该值；Windows/非 Windows 一致。
- [x] 1.2 更新既有断言无参 `_builtin_tools()` 的用例（`test_runtime_services` 等）随签名演进，不回归。验收：全量 `pytest` 绿。

## 2. 装配即建任务目录并注入工作目录

- [x] 2.1 `_task_workdir(task)`：经 `file_store.ensure_task_dir(task.space_id, task.id)` 幂等建目录并取绝对路径（`data/spaces/<space_id>/<task_id>/`）；`build()` 于组装 Agent 前调用，并把该 `workdir` 传入 `_builtin_tools(cwd=workdir)`；运行描述 `desc["workdir"]` 暴露该绝对路径。验收：注入临时 DATA_DIR 后 `build()` 创建任务目录、desc.workdir 指向它；重复 build 幂等沿用。
- [x] 2.2 目录创建失败即真实 IO 错误，向上抛（由端点转 SSE error），不静默回落进程 cwd。验收：单测用不可建路径断言会话以 error 结束、仓库根无新散落文件。
- [x] 2.3 `_task_context_block(task, workdir)` 追加 `- 工作目录：<绝对路径>` 行及写入指引（Read/Write/Edit 用其中绝对路径、Bash/PowerShell 已在该目录下执行、相对路径即相对工作目录）；workdir 缺省不注入该段，兼容旧调用。`_compose_system_prompt` 透传 workdir。验收：单测断言上下文块含工作目录与指引、无 workdir 时不出现。

## 3. 产物回看与目录清理联动

- [x] 3.1 不改文件列表契约：前端文件抽屉沿用既有 `GET /api/tasks/<id>/files`（扫任务目录），沙箱产物即出现；任务删除目录级联清理沿用既有语义。验收：`GET /files` 能列出任务目录内的本轮新产物（同任务多轮共享目录）；删除任务后目录清空。

## 4. 测试与回归

- [x] 4.1 新增 `backend/tests/test_sandbox_workdir.py`：断言 Bash/PowerShell 实例 cwd；`_task_context_block` 含工作目录；注入临时 DATA_DIR 后 `build()` 建目录、`desc.workdir` 指对目录；不可建路径 → 以错误结束且不写仓库根。验收：单测通过。
- [x] 4.2 全量回归：`uv run pytest backend/tests/ -q` 全绿；手工真模型跑一轮，产物出现在 `data/spaces/<space>/<task>/`（不再落仓库根）。
