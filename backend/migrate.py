# 轻量数据库迁移器（不用 Alembic，见 CLAUDE.md §3）。
# 约定：backend/migrations/NNNN_*.sql，按 NNNN 编号顺序只执行一次。
# 元表 schema_version 记录已应用版本；应用启动时调用 run_migrations()。
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _connect(db_path: Path) -> sqlite3.Connection:
    """裸连接 SQLite。

    为什么不用 SQLAlchemy 引擎：迁移器要在 ORM 层就绪/模型注册前工作，
    用标准库 sqlite3 更简单且无初始化顺序依赖。
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    # SQLite 外键默认关闭：不开则 0001 里 ON DELETE CASCADE 级联静默失效，
    # 删空间/任务会残留孤儿行（见 design D3）。
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_schema_version(conn: sqlite3.Connection) -> None:
    """建 schema_version 元表（非业务表），记录每个已应用迁移的编号。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version     INTEGER PRIMARY KEY,
            applied_at  TEXT NOT NULL
        )
        """
    )
    conn.commit()


def run_migrations(db_path: Path) -> None:
    """按编号顺序执行未应用过的 migrations/*.sql，并把版本写入 schema_version。

    幂等：重复调用对已应用版本直接跳过；本能力没有编号迁移，因此只保证
    建出 sqlite 文件与元表（规格要求启动后库内无任何业务表）。
    """
    _ensure_schema_version_conn = _connect(db_path)
    try:
        _ensure_schema_version(_ensure_schema_version_conn)
        applied = {
            row[0]
            for row in _ensure_schema_version_conn.execute(
                "SELECT version FROM schema_version"
            )
        }

        for script in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            version = int(script.stem.split("_", 1)[0])  # NNNN_xxx.sql -> NNNN
            if version in applied:
                continue  # 已应用，跳过（保证幂等）
            _ensure_schema_version_conn.executescript(script.read_text(encoding="utf-8"))
            _ensure_schema_version_conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (version, datetime.now(timezone.utc).isoformat()),
            )
        _ensure_schema_version_conn.commit()
    finally:
        _ensure_schema_version_conn.close()
