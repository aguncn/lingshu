-- 0006: 智能体运行时（P8 agentscope-runtime）——建 messages + audit_log 表。
-- 作用：承载每任务对话历史（POST /api/tasks/<id>/chat 的用户/助手消息，供 GET /messages 与上下文续接），
--       以及运行时审计（model_call / tool_call / confirm_decision → AuditLog，供追溯）。
-- 语义/决策见 agentscope-runtime design D6：
--   - messages.task_id 级联删除（对话内容属任务，删任务即清历史）；
--   - audit_log.task_id ON DELETE SET NULL（审计不可随任务消失，追溯保留），故该列可空；
--   - audit_log 仅 created_at、无 updated_at：append-only 写入即不可变；
--   - 列均 TEXT/通用（actor/action/target/result/detail），兼容 P10 全量审计扩列扩展；
--   - 只建表 + 索引，无既有表改动；幂等由 migrate.py 的 schema_version 保证。
CREATE TABLE messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    run_id     TEXT,
    model      TEXT,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);

CREATE INDEX idx_messages_task_id ON messages (task_id);

CREATE TABLE audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER REFERENCES tasks (id) ON DELETE SET NULL,
    run_id     TEXT,
    actor      TEXT    NOT NULL,
    action     TEXT    NOT NULL,
    target     TEXT,
    result     TEXT,
    detail     TEXT,
    created_at TEXT    NOT NULL
);

CREATE INDEX idx_audit_log_task_id ON audit_log (task_id);
