-- 0001: 空间与任务管理建表 + 内置管理员种子。
-- 建表顺序对齐外键依赖；FK 一律 ON DELETE CASCADE（删父清子），由 migrate.py / app.py 开启 SQLite PRAGMA 生效。
-- 时间戳存 UTC ISO 文本（与模型 _utcnow 一致）。

CREATE TABLE users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT    NOT NULL UNIQUE,
    display_name TEXT,
    role         TEXT    NOT NULL DEFAULT 'owner',
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

CREATE TABLE spaces (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT,
    owner_id    INTEGER NOT NULL REFERENCES users (id),
    visibility  TEXT    NOT NULL DEFAULT 'private',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE memberships (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id   INTEGER NOT NULL REFERENCES spaces (id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role       TEXT    NOT NULL DEFAULT 'Viewer',
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    UNIQUE (space_id, user_id)
);

CREATE TABLE tasks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id         INTEGER NOT NULL REFERENCES spaces (id) ON DELETE CASCADE,
    title            TEXT    NOT NULL,
    task_type        TEXT    NOT NULL,
    status           TEXT    NOT NULL DEFAULT 'open',
    scenario_domain  TEXT,
    visibility       TEXT    NOT NULL DEFAULT 'private',
    model_config_id  INTEGER,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);

CREATE INDEX idx_tasks_space_id ON tasks (space_id);

CREATE TABLE file_records (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id   INTEGER NOT NULL REFERENCES spaces (id) ON DELETE CASCADE,
    task_id    INTEGER NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    filename   TEXT    NOT NULL,
    path       TEXT    NOT NULL,
    mime       TEXT,
    size       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);

CREATE INDEX idx_file_records_task_id ON file_records (task_id);

-- 内置管理员（单人模式默认归属人；id 自增为 1）
INSERT INTO users (username, display_name, role, created_at, updated_at)
VALUES ('admin', 'Administrator', 'owner', '2026-09-05T00:00:00+00:00', '2026-09-05T00:00:00+00:00');
