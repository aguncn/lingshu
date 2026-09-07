-- 0010: 运维专家档案（C5 expert-profile）——experts 升格为自包含档案 + 十二场景域硬删。
-- 作用两块：
--   a) experts 增列 preset_*/default_*：把「专家」从纯人设（0003 只有 name/description/
--      system_prompt/role/composed_of/enabled）升级为可复用「运维专家档案」——
--      人设(system_prompt) + 预设技能/MCP/RAG(知识库)/资料库(文档引用) id 数组 + 可选默认模型。
--      preset_* 存 JSON 文本（id 数组，与 0007 scenario_templates 同风格；SQLite 无 JSONB），
--      模型侧 db.JSON 序列化。default_provider_id 引用 model_providers(SET NULL：删供应商置空，
--      不让供应商删除被档案卡死)；default_model_name 空 = 用供应商 default_model。
--   b) task_expert 增 persona_snapshot：挂载时快照该专家的 system_prompt（C5 快照语义——
--      任务人设取挂载行快照而非实时读档案，改档案不影响已建任务）。
--   c) 硬删十二场景域体系：DROP scenario_templates 表（其 preset 语义整体由 Expert 档案承接），
--      ALTER tasks DROP COLUMN scenario_domain（SQLite ≥3.35）。prompts/scenarios/*.md 目录
--      与 seed/scenario_service/api 由代码库一并移除，不在此脚本内（非 schema 数据）。
-- 数据整理：删除 0003 遗留占位专家 ops-sme——仅当其未被任何 task_expert 引用（避免级联删任务挂载）；
--   C5 由 seed/profiles.py 装载语义化命名的「SRE 值班专家」档案取代它。
-- 幂等由 migrate.py 的 schema_version 保证（本脚本只执行一次）。
ALTER TABLE experts ADD COLUMN preset_skills  TEXT NOT NULL DEFAULT '[]';  -- JSON [Skill.id,...]
ALTER TABLE experts ADD COLUMN preset_mcp     TEXT NOT NULL DEFAULT '[]';  -- JSON [MCPConnector.id,...]
ALTER TABLE experts ADD COLUMN preset_kb      TEXT NOT NULL DEFAULT '[]';  -- JSON [KnowledgeBase.id,...]
ALTER TABLE experts ADD COLUMN preset_library TEXT NOT NULL DEFAULT '[]';  -- JSON [LibraryFile.id,...]
ALTER TABLE experts ADD COLUMN default_provider_id INTEGER REFERENCES model_providers (id) ON DELETE SET NULL;
ALTER TABLE experts ADD COLUMN default_model_name   TEXT;

DROP TABLE IF EXISTS scenario_templates;
ALTER TABLE tasks DROP COLUMN scenario_domain;

ALTER TABLE task_expert ADD COLUMN persona_snapshot TEXT;

DELETE FROM experts
WHERE name = 'ops-sme'
  AND NOT EXISTS (SELECT 1 FROM task_expert te WHERE te.expert_id = experts.id);
