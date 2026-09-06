## Why

空间是**隔离与协作边界**，任务是**最小运行单元**——后续的模型绑定、能力装配、对话、文件、审计全都挂在 Space/Task 上。没有它们，P3+（模型/技能/资料库/工作台 UI）无挂载主体。本提案先把这块核心骨架落地为可运行、可验收的 CRUD + 文件落盘。

## What Changes

- 新增 5 张业务表 + 初始化迁移：`Space` `User` `Membership` `Task` `FileRecord`（字段对齐设计 §5.2，含 `visibility`、Membership 角色 `Owner/Editor/Viewer`），并种入内置管理员 `User`。
- 新增空间接口：`GET/POST /api/spaces`、`PATCH/DELETE /api/spaces/<id>`（列表/新建/改名/删除，删除级联清文件目录与子任务）。
- 新增任务接口：`GET/POST /api/spaces/<sid>/tasks`、`GET/PATCH/DELETE /api/tasks/<id>`（按空间建任务：命名+必选类型+绑模型占位 `model_config_id`；打开/改名/删除，删除清理文件目录）。
- 新增文件落盘服务 `services/file_store.py`：按 `data/spaces/<space>/<task>/` 两级目录写盘（本提案仅落盘能力 + 元数据，无实际上传接口）。
- 新增 `GET /api/tasks/<id>/files`：列出该任务工作空间目录下文件（TR-05）。
- 轻量鉴权占位：单人项目先用固定内置管理员（`X-Lingshu-User` 头或默认），不实现登录；权限模型落库但本期仅做一致性约束（TR-03 角色写入）。

非目标（后续提案）：登录鉴权体系、模型 provider/config 真实管理（P3）、能力挂载（P4）、注册中心 CRUD（P5）、上传下载接口（P6/LB 或后续）、会话（P7/后续）。

## Capabilities

### New Capabilities

- `space-task-mgmt`: 空间/用户/成员/任务/文件元数据模型与迁移；空间与任务的 CRUD（含 visibility 权限字段与 Membership 角色）；文件按「空间→任务」两级目录落盘与删除清理；列出任务工作空间文件。

### Modified Capabilities

（无。既有 `project-scaffold` 的「无业务表」是脚手架交付时的状态描述，本提案新增业务表不构成对其需求的修改。）

## Impact

- 数据模型：`backend/models.py` 新增 5 实体；新增迁移 `backend/migrations/0001_spaces_tasks.sql`（建 5 表 + 内置管理员 User 种子）。
- 接口：新增 `/api/spaces`、`/api/tasks`、`/api/tasks/<id>/files` 三组 REST 端点（契约见设计 §6）。
- 代码：`backend/app.py` 注册新 blueprint；新增 `backend/api/spaces.py`、`backend/api/tasks.py`；新增 `backend/services/space_service.py`、`backend/services/task_service.py`、`backend/services/file_store.py`（FileStore）。
- 文件系统：`backend/data/spaces/<space>/<task>/` 两级目录（gitignore 已覆盖 `backend/data/`）。
- 依赖：无新增外部依赖（复用 scaffold 的 Flask/SQLAlchemy/migrate.py）。
- 风险面：DELETE 空间/任务涉及**文件目录删除**（不可逆），需在 API 层确认 + 用绝对路径白名单约束防止路径穿越。
