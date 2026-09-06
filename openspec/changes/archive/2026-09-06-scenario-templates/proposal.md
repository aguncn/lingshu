## Why

十二运维域（§8 表）是 PRD 核心差异点：每域差异化系统提示 + 预设工具/技能/专家装配，决定智能体「专业不像玩具」。目前 Task 已预留 `scenario_domain` 列、运行时（P8 agentscope-runtime）也已声明"供 P9 场景模板接入"，但尚无模板实体、种子、模板文件与运行时按域注入——选任意域建任务都只会得到通用运维人设。本提案补齐这条链路，让同一套运行时按域产出专业结论。

## What Changes

- **ScenarioTemplate 实体 + 迁移 + 十二域种子**：每域一条记录，含受控 `domain` 键、`name`、`system_prompt`（领域提示词）、`task_template`（任务引导）、`preset_skills/preset_mcp/preset_kb/preset_expert`（预设装配）。
- **十二域提示词落 `backend/prompts/scenarios/*.md` 供版本管理**：文件为系统提示词唯一来源，seed 幂等装载入表；附 `README.md` 设计说明。监控巡检 / 故障诊断两域补**真实 preset 示例**（种子若干 Skill/MCP/KB/Expert 实体供其引用），其余十域 preset 为空、由用户后续挂载。
- **`GET /api/scenarios` 列表 / 单查**：返回十二域元数据，供前端"选域"分类（列表含每域预设装配概览）。
- **`POST /api/tasks/<id>/scenario/apply {domain}`（独立 apply 接口）**：设 `task.scenario_domain`，把该域 `preset_*` 解析为现存可用实体后**复用 P4 caps 全量覆盖语义**写挂载，返回装配汇总与跳过的缺失实体；未知域 → 400。P2 建任务 / P4 caps 契约零改动；建任务后前端调一次即可，细节栏仍可再 `PUT caps` 逐次覆盖（UI-06）。
- **运行时按域注入（仅域会话）**：AgentRuntime 组装系统提示时，对绑定了已存在 `scenario_domain` 的任务，其 system_prompt = 域模板 `system_prompt` 前置 + 现有专家/技能挂载内容 + **统一约束段收尾**（禁臆造数据 / 危险操作二次确认 / 回答引用来源 / 输出结构化报告表格工单）；无域 / 未知域任务系统提示与现状完全一致。

## Capabilities

### New Capabilities
- `scenario-templates`: 十二运维场景域的模板实体与种子、`prompts/` 版本化提示词、列表/单查 REST、`POST /tasks/<id>/scenario/apply` 套用预设装配，以及 AgentRuntime 对域任务的系统提示注入（域提示词前置 + 统一约束段收尾）。后端能力域，单域提案。

### Modified Capabilities
<!-- 无：agentscope-runtime 主规范 Purpose 已声明"供后续 P9 场景模板接入"，且仅对域任务做前置+收尾的增量拼装，不改变其既有需求文本；space-task-mgmt 仅消费其已预留的 scenario_domain 列，不改建任务契约。 -->

## Impact

- 新增：`backend/models.py`（ScenarioTemplate + DOMAIN 常量）、`backend/migrations/0007_scenario_templates.sql`、`backend/prompts/scenarios/`（12 个 `.md` + README）、`backend/seed/scenarios.py`、`backend/services/scenario_service.py`、`backend/api/scenario.py`。
- 修改：`backend/services/agent_runtime.py`（`_compose_system_prompt` 域注入）、`backend/app.py`（注册 blueprint）、种子装配示例实体。
- 消费既有 P4 caps 覆盖写与 P8 消息/审计链路，不改其契约。
- 前端工作台"新建任务选域 / 顶部分类展示"属 `workbench-ui` 后续提案，不在本域。
