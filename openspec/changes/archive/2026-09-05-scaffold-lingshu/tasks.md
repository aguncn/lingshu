# Tasks — scaffold-lingshu

> 依据 design.md（uv 于仓库根、backend 为包目录）。任务编号沿用任务书 P1 的三段分组。

## 1. Backend（uv + Flask 骨架）

- [x] 1.1 核对根 `pyproject.toml` 依赖齐全：flask / flask-cors / sqlalchemy / `agentscope>=2.06` / cryptography / python-dotenv / pytest；缺则用 `uv add` 补齐并跑 `uv sync`。不动 python 版本（`.python-version`=3.12）
- [x] 1.2 建 `backend/__init__.py`（顶部用 python-dotenv 加载根 `.env`，存在才加载），使 `backend` 成包
- [x] 1.3 写 `backend/config.py`：`Config` 读 `LINGSHU_MASTER_KEY`、数据目录、CORS 来源；SQLite 路径由仓库根推导为绝对路径 `backend/data/app.db`，并提供确保 `data/` 目录存在的方法
- [x] 1.4 写 `backend/extensions.py`：`db = SQLAlchemy()` 单例（后续 models 复用）
- [x] 1.5 写 `backend/app.py`：`create_app()` 组装 Flask + Flask-CORS（来源取 config）+ `db.init_app` + 注册 API blueprint，文件底部 `app = create_app()`；入口可用 `uv run flask --app backend.app run`
- [x] 1.6 写 `backend/api/health.py`：`url_prefix="/api"` 的 blueprint，`GET /api/health` 返回 `{"ok": true, "ts": <ISO 时间>}`，并建 `backend/api/__init__.py`
- [x] 1.7 写 `backend/migrate.py` 轻量迁移器：确保 data 目录 → 建 `schema_version` 元表 → 按编号执行 `backend/migrations/*.sql` 未应用项；启动时调用以保证 SQLite 文件生成且库内无业务表（migrations/ 仅空目录 + 说明）

## 2. Frontend（Vue3 + Vite 壳）

- [x] 2.1 建 `frontend/`：`package.json`（vue/vite/@vitejs/plugin-vue/element-plus/pinia/vue-router/axios + dev/build/preview 脚本）、`index.html`、`vite.config.js`（port 5173，`/api` 代理 → `http://localhost:5000`）
- [x] 2.2 建 `src/main.js`（挂载 Element Plus 全量 + Pinia + Router）、`src/App.vue`
- [x] 2.3 建 `src/router/index.js`（`/` → HomeView）、`src/api/http.js`（axios 实例 `baseURL:'/api'` + 响应错误归一）、`src/api/health.js`（封装 `getHealth`）
- [x] 2.4 建 `src/views/HomeView.vue`：onMounted 调 `getHealth`，成功显示「后端就绪」标签，失败显示不可达告警（页面不白屏）；`npm install && npm run dev` 冒烟

## 3. 规范与工程文件

- [x] 3.1 核对根 `CLAUDE.md` 与 `docs/CLAUDE.md` 内容一致（缺失才补写）
- [x] 3.2 新建 `openspec/project.md`：内容取自 `docs/openspec_project.md`
- [x] 3.3 扩展 `.gitignore`：追加 `backend/data/`、`node_modules/`、`.env`、`*.db`
- [x] 3.4 新建 `.env.example`：`LINGSHU_MASTER_KEY=`、`LINGSHU_DATA_DIR=`、`CORS_ORIGINS=http://localhost:5173`
- [x] 3.5 重写空壳 `README.md`：前后端两条启动命令 + `/api/health` 冒烟说明；删除残留空壳 `main.py` 与空文件 `2.06`

## 4. 联调与验收

- [x] 4.1 验收命令：`uv run flask --app backend.app run --port 5000`（另开终端）后 `curl http://127.0.0.1:5000/api/health` 返回 `{"ok":true,...}`；`cd frontend && npm run build` 通过
- [x] 4.2 手工验收清单全过：后端 5000 起得来且 health 返回 ok；前端 5173 起得来且首页显示后端就绪（后端停止时显示失败提示不白屏）；`git status` 未见 `.venv`/`backend/data/`/`node_modules` 被跟踪
