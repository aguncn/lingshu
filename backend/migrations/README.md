# 数据库迁移

编号 SQL 脚本，由 `backend/migrate.py` 按 `schema_version` 顺序执行，命名：`NNNN_描述.sql`（NNNN 为递增编号）。

本期脚手架不含任何业务表，故无编号迁移；P2+ 提案各自追加 `0001_*.sql`、`0002_*.sql` 等。
