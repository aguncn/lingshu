-- 0005: 资料库（P6 library LB-01）——建 library_files 表 + file_records 加引用列。
-- 作用：承载跨任务集中文件资产（POST/GET /api/library、download、PATCH shared/改名、DELETE），
--       以及任务经 FileRecord.library_file_id 对库文件的「引用」挂载（引用不复制字节）。
-- 语义/决策见 library design：
--   - file_records.path 为 NOT NULL（0001），引用行不落任务目录 → 本脚本不重建表，仅 ADD COLUMN，
--     引用行 path 存空串、靠 library_file_id IS NOT NULL 区分（D4）；
--   - library_file_id 无 FK 不强绑（沿 knowledge_chunks.file_id 先例），引用完整性由服务层 DELETE 守（D10）；
--   - 部分唯一索引 (task_id, library_file_id) WHERE IS NOT NULL 在 DB 层兜底防同一任务重复引用同一文件；
--   - library_files.space_id 可空 = 全局库；ON DELETE SET NULL：删空间自动降级为全局，磁盘不动、不悬空引用（D3）。
-- 幂等由 migrate.py 的 schema_version 保证。
ALTER TABLE file_records ADD COLUMN library_file_id INTEGER;

CREATE INDEX idx_file_records_library_file_id ON file_records (library_file_id);
CREATE UNIQUE INDEX uq_file_records_task_library
    ON file_records (task_id, library_file_id)
    WHERE library_file_id IS NOT NULL;

CREATE TABLE library_files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id   INTEGER REFERENCES spaces (id) ON DELETE SET NULL,
    filename   TEXT    NOT NULL,
    path       TEXT    NOT NULL,
    mime       TEXT,
    size       INTEGER NOT NULL DEFAULT 0,
    shared     INTEGER NOT NULL DEFAULT 0,
    shared_at  TEXT,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);

CREATE INDEX idx_library_files_space_id ON library_files (space_id);
