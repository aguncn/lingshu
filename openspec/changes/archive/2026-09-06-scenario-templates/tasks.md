## 1. 数据模型与提示词源

- [x] 1.1 `models.py` 新增 `ScenarioTemplate`（domain 唯一/name/system_prompt/task_template/preset_skills/preset_mcp/preset_kb/preset_expert，preset_* 用 Text-JSON 存 id 数组），并定义集中式 `SCENARIO_DOMAINS` 受控枚举常量（12 个 `(key,label)`）供 model/api/seed/runtime 共用
- [x] 1.2 写迁移 `backend/migrations/0007_scenario_templates.sql` 建表（domain 唯一约束），跑 migrate 使 schema_version 前进
- [x] 1.3 写 `backend/prompts/scenarios/<domain>.md` 十二个系统提示词文件（正文按设计 §8 各域"系统提示要点"），附 `README.md`（域键说明 + 提示词改版/reseed 流程 + 统一约束设计）

## 2. 种子与示例装配

- [x] 2.1 `backend/seed/scenarios.py`：应用初始化时读 `prompts/scenarios/*.md` 幂等装载十二域（system_prompt + 最小 task_template，preset_* 本步为空），仅插入缺失行、不覆盖既有行
- [x] 2.2 该 seed 以 `(type,name)` 幂等造少量真实示例注册中心实体：监控巡检（监控 MCP 连接器 + 巡检规范库 KB + 巡检报告 Skill）、故障诊断（SRE 专家 + 监控/日志/链路 三连接器，监控连接器为对齐产品验收补挂、与监控巡检共用）等，供 preset 引用
- [x] 2.3 把"监控巡检 / 故障诊断"两域 preset_* 指向上述示例实体 id（其余十域 preset 空），使两域"真实 preset"可直接套用

## 3. 场景域 REST

- [x] 3.1 `services/scenario_service.py` + `api/scenario.py`（新 blueprint，注册进 app）：`GET /api/scenarios` 列表（固定十二域序 + name + 装配摘要）、`GET /api/scenarios/<domain>` 详情（system_prompt/task_template/preset_* 全文）；未知域单查 404
- [x] 3.2 `POST /api/tasks/<id>/scenario/apply`：body 必填受控 domain；任务不存在 404 / 域非受控 400（均无副作用）；成功 → 设 task.scenario_domain 并把 preset id 求交现存启用实体后复用 caps 覆盖写，返回装配汇总（mounted 四类 + skipped 引用）

## 4. 运行时按域注入

- [x] 4.1 `agent_runtime.py` 定义 `UNIFIED_CONSTRAINTS` 常量（禁臆造数据／危险操作二次确认／回答引用来源／输出结构化报告·表格·工单）
- [x] 4.2 `_compose_system_prompt` 增量拼装：仅当 task.scenario_domain 命中受控枚举且表内存在该行 → 域 system_prompt 前置、末尾追加 UNIFIED_CONSTRAINTS；无域/域缺失走原拼装且不报错

## 5. 测试与验收

- [x] 5.1 `backend/tests/test_scenarios.py`：种子后恰 12 域且 system_prompt==文件内容、重复 seed 不重复；GET 列表 12/单查/未知域 404；apply→scenario_domain+caps 含预设、未知域 400、任务 404、缺失实体 skip 仍 200；运行时系统提示含域段+统一约束、无域任务与既有一致
- [x] 5.2 跑 `uv run pytest backend/tests/ -q` 全绿；`curl http://127.0.0.1:5000/api/scenarios` 返回 12 个域
