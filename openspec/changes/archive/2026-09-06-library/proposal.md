# library 提案

## Why

运维中大量文件资产（排障手册、日志片段、SQL 脚本）会被多个任务反复使用，而现有文件只按「任务工作空间」私有落盘（`data/spaces/<space>/<task>/`），跨任务只能拷贝副本——造成文件散落、多份不一致、无统一入口。资料库（LB-01）提供**跨任务集中复用**的文件资产层：上传/下载/列表统一管理，归属空间或全局（不绑单一任务），可打分享标记，并允许任务以「引用」方式挂载库文件（引用不复制字节），与「任务私有文件」区分。

## What Changes

- 新增独立 `LibraryFile` 数据实体（空间/全局两级归属，全局=space_id 可空；单任务不归属），物理文件落 `data/library/`，不与任务目录纠缠。
- 新增资料库 REST 契约（前缀 `/api/library`）：上传、列表（按空间/全局/分享等 scope 过滤）、下载、分享标记开关、删除。
- 跨任务引用：`FileRecord` 增加可空 `library_file_id` 列表示「该条文件记录指向资料库某文件、字节不复制」；`GET /api/tasks/<id>/files` 的返回把任务真实工作区文件与库引用合并列出并带来源 `kind` 标记；删除引用只删 FileRecord，资料库文件被引用时禁止删除（引用完整性）。
- 复用 P2 `file_store` 的落盘路径白名单手法，为 `data/library/` 域扩展同等防护（防路径穿越）。
- **知识库(KB)不上接**：`POST /api/kb/<id>/upload` 行为与 `knowledge_chunks.file_id`（恒 NULL）本期均不改动，KB 切块指向资料库文件的回填留待 P8 运行时摄取。

## Capabilities

### New Capabilities
- `library`: 跨任务集中资料库——`LibraryFile` 实体与 CRUD/下载/分享标记/跨任务引用的 REST 契约。

### Modified Capabilities
- `space-task-mgmt`: 「任务工作空间文件列举」与「文件两级落盘与元数据记录」两条需求扩展——`FileRecord` 允许 `library_file_id` 引用型记录，`GET /api/tasks/<id>/files` 返回真实工作区文件与库引用的合并清单。

## Impact

- 后端：`models.py` 新增 `LibraryFile` 并给 `FileRecord` 加可空 `library_file_id` 列（含 ORM 关系与 `to_dict`）；新 `backend/services/library_service.py`（+ `file_store` 增 `data/library/` 域函数）；新 `backend/api/library.py`（`url_prefix=/api`）。
- 迁移：`backend/migrations/0005_library.sql`（建 `library_files` 表、`file_records` 加列、相关索引），`migrate.py` 按序执行升至 5。
- 既有行为变更：`GET /api/tasks/<id>/files` 出口语义扩展（**对 P7 UI 与既有测试为兼容性注意点**）。
- 注册：`backend/app.py` 注册 `library_bp`。
- 测试：新增 `backend/tests/test_library.py`；既有 `space_task` 文件列举相关断言随合并清单语义做兼容更新。
- 不改动：知识库上传/检索、能力挂载、模型/提示词域；`knowledge_chunks.file_id` 维持 NULL。
