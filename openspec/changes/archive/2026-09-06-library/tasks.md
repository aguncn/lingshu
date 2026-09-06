# library 任务清单

实现纪律：每条独立可验收；完成一条即把 `- [ ]` 改 `- [x]`。验收口径 = spec 各 SHALL/Scenario + 本文件各条验收点。

## 1. 模型、落盘域与迁移

- [x] 1.1 models.py：新增 `LibraryFile` 模型（space_id 可空 FK→spaces ON DELETE SET NULL、filename 净化名、path 存储 key NOT NULL、mime、size、shared 布尔默认 False、shared_at 可空、时间戳），`to_dict` **不含 path 存储键**；给 `FileRecord` 加可空 `library_file_id` 整数列（无 FK），补中文注释说明 why（引用型记录 path 存空串、bytes 归资料库；沿 knowledge_chunks.file_id 无 FK 先例）。`knowledge_chunks`/KB 不改。
- [x] 1.2 file_store.py：把 `_resolve_within_root` 泛化为（root, parts）守卫、spaces 调用不变；新增 library 域函数 `write_library_file(key, data)`（tmp+`os.replace` 原子落盘，目录自动建）、`resolve_library_file(key)`（非文件→NotFoundError）、`delete_library_file(key)`（幂等删）。落盘根 `<DATA_DIR>/library`，全部经守卫防穿越（design D2）。
- [x] 1.3 迁移 `migrations/0005_library.sql`：`ALTER TABLE file_records ADD COLUMN library_file_id INTEGER` + `idx_file_records_library_file_id` + 部分唯一索引 `uq_file_records_task_library (task_id, library_file_id) WHERE library_file_id IS NOT NULL` + 建 `library_files` 表（DDL 对齐 0004：space_id `ON DELETE SET NULL`、shared `INTEGER NOT NULL DEFAULT 0`、shared_at TEXT、created_at/updated_at TEXT NOT NULL）+ `idx_library_files_space_id`。真实/临时库迁移后 schema_version=5。

## 2. 资料库资源服务与 API

- [x] 2.1 `services/library_service.py`：共享 helper（`_clean_filename` 取 basename/剥分隔符/拒空、`_require_positive_int`、`_resolve_space` 不存在→400、`_get_library_or_raise`→404）；`create_library(space_id, filename, data)`（归属全局/空间、写盘→建行→commit、失败清孤儿盘文件、返回 201 字典）与 `list_library(scope, space_id)`（scope ∈ all/global/shared/space，space 需存在否则 400，`ORDER BY id ASC`，出口不含 path）。
- [x] 2.2 `api/library.py`：`library_bp(url_prefix=/api)` + `@errorhandler(AppError)`；`POST /api/library`（multipart 字段 file，缺→400，可选 form `space_id`）返回 201；`GET /api/library`（query scope/space_id）。GET 列表返回空库 `[]`。
- [x] 2.3 service 补齐 `download_file(library_id)`（行 404；磁盘缺→404 可读消息；命名相对 2.1 草案的 `download_path` 但语义一致）、`update_library(library_id, **fields)`（仅应用出现字段：shared 须 bool 开关+记 shared_at、filename 净化改名；未知字段/非法→400）、`delete_library(library_id)`（被引用 count>0→400 完整性，否则删行+幂等删盘文件）。
- [x] 2.4 api/library.py 补齐 `GET /api/library/<id>/download`（`send_file` attachment + 原名 + mime）、`PATCH /api/library/<id>`、`DELETE /api/library/<id>`→`{ok:true}`。
- [x] 2.5 app.py 注册 `library_bp`；冒烟进程启动后 GET /api/library 返回 200（空数组）。

## 3. 跨任务引用与清单合并

- [x] 3.1 `services/library_service.py` 增 `attach_library(task_id, library_file_id)`（任务 404、参数 400、库文件 404、重复(task,lib) 400；构造 FileRecord：space_id=task.space_id、filename/mime/size 抄录、path=''、library_file_id）与 `detach_library(task_id, file_record_id)`（归属+确为引用否则 404）；api 增 `POST /api/tasks/<tid>/library-files`→201 与 `DELETE /api/tasks/<tid>/library-files/<fid>`→`{ok:true}`（只删引用行，绝不动资料库实体）。
- [x] 3.2 改造 `GET /api/tasks/<id>/files`（space_task.py，业务收敛到 `library_service.merge_task_files(task)`）：真实工作区条目 `scan_task_dir` 补 `kind="file"` 在前；追加引用条目 `{kind:"ref", id, library_file_id, filename, size, mime, shared}` 在后；任务不存在 404 沿用既有。无引用时形状不变（仅多 kind 字段）。

## 4. 验收测试

- [x] 4.1 新增 `backend/tests/test_library.py`（app(tmp_path) 夹具）：覆盖 spec 各 Scenario——上传 全局/指定空间/缺 file 400/不存在空间 400；列表 scope 互斥 + shared 视图 + 空库 [] + 非法 scope 400 + 不存在空间 400；下载字节一致/attachment 文件名/不存在 404；PATCH shared+改名回读/非法 400；删除 记录与盘文件消失/被引用 400；attach 成功回读/重复 400/库文件不存在 404；detach 后库仍在；合并清单 ref 条目出现与顺序。
- [x] 4.2 兼容既有：更新 `space_task` 文件列举相关断言（新增 kind 字段）；`uv run pytest backend/tests/ -q` 全绿（60/60，含既有无回归）；按验收命令起后端（临时 LINGSHU_DATA_DIR，端口 5057 干净进程）curl 冒烟：上传→列表(scope)→下载一致→分享标记→跨任务引用→删引用→删文件 全链通过，进程已停、临时目录已清理。附注：中文放 curl -d argv 会因 git-bash→curl.exe 编码损坏而 400，冒烟用 `--data-binary @utf8文件` 规避。

<!-- 完成标准：全部 [x]，openspec validate library 通过，spec 的 Requirement/Scenario 均有测试或手工判据覆盖。 -->
