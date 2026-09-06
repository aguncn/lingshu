-- 0007: 十二运维场景域（P9 scenario-templates）——建 scenario_templates 表。
-- 作用：承载每域系统提示词/任务引导与预设装配（skills/mcp/kb/expert id 数组），
--       供 GET /api/scenarios、POST /tasks/<id>/scenario/apply 与 P8 运行时按域注入消费。
-- 语义/决策见 scenario-templates design D1/D3：
--   - domain 唯一 = 十二域受控键（SCENARIO_DOMAINS），行由 seed 从 prompts/*.md 装载；
--   - system_prompt/task_template 为 TEXT；preset_* 存 JSON 文本（id 数组，SQLite 无 JSONB），
--     注册中心实体动态增删 → 引用允许漂移，apply 交现存集合并跳过失效项；
--   - 沿用 created_at/updated_at TEXT 由 ORM 统一写入（其余业务表一致先例）。
-- 幂等由 migrate.py 的 schema_version 保证。
CREATE TABLE scenario_templates (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    domain         TEXT    NOT NULL UNIQUE,
    name           TEXT    NOT NULL,
    system_prompt  TEXT    NOT NULL,
    task_template  TEXT,
    preset_skills  TEXT    NOT NULL DEFAULT '[]',
    preset_mcp     TEXT    NOT NULL DEFAULT '[]',
    preset_kb      TEXT    NOT NULL DEFAULT '[]',
    preset_expert  TEXT    NOT NULL DEFAULT '[]',
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);
