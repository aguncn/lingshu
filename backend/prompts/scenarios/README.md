# prompts/scenarios —— 十二运维场景域系统提示词源

本目录是 `ScenarioTemplate.system_prompt` 的**唯一来源**（P9 scenario-templates，design D1）。
每域一个 `<domain>.md`，正文按设计 §8 各域「系统提示要点」撰写，随 git 版本管理；
应用初始化时由 `backend/seed/scenarios.py` 幂等装载入库（仅插入缺失域、**不覆盖既有行**）。

## 域键说明

域键即 `Task.scenario_domain` 取值、DB `domain` 列、本目录文件名与 models 受控枚举三方共用的主键。
受控枚举与展示名的唯一权威定义在 `backend/models.py::SCENARIO_DOMAINS`（勿在本目录再抄一份，避免漂移）：

| 域键 | 展示名 |
| --- | --- |
| `monitor-inspection` | 监控巡检 |
| `log-triage` | 日志隐患 |
| `db-performance` | 数据库性能排查 |
| `middleware-setup` | 中间件安装配置 |
| `alert` | 告警 |
| `fault-diagnosis` | 故障诊断 |
| `change-risk` | 变更风险 |
| `capacity-forecast` | 容量预测 |
| `cmdb-governance` | CMDB 数据治理 |
| `kb-qa` | 知识库问答 |
| `runbook-generation` | 应急预案生成 |
| `ops-scripting` | 运维脚本编写 |

## 提示词改版 / reseed 流程

改版分两步（README 外唯一入口是 `seed/scenarios.py::reseed`）：

1. 直接编辑目标 `.md`（走 git 评审/历史）。
2. 显式执行 reseed 覆盖对应库内行（自动 seed 默认不覆盖，避免「改了文件库里还是旧值」的静默窗口）：

   ```bash
   uv run python -c "from backend.app import app; from backend.seed.scenarios import reseed; app.app_context().push(); print(reseed(['fault-diagnosis']))"
   ```

   `reseed()` 仅覆盖 `system_prompt`（及展示名），**不触碰 `preset_*`**（可能已被人为调整）。
   不带参数则重载全部十二域。重启/下一次任意 app 创建即触发自动 seed，无需额外操作。

## 统一约束设计

十二域 `.md` 只写「领域角色 + 工作准则 + 结构化输出」；跨域的**统一约束段**
（禁臆造数据／危险操作二次确认／回答引用来源／结构化输出）不作为文件正文重复落盘，
而由 `services/agent_runtime.py::UNIFIED_CONSTRAINTS` 常量在**域会话**装配时统一收尾追加
（design D5，无域任务不注入、行为与 P8 完全一致）。需要调整统一约束时只改该常量一处。

## 一致性测试

`backend/tests/test_scenarios.py` 断言「种子后 `system_prompt` 与对应 `.md` 逐字一致、
恰十二行、重复 seed 不产生重复」，改本目录文件若不同步 reseed，测试即红——用测试兜住漂移。
