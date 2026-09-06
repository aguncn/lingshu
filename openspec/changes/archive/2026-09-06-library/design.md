# library（P6 集中资料库）设计

## Context

- 现文件能力只服务**任务私有**：`GET /api/tasks/<id>/files` 走 `file_store.scan_task_dir`（目录扫描）、`GET .../files/<path>` 走 `resolve_task_file`，落盘根 `<DATA_DIR>/spaces`；**尚无任何上传端点**，`file_store.record()` 零调用者，`FileRecord` 行从未被写入。
- `file_records` 表约束：`path TEXT NOT NULL`（0001 建表 + 模型均不可空）——引用型记录不能存 NULL。
- 其它底座：`file_store._resolve_within_root` 白名单守卫（防路径穿越）；迁移到 0004；每连接 `PRAGMA foreign_keys=ON`；SQLite 布尔列= `INTEGER NOT NULL DEFAULT 1`（0003 先例）；`space_service.get_space_or_raise`（404）/ `task_service.get_task_or_raise`（404）；`ValidationError`=400、`NotFoundError`=404（`errors.py`）。
- 决策（用户已确认）：KB 不上接、`knowledge_chunks.file_id` 留 P8；引用= `FileRecord.library_file_id`；`shared` 布尔 + 空间归属过滤，RBAC 门控归 P8。
- 动机与 Why 见 proposal.md；可观察契约以 specs 两条 delta 为准。

## Goals / Non-Goals

**Goals**：可跨任务复用的文件资产 REST（上传/列表/下载/改名+分享标记/删除）；资料库落盘独立域 `data/library/` 且与任务域同等防穿越；任务以引用方式挂载库文档（不复制字节、删除任务不动库）；引用完整性（被引库文件不可删）。

**Non-Goals**（本提案明确不做）：接入知识库上传或回填 `knowledge_chunks.file_id`（P8 摄取时做）；真实任务工作区文件上传；多用户 RBAC / `shared` 的门控语义（仅标记 + 过滤视图）；内容去重/内容寻址/哈希、库内全文搜索、版本化；超大文件流式/分块。

## Decisions

### D1 资料库落盘布局：`data/library/<uuid-key>` 扁平，row.path 存 key
上传时生成 `key = uuid4().hex`，实体写 `data/library/<key>`；`LibraryFile.path` 存该 key（内部存储键，**任何 API 出口都不暴露**），`filename` 列只做展示/下载文件名。原文件名冲突互不影响（key 全局唯一），不存在「同目录同名」问题。
- 备选 A：按行 id 命名（`data/library/<id>`）→ 需先插入拿到 id 再写文件，流程倒置；备选 B：按 space 分层（`library/<space_id>/...`）→ 空间删除时要搬盘。均拒绝；**space 归属只体现在 DB 列，磁盘不镜像层级**（见 D3 的 SET NULL）。

### D2 复用 file_store 白名单守卫，扩展 library 域
把 `_resolve_within_root` 泛化为接受「根目录 + parts」的守卫，保留原 spaces 调用不变；`file_store.py` 新增 library 域函数：`write_library_file(key, data)`（先写 `data/library/.<key>.tmp` 再 `os.replace` 原子落盘，防半写）、`resolve_library_file(key) -> Path`（`is_file` 否则 `NotFoundError`）、`delete_library_file(key)`（幂等删）。路径均经守卫校验防穿越。业务编排/DB 事务放 `services/library_service.py`，与现 split（services 管逻辑、file_store 管盘）一致。

### D3 `LibraryFile` 模型：space_id 可空 + `ON DELETE SET NULL`
字段：`id, space_id(nullable, FK spaces ON DELETE SET NULL), filename(净化 basename, 无唯一), path(存储 key, NOT NULL), mime(nullable), size(NOT NULL), shared(Boolean default False), shared_at(TEXT nullable), created_at/updated_at`。不加 `owner_id`（本提案无请求身份，归属由 space_id 表达；taskbook 的 owner 留待鉴权引入，成本当前是死字段）。与任务无任何 FK。
- **ON DELETE SET NULL 理由**：删除空间不连带销毁库文档、不悬空其它空间任务的引用，空间私有文档自动降级为全局（磁盘不动，只改 DB 一行）；比 CASCADE（连带删文档/悬空引用）安全，符合单人「文档留存优先」。
- 空间存在性校验语义（上传/scope 过滤指定不存在空间 → **400** ValidationError，对齐 P5 `create_kb` 的 `_resolve_space` 风格）。

### D4 `FileRecord.library_file_id` 可空列（无 FK）+ path 兼容
- `path TEXT NOT NULL` 既有约束不允许 NULL → 引用行 **path 存空串 `''`**（语义=「无任务目录本地字节」，靠 `library_file_id IS NOT NULL` 区分），迁移只 `ALTER TABLE ... ADD COLUMN`，**不重建表**。
- `library_file_id` 为普通整数列**无 FK**：沿 `knowledge_chunks.file_id`「无 FK 不强绑」先例；引用完整性由 `DELETE /api/library/<id>` 服务层 400 守（D10），无需 DB 级联。
- 防重复引用：`CREATE UNIQUE INDEX (task_id, library_file_id) WHERE library_file_id IS NOT NULL`（部分唯一索引）兜底，服务层先查并回 400 友好消息。

### D5 API/服务分层与形态（对齐 skills/kb 域）
- 新 `api/library.py`：`library_bp = Blueprint(..., url_prefix="/api")` + `@library_bp.errorhandler(AppError)`；路由：`POST /api/library`、`GET /api/library`、`GET /api/library/<id>/download`、`PATCH /api/library/<id>`、`DELETE /api/library/<id>`、`POST /api/tasks/<tid>/library-files`、`DELETE /api/tasks/<tid>/library-files/<fid>`。
- 新 `services/library_service.py` 承载全部校验/事务；POST→`(dict, 201)`、PATCH 只转发 body 出现字段、DELETE→`{"ok": True}`。
- 文件名净化 `_clean_filename`（取 basename、剥 `/` `\`、strip、拒空）放 service，上传与 PATCH 改名共用；返回字段一律不含存储 key。

### D6 上传解析与归属
`request.files.get("file")` 缺/空名 → 400；读入字节（空内容文件合法）。归属：multipart 同传可选 `space_id` 表单字段——缺省或空 → 全局（DB NULL）；字符串须为纯正整数并存在否则 400。先建行拿到 id 无关（key 独立），故顺序：净化文件名 → 写盘（tmp+replace）→ 建行（key/size/mime 已定）→ commit；任一失败回滚并清理已写临时盘（防孤儿文件）。mime 用 `mimetypes.guess_type`。

### D7 列表 scope 过滤
`scope ∈ {all, global, shared, space}`，缺省 `all`；`space` 必带 `space_id`（纯正整数、存在，否则 400）；非法 scope 值 → 400。查询组合 `WHERE`（global: `space_id IS NULL`；space: `space_id = X`；shared: `shared = 1`；all: 无过滤），`ORDER BY id ASC`。`shared=true` 文档不设空间区分，进入 shared 视图即可见。

### D8 合并文件清单：改造 `GET /api/tasks/<id>/files`
既有路由保持路径不变，返回体**加法扩展**：真实工作区条目来自 `scan_task_dir` 并补 `kind="file"`；随后追加该任务的引用条目（查 `FileRecord` join `LibraryFile` where `task_id` & `library_file_id IS NOT NULL`），形如 `{kind:"ref", id, library_file_id, filename, size, mime, shared}`（filename/size/mime 抄录自库，供直接展示）；实体在前、引用在后，稳定有序。任务不存在 404 沿用 `get_task_or_raise`。
- 兼容性：每条新增 `kind` 字段、无引用时形状不变——对 P7 UI 友好；既有严格相等断言需随本提案更新（proposal Impact 已记）。

### D9 引用挂载/解除（不复制字节）
- `POST /api/tasks/<tid>/library-files` body `{library_file_id}`：任务不存在→404；缺参数/非正整数→400；库文件不存在→404；重复（task, lib）→400。构造 `FileRecord(space_id=task.space_id, task_id, filename/mime/size 抄录, path="", library_file_id)`；唯一索引兜底。返回 201 `{id, library_file_id, filename, size, mime, task_id, kind:"ref"}`。
- `DELETE /api/tasks/<tid>/library-files/<fid>`：`FileRecord` 存在、归属该任务、`library_file_id` 非空，否则 404；删除该行，**不动资料库** → `{"ok": True}`。
- 删除任务：既有 `ON DELETE CASCADE` 清其全部 `FileRecord`（含引用行）；库实体在 `data/library/`、非任务目录，天然不受影响（spec 已含该 Scenario）。

### D10 `DELETE /api/library/<id>` 引用完整性
先 `count(FileRecord.library_file_id == id)`，>0 → `ValidationError(400)`「仍被 N 个任务引用」；否则删行 + `delete_library_file(key)`（磁盘已无文件也成功清孤儿行，幂等）。行/盘任一缺失 → 404（行在盘失 → 下载场景 404 提示「文件已丢失」；删除场景照删行）。

## Risks / Trade-offs
- [绕过 API 删库行 → 引用悬空] → `DELETE` 服务层完整性 400 + 部分唯一索引；库文件删除唯一入口在本 API。悬空行不可经 API 产生。
- [`GET /files` 返回体加 `kind` 破坏既有严格断言] → 本提案随附更新既有 space_task 测试断言；语义加法式、非 breaking。
- [`data/library/` 文档无大小上限/去重] → 单人本地上传可接受；容量限制与内容寻址记 P1/P2，不引入本提案。
- [SET NULL 使空间私有文档在删空间后变全局可见] → 单人项目无鉴权，风险低；语义取向「文档留存优先」，避免级联丢数据。

## Migration Plan

- 新增 `backend/migrations/0005_library.sql`（一次性、编号顺序执行升至 5）：
  1. `ALTER TABLE file_records ADD COLUMN library_file_id INTEGER;`
  2. `CREATE INDEX idx_file_records_library_file_id ON file_records(library_file_id);`
  3. `CREATE UNIQUE INDEX uq_file_records_task_library ON file_records(task_id, library_file_id) WHERE library_file_id IS NOT NULL;`
  4. `CREATE TABLE library_files(...)`（DDL 风格对齐 0004：`space_id INTEGER REFERENCES spaces(id) ON DELETE SET NULL`、`shared INTEGER NOT NULL DEFAULT 0`、`shared_at TEXT`、`created_at/updated_at TEXT NOT NULL`）+ `idx_library_files_space_id`。
- 应用：`migrate.py` 启动自动补跑；真实库 0004→0005。回滚：单人本地可重建库重跑；无线上发布，无需向下迁移脚本（与既有迁移约定一致）。

## Open Questions

无会改 spec/方案/任务拆分的悬而未决项。已确认三项边界决策；`shared` 的实际门控语义（谁能见谁）与容量/寻址增强分别在 P8 与 P1/P2 推进。
