## Why

灵枢需要一个**可运行**的工程骨架：统一后端（uv + Flask + SQLite）、前端（Vue3 + Vite）与 OpenSpec 工作流基线。没有骨架，后续 P2+ 提案（空间任务、模型配置、能力装配等）就没有落点、也无法按「起服务 + 调接口」验收。CLAUDE.md / openspec/project.md 作为团队与 AI 的长期规范，必须先就位。

## What Changes

- 新增 `backend/`：Flask 应用包 + CORS + SQLite 初始化 + `GET /api/health`；依赖用 uv 管理（root pyproject），Python 3.12。
- 新增 `frontend/`：Vue3 + Vite + Element Plus + Pinia + Axios 骨架；`/api` 代理到 5000；首页调用 `/api/health` 并展示「后端就绪」。
- 新增 `openspec/project.md`：项目简述（对照 `docs/openspec_project.md`）。
- 写入根目录 `CLAUDE.md`（对照 `docs/CLAUDE.md` 全文）。
- 补齐 `.env.example` 与 `.gitignore`（忽略 `.venv` / `data/` / `node_modules`），README 记录启停命令。
- 写 `backend/config.py`、`extensions.py`、`migrate.py` 轻量迁移器**骨架**（本期不建任何业务表）。

非目标：不实现任何业务功能（空间/任务/模型/注册中心/资料库等均为后续提案）。

## Capabilities

### New Capabilities

- `project-scaffold`: 灵枢工程骨架——backend(Flask+SQLite+CORS+health) + frontend(Vue3 工作台壳子) + 项目规范文件(CLAUDE.md/openspec/project.md/.env.example/.gitignore/README) 全部就位，前后端联调可跑通。

### Modified Capabilities

（无既有 spec 需修改）

## Impact

- 依赖：新增 `flask`、`flask-cors`、`sqlalchemy`、`agentscope>=2.06`、`cryptography`（Fernet 密钥加密）、`python-dotenv` —— 由 uv 管理于 root `pyproject.toml`（uv.lock 已生成）。前端新增 `element-plus`、`pinia`、`axios`、`vue-router`。
  - 说明：提示词中「pyfernet」按项目既定约定落地为 `cryptography.Fernet`（见 docs/CLAUDE.md §3、pyproject.toml 现状）；不引入独立 `pyfernet` 包。
- 目录：新建 `backend/`、`frontend/`、`backend/data/`(gitignore)。
- 接口：新增 `GET /api/health`（无鉴权、无业务副作用）。
- 代码库状态：全部为新增文件，无存量代码改动；无业务表。
