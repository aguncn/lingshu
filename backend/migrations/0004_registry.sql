-- 0004: 注册中心（P5 registry-center）——建 knowledge_chunks 切块表。
-- 作用：承载 AD-03 文档上传解析后的切块（POST /api/kb/<id>/upload 写入、search 检索）。
-- 级联语义：删知识库 → 其全部切块随删（CASCADE）；file_id 预留 P6 资料库文件行（无 FK 不强绑）；
--          meta 存 JSON 文本（{filename, chunk_index, chars}），embedding 向量本期恒 NULL。
-- MCP env/headers 密文化不改 DDL：SQL 层本就是 TEXT，模型列类型由 db.JSON 改 db.Text 即可，无数据迁移。
-- 幂等由 migrate.py 的 schema_version 保证。
CREATE TABLE knowledge_chunks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id      INTEGER NOT NULL REFERENCES knowledge_bases (id) ON DELETE CASCADE,
    file_id    INTEGER,
    content    TEXT    NOT NULL,
    meta       TEXT,
    embedding  BLOB,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);

CREATE INDEX idx_knowledge_chunks_kb_id ON knowledge_chunks (kb_id);
