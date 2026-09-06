## Why

PRD 核心交互是「能力按任务粒度按需挂载、可折叠」（UI-06），避免全局污染——每个任务只装配自己需要的技能/MCP/知识库/专家。当前任务只有 P2/P3 骨架，尚无任何「任务 ↔ 能力」的数据关联层；本提案把它建起来，作为 P5 注册中心（能力供给方）与 P8 运行时（能力消费方）之间唯一的装配数据源。

## What Changes

- **四张实体表 schema-only 落盘**：`Skill` / `MCPConnector` / `KnowledgeBase` / `Expert`（字段对齐设计 §5.2）。本提案只建表、只承载挂载引用与存在性校验，**不含** CRUD / MCP 连通 / KB 解析 / 专家编排等 P5 逻辑。
  - 决策背景：实体表原属 P5(registry-center)，但 P4 挂载校验需要「目标实体存在才允许关联」、且手工验收要求能挂真实 id——apply 前经用户确认采用**前置实体表**：P4 一次落 8 张表，P5 届时只做四中心 CRUD/编辑，不再重复建表。
- **四张关联表**：`task_skill` / `task_mcp` / `task_kb` / `task_expert`（`task_id` FK→`tasks.id`，目标列 FK→对应实体表，`(task,目标)` 唯一），任务删除级联清理挂载。
- **`PUT /api/tasks/<id>/caps` 全量覆盖式更新挂载**：请求 `{skills:[], mcps:[], kbs:[], experts:[]}`（每键为 id 数组，缺失的键视为清空该分类）；元素必须是已存在的实体 id（去重、正整数），否则 400。
- **`GET /api/tasks/<id>/caps` 返回当前挂载**（四组 id 清单）。
- **`services/capability.py`**：统一校验/写入/读取，并提供供 P8 使用的「按任务加载已挂载实体」聚合读取。
- **迁移 `0003_task_caps.sql`**：建 4 实体表 + 4 关联表 + 极少量演示行 seed（每类 1~2 条，供 curl/手工验收直接挂载）。
- 仅后端数据关联；**不接 AgentScope 运行时**（P8），**不改前端**（P7 细节栏四个空态分区的数据接入，留给 registry-center 及其后的 UI 对接提案）。

## Capabilities

### New Capabilities

- `capability-mount`: 任务级能力挂载——Skill/MCPConnector/KnowledgeBase/Expert 四实体表的 schema 基础、task_* 四关联表、`PUT/GET /api/tasks/<id>/caps` 全量覆盖装配与存在性校验、capability 服务聚合读取。纯后端数据契约，供 P5/P7/P8 消费。

### Modified Capabilities

（无——不触碰任何既有 spec；P2/P3 接口仅被消费、P5 实体表另行 CRUD。）

## Impact

- **backend/models.py**：集中新增 `Skill/MCPConnector/KnowledgeBase/Expert` + `TaskSkill/TaskMcp/TaskKb/TaskExpert`（TimestampMixin、集中白名单常量如 transport/status）。
- **backend/migrations/0003_task_caps.sql**：新编号迁移（建 8 表 + 演示 seed 行），随 migrate.py 顺序执行，不动 Alembic。
- **backend/services/capability.py**：新增（校验/覆盖写/读 + 供 P8 的 load_mounted 聚合）。
- **backend/api/capability.py**（新 blueprint）：`PUT/GET /api/tasks/<id>/caps`；在 app 注册。
- **backend/tests/test_capability.py**：挂载→读取→覆盖改→删级联 全链路 + 校验 400/404。
- **后续被消费**：registry-center(P5) 在其上补 CRUD；AgentRuntime(P8) 读 capability 聚合装配工具/注入；P7 细节栏挂载 UI（registry-center 对接提案接通数据源）。
- **范围外**：无前端、无新第三方依赖、无运行时、无 P5 的 CRUD/解析/连通/编排。
