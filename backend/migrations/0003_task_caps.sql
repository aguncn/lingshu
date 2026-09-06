-- 0003: 能力装配（P4 capability-mount）——4 张能力实体表(schema-only) + 4 张任务↔能力关联表 + 演示 seed。
-- 建表顺序对齐外键依赖：先实体表（skills/mcp_connectors/knowledge_bases/experts），
--   再关联表（task_skill/task_mcp/task_kb/task_expert）；knowledge_bases 引用 spaces(SET NULL)。
-- 级联语义：task 删 → 其全部 task_* 挂载行随删（CASCADE）；实体删 → 挂它的任务该行随删（CASCADE）；
--          space 删 → 全局库保持、空间专属库 space_id 置空（SET NULL）。
-- args/env/headers/composed_of 存 JSON 文本（模型侧 db.JSON 序列化，与 §5.2 (json) 一致）。
-- 时间戳存 UTC ISO 文本（与 0001/0002 一致）。幂等由 migrate.py 的 schema_version 保证。

-- ---------- 能力实体 ----------
CREATE TABLE skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT,
    skill_md    TEXT,
    version     INTEGER NOT NULL DEFAULT 1,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE mcp_connectors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    transport  TEXT    NOT NULL DEFAULT 'stdio',
    command    TEXT,
    args       TEXT,
    env        TEXT,
    url        TEXT,
    headers    TEXT,
    trust      INTEGER NOT NULL DEFAULT 0,
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);

CREATE TABLE knowledge_bases (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT    NOT NULL UNIQUE,
    space_id           INTEGER REFERENCES spaces (id) ON DELETE SET NULL,
    embedding_provider TEXT,
    chunk_size         INTEGER,
    status             TEXT    NOT NULL DEFAULT 'ready',
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL
);

CREATE TABLE experts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL UNIQUE,
    description   TEXT,
    system_prompt TEXT,
    role          TEXT    NOT NULL DEFAULT 'general',
    composed_of   TEXT,
    enabled       INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

-- ---------- 任务↔能力关联（(task,目标) 唯一） ----------
CREATE TABLE task_skill (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    skill_id   INTEGER NOT NULL REFERENCES skills (id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    UNIQUE (task_id, skill_id)
);

CREATE INDEX idx_task_skill_task_id ON task_skill (task_id);

CREATE TABLE task_mcp (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    mcp_id     INTEGER NOT NULL REFERENCES mcp_connectors (id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    UNIQUE (task_id, mcp_id)
);

CREATE INDEX idx_task_mcp_task_id ON task_mcp (task_id);

CREATE TABLE task_kb (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    kb_id      INTEGER NOT NULL REFERENCES knowledge_bases (id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    UNIQUE (task_id, kb_id)
);

CREATE INDEX idx_task_kb_task_id ON task_kb (task_id);

CREATE TABLE task_expert (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    expert_id  INTEGER NOT NULL REFERENCES experts (id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    UNIQUE (task_id, expert_id)
);

CREATE INDEX idx_task_expert_task_id ON task_expert (task_id);

-- ---------- 演示 seed（每类 1~2 条，供 curl/手工验收直接挂载；P5 提供 CRUD 后可覆盖/删除） ----------
INSERT INTO skills (name, description, skill_md, version, enabled, created_at, updated_at) VALUES
('sql-analysis',
 'SQL 慢查询与执行计划分析技能',
 '# SQL 分析技能

分析慢查询与执行计划时：先复述查询意图与表量级假设，再逐段解释执行计划代价；给出索引/改写建议前说明其适用条件与副作用；禁止盲改生产 DDL。',
 1, 1, '2026-09-05T00:00:00+00:00', '2026-09-05T00:00:00+00:00'),
('safe-shell',
 '排障纪律与安全 Shell 操作规范',
 '# 排障纪律

一切变更遵循排障纪律：先复现与缩小范围（现象→影响→最近变更），再分层假设并验证；执行写类命令前说明副作用并做无损检查；危险操作先走二次确认。',
 1, 1, '2026-09-05T00:00:00+00:00', '2026-09-05T00:00:00+00:00');

INSERT INTO mcp_connectors (name, transport, command, args, env, url, headers, trust, enabled, created_at, updated_at) VALUES
('db-ro', 'stdio', 'npx',
 '["-y", "mcp-server-sqlite", "./data/db-ro.db"]',
 NULL, NULL, NULL,
 0, 1, '2026-09-05T00:00:00+00:00', '2026-09-05T00:00:00+00:00');

INSERT INTO knowledge_bases (name, space_id, embedding_provider, chunk_size, status, created_at, updated_at) VALUES
('ops-knowledge', NULL, NULL, 400, 'ready', '2026-09-05T00:00:00+00:00', '2026-09-05T00:00:00+00:00');

INSERT INTO experts (name, description, system_prompt, role, composed_of, enabled, created_at, updated_at) VALUES
('ops-sme',
 '资深运维 SME：以事实与证据闭环输出诊断结论',
 '你是灵枢平台资深 SRE 运维专家。诊断问题遵循假设-验证闭环：先收集多维证据（日志/指标/配置），定位影响面后再给处置建议；建议可执行、含回滚与升级路径；无法确认处显式说明，不臆造结论。',
 'ops-sme', NULL, 1, '2026-09-05T00:00:00+00:00', '2026-09-05T00:00:00+00:00');
