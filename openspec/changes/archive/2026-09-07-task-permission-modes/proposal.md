## Why

P8 会话内置写/执行类工具（Bash/Write/Edit/PowerShell）一律在调用前二次确认（即现在的「严格」档），对真实运维任务存在两个不适：

1. **确认频次不可调**：逐条确认虽安全，但对高频、低危的运维操作过度打断；而需要全自动/少打扰的场景（模型值得信任的受限任务）又无法按任务放开。
2. **任务级不可选、运行后不可调**：权限策略理应是任务属性——每任务的工具暴露面与风险等级不同；但新建任务时无法选择、创建后也看不到/改不了，只能全局一刀切。

本变更引入**任务级权限模式**（`permission_mode`，三档：`strict` 严格 / `limited` 有限 / `trusted` 完全信任）：默认 `strict` 与旧行为逐字一致；`limited` 只对「删除/覆盖类命令 + 修改本地文件」确认一次；`trusted` 全程无人工确认。新建任务时可选（每次回默认最严），细节栏可随时调整（下次提问生效）。浏览器手工验收通过，现回填规范并归档。

## What Changes

- **space-task-mgmt（数据与 API）**：`tasks` 表新增 `permission_mode` 列（迁移脚本 0009，既有行回填 `strict`）；`POST /api/spaces/<sid>/tasks` 与 `PATCH /api/tasks/<id>` 接受并校验三档取值（越界 400），任务对象暴露该字段。
- **agentscope-runtime（权限档位映射）**：装配 Agent 时按任务 `permission_mode` 映射进 AgentScope 权限上下文——`strict` → 默认模式（写/执行类工具请求即确认）；`trusted` → `BYPASS`（全程免确认）；`limited` → `BYPASS` + 少量 ask 规则（Write/Edit 全量 + Bash/PowerShell 删除/覆盖类命令子串），PowerShell 以命令内容大小写不敏感子串匹配。每次会话按任务当前值即时取用，运行中改档只影响之后新发起的 run。
- **workbench-ui（选择与调整入口）**：新建任务对话框提供「权限模式」三档选择（默认 `strict`、每次打开回默认）；细节栏原「权限模板」远期占位替换为「权限模式」分区，三档即时切换并 `PATCH` 持久化、提示「下次提问生效」。
- 数据库变更走编号 SQL 迁移；无新增外部依赖。

## Capabilities

### New Capabilities
<!-- 无新增能力。 -->

### Modified Capabilities
- `space-task-mgmt`: 任务创建/修改接受并持久化 `permission_mode`（含迁移与枚举校验）。
- `agentscope-runtime`: 任务级权限模式到 AgentScope 权限上下文的档位映射。
- `workbench-ui`: 新建任务对话框权限模式选择；细节栏「权限模板」占位替换为「权限模式」分区。

## Impact

- 后端：`models.py`、`migrations/0009_task_permission_mode.sql`、`api/space_task.py`、`services/task_service.py`（字段承载/校验）、`services/agent_runtime.py`（档位映射、PowerShell 子串匹配子类）。
- 前端：`constants.js`（三档元数据）、`components/layout/TaskCreateDialog.vue`（新建选择）、`components/layout/DetailDock.vue`（权限模式分区调整）。
- 测试：`backend/tests/` 补三档映射/危险子串/大小写/改档生效用例；`npm run build` 通过。
