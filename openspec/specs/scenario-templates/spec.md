# scenario-templates Specification

## Purpose

以十二运维场景域为粒度，为任务提供可版本化、可装配的领域模板：`prompts/scenarios/*.md` 作为系统提示词唯一来源并 seed 入库，REST 提供十二域列表/单查与「选域套用预设装配」入口，运行时对绑定场景域的任务按「域提示词前置 + 统一约束段收尾」拼装系统提示，让同一套 AgentScope 运行时按域产出专业、可验收的结论。

## Requirements

### Requirement: 场景域实体与受控域枚举

系统 SHALL 提供 ScenarioTemplate 数据模型，字段含：受控 `domain` 键、`name`、`system_prompt`（领域系统提示）、`task_template`（任务引导/建任务预填）、`preset_skills`/`preset_mcp`/`preset_kb`/`preset_expert`（预设装配引用）。`domain` SHALL 是受控枚举，取值恰好为十二个运维场景域：监控巡检、日志隐患、数据库性能排查、中间件安装配置、告警、故障诊断、变更风险、容量预测、CMDB 数据治理、知识库问答、应急预案生成、运维脚本编写；`domain` SHALL 唯一。迁移后 SHALL 存在该表，其余场景（列表/套用/注入）只接受这十二个受控键。

#### Scenario: 迁移后存在唯一域表

- **WHEN** 完成数据库迁移且初始化种子
- **THEN** `scenario_templates` 表存在，`domain` 列唯一，十二个受控域键可被程序枚举

### Requirement: 十二域提示词模板版本管理与幂等装载

系统 SHALL 以 `backend/prompts/scenarios/<domain>.md` 作为十二域系统提示词的唯一来源（正文按 §8 各域"系统提示要点"撰写），并随 `backend/prompts/scenarios/README.md` 提供域键说明与设计说明，供 git 版本管理；seed SHALL 从这些 .md 文件装载十二域的 `system_prompt`，连同 `task_template` 与 `preset_*` 一并写入，且幂等（已存在同名域时跳过或等价于无变化，不产生重复行）。种子完成后 SHALL 至少使"监控巡检、故障诊断"两域的 `preset_*` 指向真实存在、可用的四类示例实体，其余十域 `preset_*` 为空（由用户后续经注册中心挂载）。

#### Scenario: 种子后十二域就绪且与文件一致

- **WHEN** 完成种子装载后再次执行种子装载，再查询全部场景域
- **THEN** `scenario_templates` 恰有十二行，每行 `system_prompt` 与其 `<domain>.md` 内容一致；重复种子不产生重复行

#### Scenario: 两域带真实预设示例

- **WHEN** 完成种子装载后查看"监控巡检、故障诊断"两域
- **THEN** 这两域 `preset_*` 引用的技能/MCP/知识库/专家实体真实存在且可用（可被挂载到任务）；其余十域 `preset_*` 为空

### Requirement: 场景域列表与单查

系统 SHALL 提供 `GET /api/scenarios` 返回全部十二个场景域（按固定域序排列），每项含 `domain`、`name`、任务引导概览与该域预设装配摘要（skill/mcp/kb/expert 各类目标实体或数量），用于前端"选域"分类与列表展示；SHALL 提供 `GET /api/scenarios/<domain>` 返回单个场景域详情（含 `system_prompt` 全文与完整 `task_template`、`preset_*`），用于审阅与套用。未知 `domain` 的单查 SHALL 返回 404。

#### Scenario: 列表返回十二域、单查命中

- **WHEN** 初始化后请求 `GET /api/scenarios`，再对其中某域键请求 `GET /api/scenarios/<domain>`
- **THEN** 列表恰返回十二域且顺序固定、各含名称与装配摘要；单查返回该域 `system_prompt` 全文

#### Scenario: 单查未知域

- **WHEN** 请求 `GET /api/scenarios/not-a-domain`
- **THEN** 返回 404 且不报错

### Requirement: 选域套用预设装配

系统 SHALL 提供 `POST /api/tasks/<id>/scenario/apply`（请求体 JSON 必填受控 `domain`）：任务不存在 → 404；`domain` 非受控枚举 → 400 且不产生任何副作用。成功时系统 SHALL 将该任务 `scenario_domain` 置为该域，并把该域 `preset_*` 解析为当前存在且启用的四类实体 id，复用任务级 caps 全量覆盖语义（`PUT /api/tasks/<id>/caps` 的既有存储规则）写挂载；预设中不存在或已停用的实体 SHALL 被跳过（不以失败中断），响应 SHALL 返回装配汇总——成功挂载的分类与数量、被跳过的引用项。套用完成后任务仍可经既有 `PUT /api/tasks/<id>/caps` 逐次覆盖（细节栏 UI-06），不破坏"模板装配 + 人工微调"流程。

#### Scenario: 套用后域与挂载一致生效

- **WHEN** 用户对某任务 `POST /scenario/apply {"domain":"monitor-inspection"}`（该域已种子真实示例）
- **THEN** 返回 200 与装配汇总；任务 `scenario_domain` 为该域，随后 GET caps 反映该域预设成功挂载的实体

#### Scenario: 未知域/缺失任务/缺失实体均被妥善处理

- **WHEN** 对存在的任务套用非受控域、对不存在的任务 id 套用合法域、或套用某个预设引用了已被删除实体的域
- **THEN** 分别返回 400、404、200（汇总含被跳过引用项），均不产生错误的挂载副作用

### Requirement: 运行时按域注入系统提示（域会话）

系统 SHALL 在组装对话 Agent 的系统提示时，若任务 `scenario_domain` 为受控枚举中已存在模板的域，则该任务每次运行收到的 `system_prompt` SHALL 依序包含：(1) 该域模板 `system_prompt` 作为最前领域段；(2) 既有角色塑造与挂载能力注入（单专家人设/基础运维人设/已挂载技能指令，与 agentscope-runtime 挂载注入一致）；(3) 末尾追加统一约束段，内容含：禁止臆造数据；危险操作须二次确认；回答须引用来源；输出结构化（报告/表格/工单）。仅对绑定了场景域的任务 SHALL 做上述拼装；无 `scenario_domain` 或所绑域模板已不存在（实体被删）的任务 SHALL 沿用既有拼装，不因模板缺失报错或阻断对话。

#### Scenario: 域任务的系统提示含领域段与统一约束

- **WHEN** 对绑定了"故障诊断"域的任务发起对话
- **THEN** 模型收到的系统提示包含该域 `system_prompt` 内容，并以统一约束段（禁臆造/二次确认/引用来源/结构化）收尾

#### Scenario: 无域任务行为不变

- **WHEN** 对未绑定 `scenario_domain`（或所绑域模板不存在）的任务发起对话
- **THEN** 系统提示与既有拼装一致（不注入领域段、不追加统一约束段），对话正常进行
