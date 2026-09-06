## Context

P1 骨架已就位：`backend/` 包（`app.py` create_app 工厂 + `extensions.py` 的 `db = SQLAlchemy()` + `migrate.py` 轻量迁移器，已跑通 `0001+` 编号 SQL 由 `schema_version` 顺序应用）。本提案在其上加 5 张业务表、3 组 REST 端点与两级目录文件落盘。行为契约见 specs；动机见 proposal。本文只讲落地方式。

单人项目约束（CLAUDE.md）：单进程、不用 Redis/MQ、不引额外中间件；密钥不入明文；目录/模型集中在约定位置。

## Goals / Non-Goals

**Goals:**
- `models.py` 定义 `User/Space/Membership/Task/FileRecord` 并可直接映射到迁移建出的表。
- `/api/spaces`、`/api/spaces/<sid>/tasks`、`/api/tasks/<id>`、`/api/tasks/<id>/files` 可 curl 验收（建空间→建任务→列文件→删任务清目录）。
- 删除空间/任务时数据库记录与 `data/spaces/` 下目录**一致清理**。
- 内置管理员自动存在，建空间自动写 Owner Membership。

**Non-Goals:**
- 不做真实登录/鉴权拦截（单人模式，仅固定管理员占位；P10 再做安全基线）。
- 不建 ModelConfig/ModelProvider 表与 FK（P3 model-prompt-config 负责）；`tasks.model_config_id` 本期为**可空整数占位列，无 FK**。
- 不做上传/下载端点、不做会话/消息、不做十二域模板落库（P9）。
- 不做文件内容解析/切块（P6/LB 或知识库）。

## Decisions

**D1 — 落盘目录用 id 命名：`data/spaces/<space_id>/<task_id>/`。**
`<space_id>/<task_id>` 都是数据库整数主键。理由：① 任务改名不破坏文件归属（spec「重命名同步」要求即由此天然满足）；② 删除只需按 id 计算路径，不存在「标题含非法字符/重名」问题；③ 整数 id 缩小了路径穿越面。备选「按标题命名」被否：改名要搬目录、删除要处理重名，复杂度高且易错。

**D2 — 目录删除安全护栏（防路径穿越 + 不可逆操作约束）。**
所有目录操作集中在 `FileStore`：先以 `Config.DATA_DIR / "spaces"` 为根，`Path.resolve()` 后断言目标仍在根内，再执行。路由一律用 `<int:...>`（Flask 已拒绝非整型），service 层仍做 resolve 校验作为纵深防御。删除任务/空间**立即物理删除目录**（无回收站）：单人工具定位，宁可简单可预测；用 pytest 验收覆盖。

**D3 — 迁移 `0001_spaces_tasks.sql` 一次建全 5 表 + 种子管理员。**
建表顺序对齐外键依赖：`users` → `spaces` → `memberships` → `tasks` → `file_records`。关键约束：
- FK 全部带 `ON DELETE CASCADE`（space 删→memberships/tasks/file_records；task 删→file_records）。
- SQLite **默认不开启外键**：在 `migrate.py` 连接时执行 `PRAGMA foreign_keys=ON`，并为 SQLAlchemy 引擎加 `connect` 事件同样开启，否则级联不生效。
- 种子：`INSERT users(username='admin', role='owner', ...)`（运行时以 username 取回 admin id 作归属人）。
- 枚举以字符串列存储（SQLite 无原生 enum），`visibility`/`role`/`task_type`/`status` 的取值白名单放 Python 常量，API 层校验、非法值返回 400（spec R2/R6）。
时间戳统一用 UTC ISO 文本（与 P1 `schema_version.applied_at` 一致），由模型默认值生成。

**D4 — models 集中在 `models.py`，业务在 service，API 只校验+转发。**
- `models.py`：5 个 SQLAlchemy 声明模型；relationship 补 `cascade="all, delete-orphan"`（ORM 层兜底，主路径仍走 DB FK 级联）。
- `services/space_service.py`：list/create(写 Owner membership)/rename/delete(删 dir)；`services/task_service.py`：list/create/get/rename/delete(删 dir + FileRecord)；`services/file_store.py`：`task_dir(space_id, task_id)` 计算 + `ensure_dir` + `scan_dir`(返回文件元数据数组) + `delete_dir` + `record`(写 FileRecord，供 P6 上传复用)。
- API 层（`api/spaces.py`、`api/tasks.py` 或单域 blueprint，见 D5）只做参数解析→调 service→序列化。
为什么不把逻辑塞 API：后续 P3~P10 各端点都依赖同样的目录/权限语义，服务层复用价值高（对齐 CLAUDE.md §3）。

**D5 — 路由组织：单个域 blueprint `space_task_bp`（url_prefix=`/api`）承载空间/任务/文件三组路由。**
本域路由需同时覆盖 `/spaces`、`/spaces/<sid>/tasks`、`/tasks/<id>`、`/tasks/<id>/files`，若拆两个 blueprint 会因前缀冲突（`/tasks` 属 `/api/tasks`、`/tasks/<id>/files` 却要 `/api` 下）而别扭。一个 blueprint 最干净，后续域再各建 blueprint。health blueprint 保持独立不动。

**D6 — 响应/错误约定（轻量、无信封）。**
成功返回裸 JSON（dict/array）+ 恰当状态码（201/200）。错误统一 `{"message": "<中文说明>"}` + 状态码：参数/枚举非法→400，资源不存在→404，DB 完整性异常→400 转译。在 API 内用 helper `api_error(message, code)` 返回，不引入全局 errorhandler 复杂度（骨架期少而直白）。

**D7 — task_type / status 取值范围（本期最小白名单）。**
`TaskType`: `fault`(故障排查)、`change`(变更)、`alert`(告警处理)、`general`(通用对话/默认)。
`TaskStatus`: `open`(默认)、`in_progress`、`done`。
`visibility`: `private/team/public`；`MembershipRole`: `Owner/Editor/Viewer`（写角色时统一首字母大写）。十二域 `scenario_domain` 本期可空，值域由 P9 场景模板定义。

**D8 — 鉴权占位：当前用户=内置管理员。**
单人项目不做登录。service 侧通过 `UserService.get_admin()`（按 `username='admin'` 查）取当前归属人；无 Bearer/会话机制。P10 再引入真实身份。文件接口与删除接口本期不做基于角色/visibility 的访问拦截（spec 只要求字段落库与 Owner 写入，不含鉴权场景）。

## Risks / Trade-offs

- **[不可逆删目录]** DELETE 空间/任务直接物理删目录 → 路径白名单 + resolve 校验 + pytest 级联断言兜底；文档注明无回收站。
- **[SQLite FK 级联静默失效]** 若忘开 `PRAGMA foreign_keys=ON`，删父表会留孤儿行 → D3 双开（migrate.py 原始连接 + SQLAlchemy engine connect 事件）；pytest 断言「删空间后 memberships/tasks/file_records 计数为 0」。
- **[model_config_id 无 FK]** 本期为占位列，可能悬空 → P3 建表后补真实 FK 迁移，占位值语义为「未绑定」。
- **[无鉴权]** visibility/Membership 只落库不拦请求 → 单人项目明确接受，P10 补齐；spec 未承诺鉴权行为。
- **[并发写]** SQLite + 单进程开发，默认串行足够；不额外加锁。

## Migration Plan

`0001_spaces_tasks.sql` 为全新 DDL + 种子，幂等性由 migrate.py 的 `schema_version` 保证（编号已应用则跳过）。已存在的 P1 库会增量补跑 0001。回滚：无历史数据，删表重跑即可；`backend/data/app.db` 在 gitignore 内不构成基线。

## Open Questions

无阻塞性开放问题。
