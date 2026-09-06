-- 0002: 模型供应商 / 任务级绑模型 / 提示词库 建表 + 常用任务类型预设种子。
-- 建表顺序对齐外键依赖：model_providers → model_configs → prompt_templates。
-- 级联语义：task 删 → model_configs 随删；provider 被 config 引用时 RESTRICT（DB 兜底，service 预查报 400）；
--          prompt 父版本删 → 后代 parent_id SET NULL（链头计算按 version 最大，不受影响）。
-- 时间戳存 UTC ISO 文本（与 0001/模型 _utcnow 一致）。幂等由 migrate.py 的 schema_version 保证。

CREATE TABLE model_providers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL UNIQUE,
    type          TEXT    NOT NULL DEFAULT 'openai',
    base_url      TEXT    NOT NULL,
    default_model TEXT,
    api_key_enc   TEXT,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

CREATE TABLE model_configs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER REFERENCES tasks (id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES model_providers (id) ON DELETE RESTRICT,
    model_name  TEXT,
    temperature REAL    DEFAULT 1.0,
    max_tokens  INTEGER,
    timeout     INTEGER DEFAULT 60,
    is_default  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    UNIQUE (task_id)
);

CREATE INDEX idx_model_configs_provider ON model_configs (provider_id);

CREATE TABLE prompt_templates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    category   TEXT    NOT NULL,
    domain     TEXT,
    content    TEXT    NOT NULL,
    version    INTEGER NOT NULL DEFAULT 1,
    parent_id  INTEGER REFERENCES prompt_templates (id) ON DELETE SET NULL,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    UNIQUE (name, version)
);

CREATE INDEX idx_prompt_templates_category ON prompt_templates (category);

-- 常用任务类型预设（MD-02）：category='task-preset'，version=1 链头，开箱可复用。
INSERT INTO prompt_templates (name, category, domain, content, version, parent_id, created_at, updated_at) VALUES
('写文档', 'task-preset', NULL,
 '你是一名 IT 运维文档助手。根据对话要求输出结构清晰、措辞准确的中文文档（方案/复盘/手册均可）。遵循：先给目标与范围，再分步骤，风险与回滚单独列出；涉及命令/代码用代码块。',
 1, NULL, '2026-09-05T00:00:00+00:00', '2026-09-05T00:00:00+00:00'),
('写代码', 'task-preset', NULL,
 '你是一名熟练的中文编程助手。请按需产出可运行代码：说明思路与关键取舍，代码随附简短中文注释，必要时给出调用示例与自测方法；安全敏感处（Shell/SQL/密钥）主动提示风险。',
 1, NULL, '2026-09-05T00:00:00+00:00', '2026-09-05T00:00:00+00:00'),
('数据分析', 'task-preset', NULL,
 '你是一名数据分析助手。面对日志/指标/表格类问题：先复述对数据的理解与假设，再给出可复现的分析步骤（含必要的 SQL/脚本），结论用数据说话并标注可信度与局限。',
 1, NULL, '2026-09-05T00:00:00+00:00', '2026-09-05T00:00:00+00:00'),
('排障', 'task-preset', NULL,
 '你是一名 IT 运维排障专家。遵循排障纪律：先复现与缩小范围（现象→影响→最近变更），再分层假设并验证；给出可执行的检查/修复命令前说明其副作用；始终先做无损操作。',
 1, NULL, '2026-09-05T00:00:00+00:00', '2026-09-05T00:00:00+00:00');
