## Context

现状（2026-09-05 仓库状态）：
- 仓库根已有 `pyproject.toml` + `.venv`（Python 3.12，`.python-version`）依赖已齐全：`flask 3.1`、`flask-cors`、`sqlalchemy 2.0`、`agentscope>=2.0.7.post1`、`cryptography`、`python-dotenv`、`pytest`（`uv.lock` 已生成）。→ **uv 工程位于仓库根，非 `backend/` 子目录**；`backend/` 是 Python 包目录，不是独立 pyproject。
- 根目录 `CLAUDE.md` 已就位且与 `docs/CLAUDE.md` 完全一致（含运行命令 `uv run flask --app backend.app run --port 5000`）。
- `openspec/` 只有 `config.yaml`（schema: spec-driven），`project.md`、`specs/`、`changes/` 待建；本变更即首个 capability（`project-scaffold`）。
- 残留 `uv init` 生成的空壳：根 `main.py`、空 `README.md`、空文件 `2.06`，应在骨架中清理。

动机见 proposal.md；行为契约见 specs/。本文只讲「怎么落地」。

## Goals / Non-Goals

**Goals:**
- 让 `uv run flask --app backend.app run --port 5000` 从仓库根一条命令起后端，`/api/health` 可 curl。
- 让 `npm run dev` 从 `frontend/` 起 Vue3 壳，首页经 Vite 代理调 health 并展示状态。
- 按技术方案 §9 预置目录结构，使 P2+ 的 model/api/service/迁移能直接插入，不返工。
- 规范文件（CLAUDE.md / openspec/project.md / .env.example / README）一次性落位。

**Non-Goals:**
- 不建任何业务表、业务接口、业务视图（P2+ 各提案负责）。
- 不做鉴权、权限模型、密钥真实落库流程（P10 security-audit 负责）；本变更只装好 `cryptography.Fernet` 依赖与 .env 约定。
- 不引入 AgentScope 运行时桥接（P8 agentscope-runtime 负责）。

## Decisions

**D1 — uv 工程放仓库根，`backend/` 作包目录。**
理由：现状 pyproject/uv.lock/.venv 已在根且依赖齐全，根 CLAUDE.md 的运行命令也指向 `--app backend.app`。备选「backend/pyproject.toml 独立子工程」需重排 venv、改两条启动命令、废弃现 uv.lock，改动大且与已定 CLAUDE.md 冲突。→ 采纳根工程，不新建 backend/pyproject。`backend/` 内放 `__init__.py`，使 `backend.app` 成为合法 import 路径。

**D2 — Flask 入口为 `backend/app.py` 的应用工厂 + 模块级实例。**
`create_app()` 组装 Flask + CORS + SQLite 初始化 + 注册 blueprint，文件底部 `app = create_app()`。这样 `flask --app backend.app run` 与 `from backend.app import create_app`（测试用）两种用法都稳定，不依赖 Flask 对工厂名的自动发现。CORS 允许来源取配置，默认 `http://localhost:5173`。
备选：直接模块级裸 Flask() 实例 — 不利于后续测试注入配置，P2+ 会引入 `create_app(config)` 需求，索性一步到位。

**D3 — health 走 blueprint（`backend/api/health.py`），不裸挂路由。**
对齐 §9「api/ 放各 blueprint」。本变更只注册一个 `/api/health`，但目录结构按 P2+ 扩展预留。blueprint 统一 `url_prefix="/api"`，health 路由返回 `{"ok": True, "ts": ...}`。

**D4 — 配置集中在 `backend/config.py`，读环境变量 + .env。**
`Config` 派生自环境：SQLite 路径（默认 `backend/data/app.db`，取仓库根算绝对路径）、`LINGSHU_MASTER_KEY`、上传目录（`backend/data/`）、CORS 来源。`backend/__init__.py` 顶部用 `python-dotenv` 载入根 `.env`（存在才加载）。密钥相关只留**读取约定与占位**，不落库（见 Non-Goals）。
备选：配置散在 app.py — 后续 ModelProvider/密钥/Fernet 都需要统一配置源，集中利于演进。

**D5 — extensions.py 单例 + migrate.py 轻量迁移器骨架。**
`backend/extensions.py` 建 `db = SQLAlchemy()` 单例。`backend/migrate.py` 实现：确保 `data/` 目录存在 → 用裸连接创建 `schema_version` 元表（非业务表）→ 按编号顺序执行 `backend/migrations/*.sql` 中未应用者。应用启动时 `db.init_app(app)` 并触发一次「确保元表 + 空跑迁移」，从而按 spec 生成 SQLite 文件但**无任何业务表**。本期 `migrations/` 放一个说明性 `.gitkeep` 或空目录即可，不写编号业务迁移。
备选：Alembic — CLAUDE.md 明令不用，维持自研轻量迁移器。

**D6 — 前端手写最小 Vite 工程，不交互式脚手架。**
为避免 `npm create vite` 交互与模板噪音，直接写：`package.json`（vue/vite/@vitejs/plugin-vue/element-plus/pinia/vue-router/axios + dev/build/preview 脚本）、`vite.config.js`（`server.proxy['/api'] → http://localhost:5000`、`server.port 5173`、plugin-vue）、`index.html`、`src/main.js`（挂 Element Plus + Pinia + Router）、`src/router/index.js`（`/` → Home）、`src/api/http.js`（axios 实例 `baseURL:'/api'`，简单响应拦截）+ `src/api/health.js`、`src/views/HomeView.vue`（调 `/api/health`，成功 el-tag「后端就绪」/ 失败 el-alert 提示，不白屏）、`App.vue`。
Element Plus 采用**全量引入**：单人项目换取零按需配置成本；后续 UI 提案如需瘦身再改 unplugin 按需。

**D7 — 项目文件一次性落位（大多已存在，任务=核对/补齐）。**
- `CLAUDE.md`：已存在且与 docs/CLAUDE.md 一致 → 核对即可，不覆盖。
- `openspec/project.md`：新建，内容取自 `docs/openspec_project.md`。
- `.gitignore`：在现有基础上追加 `backend/data/`、`node_modules/`、`.env`、`*.db`（保留 `.venv` 等已有规则）。
- `.env.example`：`LINGSHU_MASTER_KEY=`、`LINGSHU_DATA_DIR=`、`CORS_ORIGINS=http://localhost:5173`。
- `README.md`：替换空壳，写前后端两条启动命令 + health 冒烟 curl。
- 清理 `uv init` 空壳：删根 `main.py`、空文件 `2.06`。

## Risks / Trade-offs

- **Flask `--app backend.app` 解析在 Windows/uv 下的行为差异** → 采用 D2「模块级 `app` 实例」，双保险；验收用 curl 实测（tasks 验收命令）。
- **agentscope 锁定版本 `2.0.7.post1` 已满足 `>=2.06`** → 本能力不 import agentscope，只保证依赖在位；P8 才真正接线，若届时 API 有出入由 P8 提案处理。
- **Element Plus 全量引入使首屏体积偏大** → 单人开发期可接受，P7 UI 提案再评估按需引入。
- **端口 5000/5173 被占用** → 命令暴露 `--port`/Vite `server.port` 可改；文档标注端口含义。
- **「pyfernet」命名歧义** → 按根 CLAUDE.md/pyproject 既定约定落为 `cryptography.Fernet`，不引入独立包；已在 proposal Impact 中声明。
- **相对 SQLite 路径随 cwd 漂移** → D4 用仓库根推导绝对路径，避免从不同目录启动产生多个 db。

## Migration Plan

绿地项目，无历史迁移。回滚 = 删除本变更生成的 `backend/`、`frontend/`、`openspec/project.md`、`.env.example` 及 README/.gitignore 改动即可。`backend/data/app.db` 由 .gitignore 排除，不构成基线。

## Open Questions

无阻塞性开放问题。
