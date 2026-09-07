## 1. 数据模型与迁移

- [x] 1.1 `models.py`：删除 `SCENARIO_DOMAINS`/`ScenarioTemplate`/`Task.scenario_domain`；`Expert` 新增 `preset_skills/preset_mcp/preset_kb/preset_library`（JSON）、`default_provider_id`、`default_model_name`；`TaskExpert` 新增 `persona_snapshot`；`to_dict` 同步
- [x] 1.2 `migrations/0010_expert_profile.sql`：`DROP TABLE scenario_templates`、`ALTER TABLE tasks DROP COLUMN scenario_domain`、`ALTER TABLE experts ADD preset_*/default_provider_id/default_model_name`、`ALTER TABLE task_expert ADD persona_snapshot`、清理遗留 `ops-sme` 占位专家（未引用才删）
- [x] 1.3 删除 `backend/prompts/scenarios/`（十二域 .md + README）

## 2. 后端：专家档案字段承载与校验

- [x] 2.1 `services/registry_expert.py`：`_parse_preset_ids`/`_clean_provider_id` 写时校验（存在性、正整数、去重，非法 400）；create/update 白名单补 preset_*/default_*
- [x] 2.2 `api/experts.py`：create/patch 透传新字段

## 3. 后端：快照装配 service + apply 端点

- [x] 3.1 `services/expert_profile.py`：`apply_expert_profile(task_id, expert_id)`——caps 四类全量覆盖（experts=[档案]、预设按活跃过滤、失效进 skipped）、`preset_library` 补挂幂等只增、档案给了 provider 才落模型绑定
- [x] 3.2 `api/experts.py`：`POST /api/tasks/<id>/expert/apply`
- [x] 3.3 `services/capability.py`：`set_task_caps` 挂专家时落 `persona_snapshot`（enabled 且非空 system_prompt，停用→NULL）

## 4. 后端：十二域退场 + 运行时 + 种子

- [x] 4.1 删除 `services/scenario_service.py`、`api/scenario.py`、`seed/scenarios.py`；`app.py` 去 scenario_bp/run_scenario_seed
- [x] 4.2 `services/agent_runtime.py`：去域注入；`_compose_system_prompt` 人设=快照优先（persona_snapshot 非空胜出，否则回退 enabled 且非空 system_prompt，停用跳过）
- [x] 4.3 `services/task_service.py`/`api/space_task.py`：去 `scenario_domain` 分支与可更新字段；`task_type` 缺省回落 `general`
- [x] 4.4 `seed/profiles.py`（替代 scenarios.py）：幂等收敛 `SRE 值班专家` 档案（回填空 preset，不覆盖用户改动）

## 5. 前端：专家→运维专家档案 + 建任务套用 + 域条退场

- [x] 5.1 新增 `components/registry/ExpertCenter.vue` 档案组装整页；`CapabilityPlaza.vue`/`LeftPanel.vue` 加「运维专家」页签/导航
- [x] 5.2 `TaskCreateDialog.vue` 去「任务类型/场景模板」加可选「运维专家」下拉（预设摘要）；`stores/task.js` 建任务后 `applyExpertProfile`（apply 结果摘要/非阻断）
- [x] 5.3 删除 `components/layout/TemplateBar.vue`、`api/scenarios.js`、`stores/scenario.js`；`RightPanel.vue` 去 TemplateBar
- [x] 5.4 `DetailDock.vue`/`CapMountDialog.vue` 命名「运维专家」/快照说明、去场景域痕迹

## 6. 测试与收尾

- [x] 6.1 删除 `backend/tests/test_scenarios.py`；新增 `backend/tests/test_expert_profile.py`（档案 CRUD 校验/apply 覆盖/库引用幂等/默认模型/快照定格/停用与 404）；适配 `test_runtime_services.py`/`test_space_task.py`
- [x] 6.2 后端 `uv run pytest backend/tests/ -q` 全绿（133 passed）
- [x] 6.3 `cd frontend && npm run build` 通过；全站 grep 无 `scenario`/`TemplateBar`/`taskDialogDomain` 残留（仅历史迁移/注释）
