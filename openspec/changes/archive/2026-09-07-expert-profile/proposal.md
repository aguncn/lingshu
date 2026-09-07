## Why

前四轮（C1 空间树 / C2 任务沙箱 / C3 会话抽屉 / C4 能力广场）已让工作台具备「主区整页能力页 + 左栏导航 + 任务树」的信息架构。但「专家」与「场景域」仍有两处与用户心智错位的积弊：

1. **Expert 只是纯人设**：真正把「提示词 + 固定技能/MCP/知识库」绑成一份可复用装配的载体是「十二域场景模板预设」；专家本体（`system_prompt/composed_of`）从未被运行时按档案消费，`composed_of` 多专家协作更是从未落地。
2. **十二域是"建任务即套用预设"的唯一入口**（顶部域条 + 建任务「场景模板」下拉），但它是一套强行的 12 分类心智，用户并不按它组织工作。

C5 已拍板：**把「专家」升格为「运维专家」自包含档案**——模型 / 提示词(人设) / 技能 / MCP / RAG(知识库) / 资料库文档 一起在能力广场的「运维专家」整页里组装；新建任务时可选一位运维专家，选中后**快照装配**到任务（人设→挂载该专家并定格快照、预设技能/MCP/RAG→覆盖挂载、预设资料库→补挂引用、默认模型→任务模型绑定），此后改/停用档案不影响已建任务。同时**硬删十二场景域体系**（`scenario_templates` 表、`tasks.scenario_domain` 列、`prompts/scenarios/*.md`、顶部域条、seed、spec、测试）。UI 一律称「运维专家」；数据库/接口内部命名保持 `expert`/`experts`。

## What Changes

- **专家 → 可复用档案**：`experts` 新增 `preset_skills/preset_mcp/preset_kb/preset_library`（JSON id 数组，指向 Skill/MCPConnector/KnowledgeBase/LibraryFile）与可选默认模型 `default_provider_id`/`default_model_name`（空→供应商 default_model）；CRUD 写时校验存在性。`composed_of` 保留列/删除守卫但移出前端（deprecated）。
- **快照装配到任务**：新增 `POST /api/tasks/<id>/expert/apply`——四类 caps 全量覆盖写（experts=[档案]、预设仅保留可用引用、失效进 skipped）、预设资料库补挂引用（只增不拆、幂等）、档案给了供应商才落任务模型绑定；挂载专家时把 `system_prompt` 定格进 `task_expert.persona_snapshot`。运行时人设 = 快照优先、空快照回退 live、停用跳过。
- **十二场景域硬删**：`scenario_templates` 表 DROP、`tasks.scenario_domain` 列 DROP（迁移 0010）、删 `prompts/scenarios/`、删 scenario seed/service/api/前端条/店、移除运行时按域注入。`task_type` 仅从新建入口移除（列 + 后端缺省 'general' + SpaceTree/ChatPane 徽标保留）。
- **UI**：新建任务对话框去「任务类型/场景模板」改可选「运维专家」（带预设摘要）；能力广场新增「运维专家」整页档案组装；去除聊天/工作区顶部场景域快捷条；细节栏/挂载编辑器命名「运维专家」。

## Capabilities

### New Capabilities
<!-- 无新增能力文件夹。 -->

### Modified Capabilities
- `scenario-templates`: 整份退场——十二域实体/列表/套用/运行时注入全部移除，能力 retire（spec 删除）。
- `registry-center`: Expert（AD-04）从「纯人设 + composed_of 组合」升格为「可复用运维专家档案」——preset_* + default_provider/default_model + 快照套用语义。
- `capability-mount`: 新增「档案快照装配到任务」需求；「四类能力实体持久化基础」专家字段对齐档案。
- `agentscope-runtime`: 挂载能力注入改为「快照优先」人设解析（无域注入）。
- `space-task-mgmt`: 建任务 `task_type` 可选缺省 `general`（新建入口不再暴露）。
- `workbench-ui`: 能力广场新增运维专家整页与左栏入口；新建任务去任务类型/场景模板改可选运维专家；移除顶部场景域快捷条；细节栏命名与装配说明改为运维专家档案快照。

## Impact

- 后端：`models.py`（Expert 档案字段 / Task 去 scenario_domain / ScenarioTemplate 删除 / TaskExpert.persona_snapshot）、`migrations/0010_expert_profile.sql`、`services/registry_expert.py`/`api/experts.py`（档案字段 + apply 路由）、`services/expert_profile.py`（新增，快照装配）、`services/capability.py`（挂专家落 persona_snapshot）、`services/agent_runtime.py`（快照人设解析）、`services/task_service.py`（task_type 缺省 general）、`services/scenario_service.py`/`api/scenario.py`/`seed/scenarios.py` 删除、`seed/profiles.py`（档案种子替代场景种子）。
- 前端：`components/registry/ExpertCenter.vue`（档案组装页，新增）、`components/layout/CapabilityPlaza.vue`/`LeftPanel.vue`（运维专家入口/页签）、`components/layout/TaskCreateDialog.vue`/`stores/task.js`（建任务套用档案）、`DetailDock.vue`/`CapMountDialog.vue`（运维专家命名/快照说明）、删除 `TemplateBar.vue`/`api/scenarios.js`/`stores/scenario.js`。
- 测试：`backend/tests/test_scenarios.py` 删除；新增 `backend/tests/test_expert_profile.py`（档案 CRUD/apply 覆盖/库引用幂等/默认模型/快照定格）；`test_runtime_services.py`/`test_space_task.py` 适配（task_type 缺省 general）。
