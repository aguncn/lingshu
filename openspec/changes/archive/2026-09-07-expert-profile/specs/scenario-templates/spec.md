## REMOVED Requirements

### Requirement: 场景域实体与受控域枚举

**Reason**: C5 用户已拍板硬删十二场景域体系——十二域是强行的分类心智，用户并不按它组织工作；域实体与「受控域枚举」随之失去唯一消费方。

**Migration**: 迁移 0010 `DROP TABLE IF EXISTS scenario_templates`；`tasks.scenario_domain` 列一并 `ALTER TABLE tasks DROP COLUMN scenario_domain`。域模板/预设能力由 registry-center「运维专家档案」与 capability-mount「档案快照装配到任务」取代：用户把 人设+技能/MCP/RAG+资料+默认模型 组装为档案，在能力广场选档案套用。

### Requirement: 十二域提示词模板版本管理与幂等装载

**Reason**: `backend/prompts/scenarios/`（十二域 .md + README）随 C5 删除；以文件为系统提示唯一来源再 seed 入库的十二域装载机制不复存在。

**Migration**: 删除 `backend/prompts/scenarios/` 目录；种子由 scenario seed 切换为 seed/profiles.py——只幂等收敛「SRE 值班专家」等运维专家档案（回填空 preset，不覆盖用户改动）。

### Requirement: 场景域列表与单查

**Reason**: 十二域列表/单查 REST（`GET /api/scenarios[/<domain>]`）唯一供域条与建任务「场景模板」下拉消费；两处入口均被移除。

**Migration**: 删除 `api/scenario.py`/`services/scenario_service.py` 及对应测试；前端「运维专家」档案列表经既有 `GET /api/experts`（registry-center）获取。

### Requirement: 选域套用预设装配

**Reason**: 「选域 → 把域 preset 覆盖到任务 caps」由「选运维专家档案 → 快照装配到任务」取代，语义升级为快照（此后改档案不影响已建任务）。

**Migration**: `POST /api/tasks/<id>/scenario/apply` 删除；新增 `POST /api/tasks/<id>/expert/apply`（见 capability-mount「档案快照装配到任务」）。建任务对话框「场景模板」下拉移除，改可选「运维专家」触发 apply。

### Requirement: 运行时按域注入系统提示（域会话）

**Reason**: 运行时不再有「域模板前置 + 统一约束段收尾」注入——域注入随域体系整体退场。

**Migration**: `agent_runtime.build()` 移除按 `task.scenario_domain` 取模板拼装；人设 = 挂载运维专家 system_prompt（快照优先，见 agentscope-runtime「任务挂载能力注入」），无专家回退 BASE。无 `scenario_domain` 分支后任务一律按既有角色拼装。
