## Context

Task 模型已预留 `scenario_domain` 列（P2），`POST/GET/PATCH` 任务接口已透传该字段、暂不校验；P8 运行时 `_compose_system_prompt(task, skills, experts)` 目前 = 专家人设（或基础运维人设）+ 技能指令，agentscope-runtime 主规范 Purpose 声明"供后续 P9 场景模板接入"。设计权威 §8 给出十二域表与"每域 = 一条 ScenarioTemplate（domain + system_prompt + task_template + preset_*）"及统一约束四条；§9 目录约定 `backend/seed/` 与 `backend/prompts/`。动机见 proposal.md。

## Goals / Non-Goals

**Goals:**
- 十二域模板成为一等数据：DB 行 + `prompts/scenarios/*.md` 版本化来源 + 幂等 seed。
- 提供"选域套模板"的落点：独立 `POST /api/tasks/<id>/scenario/apply`，不改变 P2/P4 契约。
- 域任务的运行时系统提示 = 域提示词前置 + 既有角色/技能 + 统一约束段收尾；无域任务零影响。

**Non-Goals:**
- 前端"新建任务选域/顶部分类/细节栏展示"（`workbench-ui` 后续提案）。
- 自动引擎/深度 MCP 真实连接器、任务按域在服务端自动选模型等（P1/P2）。
- 统一约束段对无域任务注入（已裁定仅域会话）。

## Decisions

- **D1 `prompts/scenarios/*.md` 是系统提示词唯一来源，seed 负责装载。** 迁移是静态 `.sql`，无法读 .md；故 `0007` 只建表，`backend/seed/scenarios.py` 在应用初始化（或显式 seed 入口）读 12 个 `.md` 按 `domain` 幂等插入（写 `system_prompt` + 最小 `task_template`）。选文件为唯一来源：版本管理、审阅、与 agent 提示词同仓演进；seed 仅插入缺失域行，人工改动或改版由显式 reseed 流程处理（`prompts/scenarios/README.md` 说明），默认不覆盖既有行。
- **D2 受控域枚举集中一份常量**（`SCENARIO_DOMAINS`：12 个 `(key, label)`），供 models 校验、api 白名单、seed、runtime 注入共用，避免四处硬编码漂移。域键用英文 slug（如 `monitor-inspection`、`fault-diagnosis`），label 为 §8 中文名。
- **D3 preset_* 存实体 id 的 JSON 文本列**，容忍漂移。四类引用以 Text-JSON 数组存行内（复用项目 SQLite 无 JSONB 的现实），`apply` 时解析为现存且 enabled 的实体 id 再写挂载；被删/停用引用**跳过而非失败**，汇总里报 skip——因为注册中心实体是动态 CRUD，固化引用必然随时间失效。
- **D4 套用走"独立 apply + 复用 P4 caps 覆盖写"**（用户裁定）。`POST /api/tasks/<id>/scenario/apply {domain}` 服务内：校验域 → `task.scenario_domain = domain` → 把 preset id 求交现存实体 → 调既有 caps replace 覆盖四类关联 → 返回 `{domain, mounted:{skills,mcps,kbs,experts}, skipped:[...]}`。与前端约定：建任务成功后调一次即完成"选域套模板"；细节栏仍可 PUT caps 覆盖（P4 全量语义不变）。错误：任务不存在 404、域非受控 400，均无副作用。
- **D5 运行时注入做成增量拼装。** `agent_runtime._compose_system_prompt` 首步：仅当 `task.scenario_domain` 命中受控枚举且表内有该行时，取 `template.system_prompt` 作为最前领域段；既有专家/技能段照旧居中；统一约束常量 `UNIFIED_CONSTRAINTS`（禁臆造数据／危险操作二次确认／回答引用来源／输出结构化报告·表格·工单）收尾。域缺失/无域 → 原样返回既有拼装，绝不因模板问题抛错——保证既有无域对话与 P8 测试不回归。
- **D6 两个示例域的真实 preset 靠 seed 造实体。** "监控巡检/故障诊断"的预设要可挂载，就必须有真实 Skill/MCPConnector/KnowledgeBase/Expert 行：seed 以 `(type,name)` 幂等建少量示例实体（如 monitor-inspection：监控 MCP 连接器 + 巡检规范库 KB + 巡检报告 Skill；fault-diagnosis：SRE 专家 + 链路/日志类连接器），再让这两域 `preset_*` 指向其 id；其余十域 preset 空数组。实现修订：fault-diagnosis 预设按产品验收「监控+日志+链路 MCP + SRE 专家」把监控连接器并入——`preset_mcp` 取 监控(prometheus-mcp) + 日志(log-mcp) + 链路(trace-mcp) 三者，监控连接器与 monitor-inspection 域共用同一示例实体（preset 可跨域复用同一实体）。
- **D7 新 blueprint 收敛**：`api/scenario.py`（`/api/scenarios` 前缀，列表/单查/apply）+ `services/scenario_service.py` 承载逻辑，API 层只做校验转发，遵循 models.py 集中建模、services 放业务、api 轻的既有分层。

## Risks / Trade-offs

- [preset 引用实体随时间被删/停用] → apply 交现存集合 + 跳过策略，汇总透出 skip；seed 示例实体幂等重建（D3/D4/D6）。
- [统一约束段与 Permission 层二次确认重复] → 属提示级 + 机制级双保险，无冲突；约束仅域会话注入，无域行为与 P8 完全一致（D5）。
- [seed 装载时机：应用初始化自动跑 vs 显式命令] → 采用幂等、缺失行才插入的自动 seed，避免"忘了 seed 十二域为空"；需要改版提示词时走 README 文档化的显式 reseed 流程。
- [`.md` 文件唯一来源带来"改了文件但库里还是旧值"的漂移窗口] → seed 默认不覆盖既有行，改版经显式 reseed（比对文件覆盖对应域）执行，README 写明流程与风险。
- [apply 全量覆盖 caps 会清掉用户此前手工挂载] → "选域套模板"本就是模板语义；文档注明 apply 后再用 PUT caps 微调（UI-06）。

## Migration Plan

`uv run flask --app backend.app migrate`（或既有 migrate 命令）执行 `0007_scenario_templates.sql` → schema_version 前进；随后重启后端触发 seed 装载十二域与两域示例实体。回滚：删 0007 行 + 重跑旧 migrate 即可，无数据依赖历史任务（`scenario_domain` 列早已存在，仅在 apply/运行时被消费）。

## Open Questions

无。前端消费属 `workbench-ui` 域另行提案；apply 落点与约束注入范围已经用户裁定，无影响任务拆分的悬而未决项。
