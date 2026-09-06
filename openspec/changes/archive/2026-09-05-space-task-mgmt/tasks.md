# Tasks — space-task-mgmt

> 分组沿用任务书 P2 十项并补强：模型与迁移 / 服务与文件 / API / 测试验收。

## 1. 模型与迁移

- [x] 1.1 在 `backend/models.py` 定义 `User/Space/Membership/Task/FileRecord`（字段对齐设计 §5.2），含 `created_at/updated_at`；补枚举常量集（visibility/role/task_type/status）与 relationship + `cascade="all, delete-orphan"`
- [x] 1.2 写迁移 `backend/migrations/0001_spaces_tasks.sql`：按 users→spaces→memberships→tasks→file_records 建 5 表，FK 带 `ON DELETE CASCADE`，枚举列设 DEFAULT；末尾 `INSERT` 种子管理员 `username='admin'`
- [x] 1.3 `migrate.py` 连接时执行 `PRAGMA foreign_keys=ON`；`app.py` 为 SQLAlchemy engine 加 connect 事件开启 FK（否则 SQLite 级联失效）
- [x] 1.4 冒烟：`uv run flask --app backend.app run` 后库内出现 5 张新表 + admin 用户

## 2. 服务层（services/）

- [x] 2.1 写 `backend/services/file_store.py`：`task_dir/ensure_dir/scan_dir/delete_dir/record`；根锚定 `Config.DATA_DIR/"spaces"`，`resolve()` 后断言在根内（防路径穿越）；`scan_dir` 返回文件名/大小/mime 元数据数组
- [x] 2.2 写 `backend/services/space_service.py`：list / create(校验+写 Owner Membership) / rename / delete(删记录+级联清 `data/spaces/<sid>/` 目录)
- [x] 2.3 写 `backend/services/task_service.py`：list / create(必属空间+选 task_type+model_config_id 占位) / get / rename(目录名=id 不变) / delete(删记录+清 `data/spaces/<sid>/<tid>/` 目录与 FileRecord)
- [x] 2.4 建 `backend/services/__init__.py`，确保各 service 复用同一 admin 归属人解析（`User` 表按 username 查 `admin`）

## 3. API 层（api/）

- [x] 3.1 建域 blueprint（url_prefix=`/api`）承载 `GET/POST /api/spaces`、`PATCH/DELETE /api/spaces/<int:sid>`；成功 200/201、缺 name/非法 visibility→400 `{"message":...}`、不存在→404
- [x] 3.2 同 blueprint 承载 `GET/POST /api/spaces/<int:sid>/tasks`、`GET/PATCH/DELETE /api/tasks/<int:task_id>`；title/task_type 校验→400、空间/任务不存在→404
- [x] 3.3 承载 `GET /api/tasks/<int:task_id>/files`：扫描任务工作空间目录返回文件数组（目录不存在则按需创建并返回空数组）
- [x] 3.4 在 `app.py` 注册新 blueprint；错误响应统一 `{"message":...}` 无信封、无额外全局 errorhandler

## 4. 测试与验收

- [x] 4.1 写 `backend/tests/test_space_task.py` 冒烟：建空间→建任务→列文件（空）→放文件→列文件→删任务清目录 全通过；断言删空间后 memberships/tasks/file_records 计数为 0（验证 FK 级联）
- [x] 4.2 验收命令：`uv run pytest backend/tests/ -q` 全绿；curl `POST /api/spaces` 建 demo→`GET /api/spaces` 列表可见；`git status` 未见 `.venv`/`backend/data/`/`node_modules` 被跟踪
