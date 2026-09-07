## 1. 数据模型与迁移

- [x] 1.1 `models.py`：`TASK_PERMISSION_MODES = {"strict","limited","trusted"}`；`tasks.permission_mode` 列（`db.String(16)`，`default="strict"`、`nullable=False`），`to_dict` 暴露该字段
- [x] 1.2 `migrations/0009_task_permission_mode.sql`：`ALTER TABLE tasks ADD COLUMN permission_mode TEXT NOT NULL DEFAULT 'strict';` 既有行回填最严档

## 2. API 承载与校验（services/task_service.py / api/space_task.py）

- [x] 2.1 任务创建 `POST /api/spaces/<sid>/tasks` 接受可选 `permission_mode`，经白名单 `_clean` 校验（越界 400），缺省 `strict`
- [x] 2.2 任务修改 `PATCH /api/tasks/<id>` 支持改 `permission_mode`（越界 400），返回更新后任务含该字段；列表/详情对象含 `permission_mode`

## 3. 运行时档位映射（services/agent_runtime.py）

- [x] 3.1 `_permission_context_for(mode_key)`：`strict`/未知 → `PermissionMode.DEFAULT`；`trusted` → `BYPASS`；`limited` → `BYPASS` + ask 规则（`Write`/`Edit` 全量 + `_LIMITED_DANGEROUS_SUBSTRINGS` 逐条子串）
- [x] 3.2 `_LIMITED_DANGEROUS_SUBSTRINGS`（Bash：rm/rmdir/unlink/shred/mv/cp/sed -i；PowerShell：remove-*/del/erase/rd/rmdir/move-*/copy-*/set-content/clear-content/out-file/ren 等）；`_AskablePowerShell` 子类覆写 `match_rule` 按命令内容大小写不敏感子串匹配并挂入内置工具（Windows）
- [x] 3.3 `build()`：`AgentState(permission_context=_permission_context_for(task.permission_mode))` 显式装配；desc 快照 `permission_mode`（每次会话即时取用，改档只影响后续 run）

## 4. 前端选择与调整入口

- [x] 4.1 `constants.js`：`PERMISSION_MODE_META`（严格/有限/完全信任 + 文案）与 `PERMISSION_MODE_ORDER`
- [x] 4.2 `TaskCreateDialog.vue`：新建任务表单加「权限模式」三档下拉，随 `POST` 提交；每次打开回默认 `strict`
- [x] 4.3 `DetailDock.vue`：原「权限模板」占位分区替换为「权限模式」分区——三档 radio 即时切换，`PATCH /api/tasks/<id>` 持久化，成功提示「下次提问生效」

## 5. 测试与收尾

- [x] 5.1 后端补单测：三档权限上下文映射、limited 危险子串命中/放行、PowerShell 命令大小写匹配、改档后新 run 生效、白名单外值 400
- [x] 5.2 `cd frontend && npm run build` 通过；浏览器手工验收（新建选档、细节栏切档持久化、strict 确认 / limited 仅危险子集确认 / trusted 免确认）
