## Purpose

灵枢的工程骨架基线：后端 Flask + SQLite、前端 Vue3 + Vite、以及 OpenSpec/CLAUDE.md 等规范文件全部就位，前后端联调可跑通 `/api/health`，作为后续提案增量开发的地基。

## Requirements

### Requirement: 后端提供健康检查接口

系统 SHALL 暴露 `GET /api/health`，无需鉴权即返回 HTTP 200，JSON 体包含 `ok: true` 与服务端时间戳。

#### Scenario: 请求健康检查成功

- **WHEN** 任意客户端以 `GET` 请求 `/api/health`
- **THEN** 返回 HTTP 200，且 JSON 体含 `"ok": true`

#### Scenario: 服务未启动时健康检查不可达

- **WHEN** 后端进程未运行，客户端请求 `/api/health`
- **THEN** 请求失败（连接被拒绝或超时），不返回任何 HTTP 200 响应

### Requirement: 后端可用一条命令从仓库根目录启动

系统 SHALL 支持用 `uv run flask --app backend.app run --port 5000` 从仓库根目录启动后端，监听 5000 端口，并对开发源（5173）启用 CORS。

#### Scenario: 从仓库根目录启动成功

- **WHEN** 在仓库根目录执行 `uv run flask --app backend.app run --port 5000`
- **THEN** 后端进程正常监听 5000 端口且无启动报错，健康检查可达

#### Scenario: 前端跨源调用被放行

- **WHEN** 运行于 `http://localhost:5173` 的前端以浏览器方式请求后端 `/api/health`
- **THEN** 响应携带允许该源的 CORS 头，浏览器不报跨域错误

### Requirement: 后端数据库与迁移器骨架就位且无业务表

系统 SHALL 在 `backend/data/app.db` 初始化 SQLite 库，并提供轻量迁移器骨架，由 `schema_version` 顺序执行 `backend/migrations/*.sql`；本能力交付时 SHALL 不含任何业务表。

#### Scenario: 启动后生成本地 SQLite 文件

- **WHEN** 后端首次完成启动与初始化
- **THEN** `backend/data/app.db` 存在，且库内不存在任何业务实体表

### Requirement: 前端工作台骨架代理 /api 并可展示后端就绪

系统 SHALL 提供 Vue3 前端工作台骨架：Vite 开发服务运行于 5173，将 `/api` 请求代理到 5000；首页 SHALL 调用 `/api/health`，并在后端可达时展示「后端就绪」状态、不可达时展示失败提示。

#### Scenario: 后端可达时首页展示就绪

- **WHEN** 后端运行中，用户在浏览器打开前端首页（5173）
- **THEN** 首页自动请求 `/api/health` 并展示「后端就绪」成功状态，无未捕获控制台错误

#### Scenario: 后端不可达时首页展示失败提示

- **WHEN** 后端未运行，用户在浏览器打开前端首页（5173）
- **THEN** 首页展示后端不可达的失败提示，前端页面本身不白屏

### Requirement: 前端打包构建通过

系统 SHALL 保证前端 `npm run build`（生产构建）可成功完成、无构建报错。

#### Scenario: 生产构建成功

- **WHEN** 在 `frontend/` 下执行 `npm run build`
- **THEN** 构建成功退出码为 0 且产物正常产出

### Requirement: 项目规范与工程文件就位

仓库根目录 SHALL 存在 `CLAUDE.md`（内容含技术栈、目录约定、编码规范、运行与验证命令，见《开发执行手册》§3）、`openspec/project.md`（项目简述）、`.env.example`（含 `LINGSHU_MASTER_KEY`、上传目录、CORS 来源占位）、`.gitignore`（忽略 `.venv`、`backend/data/`、`node_modules`）与 `README.md`（含前后端两条启动命令）。

#### Scenario: 规范文件齐备

- **WHEN** 检查仓库根目录文件
- **THEN** `CLAUDE.md`、`openspec/project.md`、`.env.example`、`.gitignore`、`README.md` 均存在且内容完整

#### Scenario: 敏感与生成目录不被 git 跟踪

- **WHEN** 在已完成环境初始化的仓库执行 `git status`
- **THEN** `.venv`、`backend/data/`、`node_modules` 及密钥文件不出现在被跟踪的新增文件列表中

#### Scenario: 密钥不落明文库

- **WHEN** 后续能力需要持久化任何密钥/凭据
- **THEN** 它们 SHALL 以 `cryptography.Fernet` 加密后存储，读取展示时脱敏
