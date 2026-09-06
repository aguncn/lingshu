# CLAUDE.md — 灵枢 (Lingshu) IT 运维智能体平台

你在此项目中担任**实现者**：按 OpenSpec 提案逐任务编码，保持简单、可运行、可验收。

## 1. 技术栈（不要引入额外复杂度）
- 后端：Python 3.12 + Flask + Flask-CORS + SQLAlchemy + SQLite（单文件库，路径 backend/data/app.db）。
- 包管理：uv（用 `uv sync` / `uv run`；不要手写 pip install 全局）。
- 前端：Vue 3 + Vite + Element Plus + Pinia + Axios（开发态 5173，代理 /api → 5000）。
- 智能体：AgentScope >= 2.06（Agent/ReAct、Toolkit、OpenAIChatModel、MCP 客户端、reply_stream 事件流）。
- 规范驱动：OpenSpec（`/opsx:propose` → `/opsx:apply` → `/opsx:verify` → `/opsx:archive`）。
- **禁止为单人项目引入**：Redis / 消息队列 / K8s / 微服务 / 额外中间件。单进程前后端即可。

## 2. 目录约定（见技术方案文档 §9）
- backend/：app.py、config.py、extensions.py、models.py、migrate.py、services/、api/、migrations/、seed/、prompts/、data/。
- frontend/src：router/、store/、api/、views/、components/。
- openspec/：project.md、specs/、changes/。

## 3. 编码规范
- 注释用中文，说明「为什么」；变量/函数名用英文。
- 后端：API 层只做校验+调用 service，业务逻辑放 services/；模型集中 models.py。
- 数据库变更：写 `migrations/NNNN_*.sql` 编号脚本，由 migrate.py 按 schema_version 顺序执行；不动 Alembic。
- 前端：视图放 views/，复用组件放 components/，接口封装放 api/，状态放 store/。
- 密钥：永不明文入库；用 cryptography.Fernet 加密（密钥取 LINGSHU_MASTER_KEY 或 .env），展示脱敏。
- 文件落盘：按 `data/spaces/<space>/<task>/` 两级；资料库归 `data/library/`。

## 4. AgentScope 集成要点（详见技术方案 §7）
- 模型：ModelProvider+ModelConfig → `OpenAIChatModel(model, api_key, base_url)`（OpenAI 兼容）。
- 运行时：AgentRuntime.build() 组装 Agent+Toolkit（内置工具 + 挂载的 MCP 工具 + 技能/RAG 注入）。
- 流式：Flask 同步框架跑 AgentScope 异步事件流，用「线程+queue」桥接转 SSE（见技术方案 §7.6 骨架）。
- 安全：内置写类工具（Bash/Write/Edit）默认 Permission confirm（危险操作二次确认）；调用写 AuditLog。

## 5. OpenSpec 工作流纪律
- 每个提案只做一件事（一个能力域），范围不超过 PRD 一个编号组。
- tasks.md 每条 = 一个接口/一张表/一个视图/一个迁移，单条可独立验收（8–12 条/提案）。
- 实现用 **新开干净会话** 跑 `/opsx:apply`，避免超长上下文改无关文件。
- 每完成一个提案必须 `verify` 再 `archive`；不攒一堆。
- 设计权威参考：@灵枢_技术方案与架构设计.md；任务划分：@灵枢_开发计划与OpenSpec提案任务书.md。

## 6. 运行与验证
- 后端：`uv run flask --app backend.app run --port 5000`
- 前端：`cd frontend && npm run dev`
- 测试：`uv run pytest backend/tests/ -q`
- 每次交付按提案的「验收命令 + 手工验收清单」逐项确认。

## 7. 范围外（本期不做，记 P1/P2）
自动化引擎、深度 MCP 真实连接器、多专家编排、容量预测、知识图谱、向量化 RAG（默认关键词检索）。
